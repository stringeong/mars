"""'파일 나눠서 병렬 실행' 블록의 실행 준비.

- plan_graph: 연결된 파일과 지금 사용 가능한 Worker 수로 조각 계획을 세운다(저장하지 않음).
  편집기 미리보기와 구성 검사, 실행이 같은 계획을 쓴다.
- materialize: 실행을 시작할 때 조각 파일을 저장하고 그래프를 조각 수만큼 펼친다.

나누는 규칙 자체는 splitter.py의 순수 함수가 맡는다.
"""

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from .. import models
from ..config import UPLOAD_DIR
from . import dag, orchestrator, splitter
from .splitter import SplitError

# 조각 파일의 저장 이름 접두사. 파일 보관함 목록에는 보이지 않고 실행 이력을 지울 때 함께 지운다
PIECE_PREFIX = "split-"
# 이보다 큰 파일은 읽어 보지 않고도 최대 조각 수로 나눌 수 없다
MAX_SOURCE_BYTES = splitter.MAX_PARTS * splitter.PIECE_HARD_LIMIT * 4

UNIT_LABELS = {"line": "줄", "csv": "행", "file": "파일"}


@dataclass
class Settings:
    unit: str = "auto"
    parts: int | None = None  # None이면 자동
    overlap: int = 0
    max_chars: int = splitter.DEFAULT_MAX_CHARS


@dataclass
class NodePlan:
    """분할 블록 하나의 조각 계획."""

    node_id: str
    unit: str
    workers: int
    auto: bool
    overlap: int = 0
    # 줄·행 단위: 원본 파일과 조각
    source: models.UploadedFile | None = None
    pieces: list[splitter.Piece] = field(default_factory=list)
    # 파일 단위: 조각별 파일 id
    file_groups: list[list[int]] = field(default_factory=list)
    file_names: dict[int, str] = field(default_factory=dict)

    @property
    def parts(self) -> int:
        return len(self.file_groups) if self.unit == "file" else len(self.pieces)

    @property
    def sizes(self) -> list[int]:
        if self.unit == "file":
            return [len(group) for group in self.file_groups]
        return [piece.count for piece in self.pieces]

    def summary(self) -> dict:
        """편집기·실행 화면의 미리보기: "워커 2대 → 3조각 예상 (667 / 667 / 666줄)"."""
        return {
            "node_id": self.node_id,
            "unit": self.unit,
            "unit_label": UNIT_LABELS[self.unit],
            "workers": self.workers,
            "parts": self.parts,
            "auto": self.auto,
            "sizes": self.sizes,
            "overlap_lines": self.overlap,
            "source_name": self.source.original_name if self.source else None,
        }


@dataclass
class SplitPlans:
    plans: dict[str, NodePlan] = field(default_factory=dict)
    errors: dict[str, SplitError] = field(default_factory=dict)

    def problem(self, node: dict) -> tuple[str, str] | None:
        """dag.inspect_graph의 split_problem 콜백."""
        error = self.errors.get(node["id"])
        return (error.code, error.message) if error else None

    def summaries(self) -> list[dict]:
        return [plan.summary() for plan in self.plans.values()]


def settings_of(node: dict) -> Settings:
    raw = node.get("split") if isinstance(node.get("split"), dict) else {}
    unit = raw.get("unit") if raw.get("unit") in ("line", "csv", "file") else "auto"
    parts = raw.get("parts")
    parts = min(max(1, parts), splitter.MAX_PARTS) if isinstance(parts, int) and not isinstance(parts, bool) else None
    overlap = raw.get("overlap_lines")
    overlap = min(max(0, overlap), splitter.MAX_OVERLAP_LINES) if isinstance(overlap, int) else 0
    max_chars = raw.get("max_chars")
    max_chars = (
        min(max(splitter.MIN_MAX_CHARS, max_chars), splitter.PIECE_HARD_LIMIT)
        if isinstance(max_chars, int) else splitter.DEFAULT_MAX_CHARS
    )
    return Settings(unit=unit, parts=parts, overlap=overlap, max_chars=max_chars)


def available_workers(devices: list[models.Device], node: dict) -> int:
    """이 블록을 지금 맡을 수 있는 Worker 수: 온라인이고, 블록 모델을 가지고 있고, 사용률 상한 아래인 기기.

    블록에 Worker를 지정했으면 그 기기만 센다.
    """
    pinned = node.get("worker_id")
    model = node.get("model") or ""
    return sum(
        1
        for device in devices
        if pinned in (None, device.id)
        and orchestrator.device_is_online(device)
        and orchestrator.device_has_model(device, model)
        and orchestrator.device_has_capacity(device)
    )


