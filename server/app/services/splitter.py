"""파일을 조각으로 나누는 순수 함수.

큰 파일 하나를 여러 Worker가 나눠 처리할 수 있도록 줄·CSV 행 단위로 자른다.
DB나 파일 시스템은 건드리지 않는다(읽기·저장은 split_inputs.py가 한다).
"""

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

# 줄 단위로 나눌 수 있는 형식. JSONL은 한 줄이 한 레코드라 줄 단위와 같다
LINE_SUFFIXES = {".txt", ".log", ".md", ".jsonl"}
CSV_SUFFIXES = {".csv"}
# JSON은 맨 바깥이 배열(또는 배열 하나를 가진 객체)일 때 항목 단위로 나눈다
JSON_SUFFIXES = {".json"}
TEXT_SUFFIXES = LINE_SUFFIXES | CSV_SUFFIXES | JSON_SUFFIXES

DEFAULT_MAX_CHARS = 12_000
MIN_MAX_CHARS = 1_000
# Worker가 파일 하나에서 읽는 최대 글자 수(worker/agent/executor.py FILE_CONTEXT_CHARS).
# 조각이 이보다 크면 뒷부분이 잘리므로 넘지 않게 나눈다
PIECE_HARD_LIMIT = 30_000
MAX_PARTS = 50
MAX_OVERLAP_LINES = 200


class SplitError(ValueError):
    """나눌 수 없는 입력. code는 구성 검사(inspect_graph)의 문제 코드로 쓴다."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Piece:
    """조각 하나. start~end는 원본 기준 처리 대상 범위(1부터, 양 끝 포함)."""

    index: int
    start: int
    end: int
    text: str
    # 앞 조각에서 가져온 참고 문맥의 범위. 겹침을 쓰지 않으면 None
    context_start: int | None = None
    context_end: int | None = None

    @property
    def count(self) -> int:
        return self.end - self.start + 1


def detect_unit(names: list[str]) -> str | None:
    """연결된 파일로 나누는 단위를 정한다. 여러 파일이면 파일 단위, 하나면 형식에 따른다."""
    if len(names) > 1:
        return "file"
    if not names:
        return None
    suffix = Path(names[0]).suffix.lower()
    if suffix in CSV_SUFFIXES:
        return "csv"
    if suffix in JSON_SUFFIXES:
        return "json"
    return "line" if suffix in LINE_SUFFIXES else None


def part_sizes(total: int, parts: int) -> list[int]:
    """total개를 parts조각에 균등하게 나눈다. 나머지 r개는 앞의 r개 조각에 하나씩 더한다.

    조각 수가 항목 수보다 크면 항목 수만큼만 만든다.
    """
    parts = max(1, min(parts, total))
    if total <= 0:
        return []
    base, extra = divmod(total, parts)
    return [base + (1 if index < extra else 0) for index in range(parts)]


def auto_parts(total_chars: int, workers: int, max_chars: int) -> int:
    """자동 조각 수: 사용 가능한 워커 수와 '조각 최대 글자 수'로 필요한 수 중 큰 값."""
    return max(1, workers, math.ceil(total_chars / max(1, max_chars)))


def distribute(items: list, parts: int) -> list[list]:
    """항목을 조각에 순서대로 돌아가며 나눈다. 조각 수보다 항목이 적으면 항목 수만큼만 만든다."""
    parts = max(1, min(parts, len(items)))
    groups: list[list] = [[] for _ in range(parts)]
    for index, item in enumerate(items):
        groups[index % parts].append(item)
    return [group for group in groups if group]


def _lines(text: str) -> list[str]:
    return text.splitlines()


def split_lines(text: str, parts: int, overlap: int = 0) -> list[Piece]:
    """줄 단위로 나눈다. overlap이 있으면 첫 조각을 뺀 각 조각 앞에 직전 조각의 마지막 줄들을
    참고 문맥으로 붙인다. 참고 문맥은 처리 대상 범위에 들어가지 않으므로 같은 줄이 두 번 처리되지 않는다.
    """
    lines = _lines(text)
    overlap = max(0, overlap)
    pieces: list[Piece] = []
    start = 0
    for index, size in enumerate(part_sizes(len(lines), parts), start=1):
        end = start + size
        body = lines[start:end]
        if not overlap:
            pieces.append(Piece(index, start + 1, end, "\n".join(body) + "\n"))
        else:
            context_from = max(0, start - overlap)
            context = lines[context_from:start]
            chunks: list[str] = []
            if context:
                chunks += [
                    f"[참고 문맥: {context_from + 1}~{start}줄. 이해에만 쓰고 판정하지 마세요]",
                    *context,
                    "",
                ]
            chunks += [f"[처리 대상: {start + 1}~{end}줄]", *body]
            pieces.append(Piece(
                index, start + 1, end, "\n".join(chunks) + "\n",
                context_start=context_from + 1 if context else None,
                context_end=start if context else None,
            ))
        start = end
    return pieces


def _csv_records(text: str) -> list[str]:
    """CSV를 레코드(행) 단위의 원문 조각으로 나눈다. 따옴표 안의 줄바꿈은 한 행으로 묶는다."""
    lines = text.splitlines(keepends=True)
    records: list[str] = []
    try:
        reader = csv.reader(lines)
        consumed = 0
        for _ in reader:
            records.append("".join(lines[consumed:reader.line_num]))
            consumed = reader.line_num
    except csv.Error:
        # 형식이 깨진 CSV는 물리적인 줄을 한 행으로 본다
        records = lines
    return [record if record.endswith("\n") else record + "\n" for record in records if record.strip()]


def csv_row_count(text: str) -> int:
    """헤더를 뺀 데이터 행 수."""
    return max(0, len(_csv_records(text)) - 1)


def split_csv(text: str, parts: int) -> list[Piece]:
    """CSV 행 단위로 나눈다. 헤더는 모든 조각 맨 위에 붙이고 데이터 행만 나눈다.

    start~end는 헤더를 뺀 데이터 행 번호다.
    """
    records = _csv_records(text)
    if not records:
        return []
    header, rows = records[0], records[1:]
    pieces: list[Piece] = []
    start = 0
    for index, size in enumerate(part_sizes(len(rows), parts), start=1):
        end = start + size
        pieces.append(Piece(index, start + 1, end, header + "".join(rows[start:end])))
        start = end
    return pieces


def _json_items(text: str) -> tuple[list, str | None]:
    """JSON에서 나눌 항목 목록과, 객체 안의 배열이면 그 키를 돌려준다."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise SplitError("split_unsupported", f"JSON 형식이 올바르지 않아 나눌 수 없습니다: {exc}") from exc
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        lists = [key for key, value in data.items() if isinstance(value, list)]
        if len(lists) == 1:
            return data[lists[0]], lists[0]
    raise SplitError(
        "split_unsupported",
        "JSON은 맨 바깥이 배열이거나, 배열 하나를 가진 객체일 때만 항목 단위로 나눌 수 있습니다.",
    )


def split_json(text: str, parts: int) -> list[Piece]:
    """JSON 배열을 항목 단위로 나눈다. 조각마다 같은 모양(배열 또는 {키: 배열})의 JSON 파일이 된다.

    start~end는 1부터 센 항목 번호다.
    """
    items, key = _json_items(text)
    pieces: list[Piece] = []
    start = 0
    for index, size in enumerate(part_sizes(len(items), parts), start=1):
        end = start + size
        chunk = items[start:end]
        body = {key: chunk} if key is not None else chunk
        pieces.append(Piece(index, start + 1, end, json.dumps(body, ensure_ascii=False, indent=2) + "\n"))
        start = end
    return pieces


def unit_count(text: str, unit: str) -> int:
    """나눌 수 있는 항목 수(줄 수, 데이터 행 수, JSON 항목 수)."""
    if unit == "json":
        return len(_json_items(text)[0])
    return csv_row_count(text) if unit == "csv" else len(_lines(text))


def split_text(
    text: str,
    unit: str,
    *,
    parts: int | None,
    workers: int,
    overlap: int = 0,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Piece]:
    """텍스트를 조각으로 나눈다. parts가 None이면 자동으로 정한다.

    자동일 때는 Worker 수와 글자 수로 조각 수를 정한 뒤, 줄 길이가 고르지 않아 어떤 조각이
    '조각 최대 글자 수'를 넘으면 넘지 않을 때까지 조각을 늘린다.
    """
    if unit not in ("line", "csv", "json"):
        raise ValueError(f"지원하지 않는 단위입니다: {unit}")
    overlap = overlap if unit == "line" else 0
    max_chars = min(PIECE_HARD_LIMIT, max(MIN_MAX_CHARS, max_chars))
    total = unit_count(text, unit)
    if total == 0:
        raise SplitError("split_empty", "나눌 내용이 없습니다. 파일이 비어 있습니다.")

    def cut(count: int) -> list[Piece]:
        if unit == "json":
            return split_json(text, count)
        return split_csv(text, count) if unit == "csv" else split_lines(text, count, overlap)

    if parts is not None:
        pieces = cut(min(max(1, parts), MAX_PARTS))
        largest = max(len(piece.text) for piece in pieces)
        if largest > PIECE_HARD_LIMIT:
            raise SplitError(
                "split_too_large",
                f"조각 하나가 {largest:,}자로 워커가 읽을 수 있는 {PIECE_HARD_LIMIT:,}자를 넘습니다. "
                "조각 수를 늘리거나 자동으로 두세요.",
            )
        return pieces

    count = auto_parts(len(text), workers, max_chars)
    limit = min(total, MAX_PARTS)
    if count > MAX_PARTS:
        raise SplitError(
            "split_too_large",
            f"파일이 너무 커서 {count}조각이 필요합니다(최대 {MAX_PARTS}조각). "
            "조각 최대 글자 수를 늘리거나 파일을 줄여 주세요.",
        )
    count = min(count, limit)
    pieces = cut(count)
    while max(len(piece.text) for piece in pieces) > max_chars and count < limit:
        count += 1
        pieces = cut(count)
    largest = max(len(piece.text) for piece in pieces)
    if largest > PIECE_HARD_LIMIT:
        raise SplitError(
            "split_too_large",
            f"최대 {MAX_PARTS}조각으로 나눠도 조각 하나가 {largest:,}자로 워커가 읽을 수 있는 "
            f"{PIECE_HARD_LIMIT:,}자를 넘습니다. 파일을 줄여 주세요.",
        )
    return pieces


def range_label(start: int, end: int, unit: str) -> str:
    """"668~1334줄", "21~40행", "1~50번 항목"처럼 조각의 원본 범위를 표시한다."""
    word = {"csv": "행", "json": "번 항목"}.get(unit, "줄")
    return f"{start}{word}" if start == end else f"{start}~{end}{word}"


def piece_name(original_name: str, index: int, total: int) -> str:
    """조각 파일 이름. 확장자를 유지해 워커가 원본과 같은 방식으로 읽게 한다."""
    path = Path(original_name)
    width = max(2, len(str(total)))
    return f"{path.stem}.part{index:0{width}d}of{total:0{width}d}{path.suffix}"