def read_text(uploaded: models.UploadedFile) -> str:
    if uploaded.size_bytes > MAX_SOURCE_BYTES:
        raise SplitError(
            "split_too_large",
            f"'{uploaded.original_name}' 파일이 너무 커서 최대 {splitter.MAX_PARTS}조각으로 나눌 수 없습니다. "
            "파일을 줄여 주세요.",
        )
    path = UPLOAD_DIR / uploaded.stored_name
    if not path.is_file():
        raise SplitError("split_unreadable", f"'{uploaded.original_name}' 파일을 서버에서 찾을 수 없습니다.")
    data = path.read_bytes()
    # 엑셀에서 저장한 한글 CSV는 cp949인 경우가 많다
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _estimated_chars(uploaded: models.UploadedFile, max_chars: int) -> int:
    """파일 단위로 나눌 때 조각 수를 정하기 위한 글자 수 추정. 문서 파일은 조각 하나를 채운다고 본다."""
    if Path(uploaded.original_name).suffix.lower() in splitter.TEXT_SUFFIXES:
        return uploaded.size_bytes
    return max_chars


def plan_node(
    node: dict, files: list[models.UploadedFile], devices: list[models.Device]
) -> NodePlan:
    """분할 블록 하나의 조각 계획. 나눌 수 없으면 SplitError."""
    settings = settings_of(node)
    names = [uploaded.original_name for uploaded in files]
    unit = settings.unit if settings.unit != "auto" else splitter.detect_unit(names)
    if unit in ("line", "csv") and len(files) > 1:
        raise SplitError(
            "split_unsupported",
            "줄·행 단위로 나누려면 파일을 1개만 연결하세요. 여러 파일은 '파일 단위'로 나눌 수 있습니다.",
        )
    suffix = Path(names[0]).suffix.lower() if names else ""
    supported = splitter.CSV_SUFFIXES if unit == "csv" else splitter.LINE_SUFFIXES | splitter.CSV_SUFFIXES
    if unit is None or (unit in ("line", "csv") and suffix not in supported):
        raise SplitError(
            "split_unsupported",
            f"'{names[0]}'은(는) 나눌 수 없는 형식입니다. "
            "줄 단위는 .txt .log .md .jsonl, 행 단위는 .csv 파일만 나눌 수 있습니다.",
        )

    workers = available_workers(devices, node)
    if workers == 0:
        raise SplitError(
            "split_no_worker",
            "지금 이 블록을 맡을 수 있는 워커가 없습니다. 온라인이고 블록 모델이 설치된 워커가 필요합니다.",
        )

    plan = NodePlan(node["id"], unit, workers, auto=settings.parts is None)
    if unit == "file":
        count = settings.parts or splitter.auto_parts(
            sum(_estimated_chars(uploaded, settings.max_chars) for uploaded in files), workers, settings.max_chars
        )
        plan.file_groups = splitter.distribute([uploaded.id for uploaded in files], count)
        plan.file_names = {uploaded.id: uploaded.original_name for uploaded in files}
        return plan

    plan.source = files[0]
    plan.overlap = settings.overlap if unit == "line" else 0
    plan.pieces = splitter.split_text(
        read_text(files[0]),
        unit,
        parts=settings.parts,
        workers=workers,
        overlap=settings.overlap,
        max_chars=settings.max_chars,
    )
    return plan


def plan_graph(db: Session, user_id: int, graph: dict) -> SplitPlans:
    """그래프의 모든 분할 블록에 대해 조각 계획을 세운다. 파일을 저장하지 않으므로 미리보기에도 쓴다.

    클라우드 블록과 파일이 없는 블록은 dag.inspect_graph가 따로 오류로 알리므로 건너뛴다.
    """
    from .transfers import is_cloud_node

    result = SplitPlans()
    targets = [
        (node, dag.input_sources(graph, node)[0])
        for node in graph.get("nodes", [])
        if node.get("type", "agent") == "agent" and dag.split_enabled(node) and not is_cloud_node(node)
    ]
    targets = [(node, file_ids) for node, file_ids in targets if file_ids]
    if not targets:
        return result

    devices = db.query(models.Device).filter(models.Device.user_id == user_id).all()
    wanted = {file_id for _, file_ids in targets for file_id in file_ids}
    by_id = {
        uploaded.id: uploaded
        for uploaded in db.query(models.UploadedFile)
        .filter(models.UploadedFile.user_id == user_id, models.UploadedFile.id.in_(wanted))
        .all()
    }
    for node, file_ids in targets:
        try:
            missing = [file_id for file_id in file_ids if file_id not in by_id]
            if missing:
                raise SplitError("split_unreadable", f"연결된 파일 #{missing[0]}을(를) 찾을 수 없습니다.")
            result.plans[node["id"]] = plan_node(node, [by_id[file_id] for file_id in file_ids], devices)
        except SplitError as error:
            result.errors[node["id"]] = error
    return result


def _save_piece(db: Session, user_id: int, source: models.UploadedFile, name: str, text: str) -> models.UploadedFile:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    stored_name = f"{PIECE_PREFIX}{uuid.uuid4().hex}{Path(source.original_name).suffix.lower()}"
    (UPLOAD_DIR / stored_name).write_bytes(data)
    piece = models.UploadedFile(
        user_id=user_id,
        original_name=name[:255],
        stored_name=stored_name,
        content_type=source.content_type,
        size_bytes=len(data),
    )
    db.add(piece)
    return piece


def materialize(db: Session, user_id: int, graph: dict, plans: SplitPlans) -> tuple[dict, list[dict]]:
    """조각 파일을 저장하고 분할 블록을 조각 수만큼 펼친다.

    (실행 스냅샷으로 쓸 그래프, 실행 기록 input_files에 덧붙일 원본↔조각 기록)을 돌려준다.
    조각이 하나뿐인 블록은 나누지 않고 원본 파일을 그대로 쓴다.
    """
    names = {node["id"]: node.get("name") or node["id"] for node in graph.get("nodes", [])}
    pieces_by_node: dict[str, list[dict]] = {}
    records: list[dict] = []
    for node_id, plan in plans.plans.items():
        if plan.parts <= 1:
            continue
        entries: list[dict] = []
        record_pieces: list[dict] = []
        if plan.unit == "file":
            for index, group in enumerate(plan.file_groups, start=1):
                label = ", ".join(plan.file_names.get(file_id, f"파일 #{file_id}") for file_id in group)
                entries.append({
                    "uploaded_file_ids": group,
                    "split_part": {"unit": "file", "label": label},
                })
                record_pieces.append({"index": index, "file_ids": group, "label": label})
            source_files = [{"id": file_id, "name": name} for file_id, name in plan.file_names.items()]
        else:
            saved = [
                _save_piece(
                    db, user_id, plan.source,
                    splitter.piece_name(plan.source.original_name, piece.index, plan.parts), piece.text,
                )
                for piece in plan.pieces
            ]
            db.flush()
            for piece, uploaded in zip(plan.pieces, saved):
                label = splitter.range_label(piece.start, piece.end, plan.unit)
                entries.append({
                    "uploaded_file_ids": [uploaded.id],
                    "split_part": {
                        "unit": plan.unit,
                        "label": label,
                        "line_start": piece.start,
                        "line_end": piece.end,
                        "context_start": piece.context_start,
                        "context_end": piece.context_end,
                        "file_id": uploaded.id,
                        "file_name": uploaded.original_name,
                        "source_file_id": plan.source.id,
                        "source_name": plan.source.original_name,
                    },
                })
                record_pieces.append({
                    "index": piece.index,
                    "file_ids": [uploaded.id],
                    "label": label,
                    "name": uploaded.original_name,
                    "line_start": piece.start,
                    "line_end": piece.end,
                })
            source_files = [{"id": plan.source.id, "name": plan.source.original_name}]
        pieces_by_node[node_id] = entries
        records.append({
            "kind": "split",
            "id": node_id,
            "label": f"{names.get(node_id, node_id)} · {plan.parts}조각으로 나눔",
            "node_ids": [dag.split_node_id(node_id, index) for index in range(1, plan.parts + 1)],
            "files": source_files,
            "directories": [],
            "unit": plan.unit,
            "workers": plan.workers,
            "pieces": record_pieces,
        })
    return dag.expand_split_nodes(graph, pieces_by_node), records


def delete_piece_files(db: Session, graph: dict | None) -> None:
    """실행 스냅샷이 쓰던 조각 파일을 지운다. 사용자가 올린 원본 파일은 건드리지 않는다."""
    file_ids = {
        (node.get("split_part") or {}).get("file_id")
        for node in (graph or {}).get("nodes", [])
        if isinstance(node.get("split_part"), dict)
    }
    file_ids.discard(None)
    if not file_ids:
        return
    rows = (
        db.query(models.UploadedFile)
        .filter(models.UploadedFile.id.in_(file_ids), models.UploadedFile.stored_name.like(f"{PIECE_PREFIX}%"))
        .all()
    )
    for uploaded in rows:
        (UPLOAD_DIR / uploaded.stored_name).unlink(missing_ok=True)
        db.delete(uploaded)
