"""Safe text extraction for files explicitly attached to cloud nodes."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from .. import models
from ..config import UPLOAD_DIR

MAX_FILE_CHARS = 30_000
MAX_FILES = 10


class CloudFileError(ValueError):
    pass


@dataclass(frozen=True)
class FileText:
    """파일에서 뽑은 글. text는 상한(MAX_FILE_CHARS)까지만 담고, total은 원본 전체 글자 수다.

    exact가 False면 끝까지 세지 않고 멈춘 것이라 total은 '이 값 이상'이다.
    """

    text: str
    total: int
    exact: bool = True

    @property
    def cut(self) -> bool:
        return self.total > len(self.text) or not self.exact


def _joined(parts: list[str], exact: bool = True) -> FileText:
    full = "\n".join(parts)
    return FileText(full[:MAX_FILE_CHARS], len(full), exact)


def cut_marker(text: FileText) -> str:
    """잘린 파일 끝에 붙여 모델도 뒷부분이 없다는 것을 알게 하는 표시."""
    used = len(text.text)
    if text.exact:
        return f"[여기까지만 포함됨: 전체 {text.total:,}자 중 앞 {used:,}자. 이후 {text.total - used:,}자는 생략됨]"
    return f"[여기까지만 포함됨: 전체 {text.total:,}자 이상 중 앞 {used:,}자. 이후는 생략됨]"


def cut_note(name: str, text: FileText) -> str:
    """실행 기록에 남겨 사용자가 보는 안내."""
    used = len(text.text)
    if text.exact:
        return f"{name}: 전체 {text.total:,}자 중 앞 {used:,}자만 읽었어요. 뒤 {text.total - used:,}자는 빠졌어요."
    return f"{name}: {text.total:,}자가 넘는 파일이라 앞 {used:,}자만 읽었어요. 나머지는 빠졌어요."


def read_file_text(path: Path) -> FileText:
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader

            return _joined([(page.extract_text() or "") for page in PdfReader(str(path)).pages])
        if suffix == ".docx":
            from docx import Document

            document = Document(str(path))
            parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
            for table in document.tables:
                parts.extend(" | ".join(cell.text for cell in row.cells) for row in table.rows)
            return _joined(parts)
        if suffix == ".xlsx":
            from openpyxl import load_workbook

            workbook = load_workbook(str(path), read_only=True, data_only=True)
            parts: list[str] = []
            stopped_early = False
            for worksheet in workbook.worksheets[:10]:
                parts.append(f"[Sheet: {worksheet.title}]")
                for row in worksheet.iter_rows(values_only=True):
                    values = [str(value) for value in row if value is not None]
                    if values:
                        parts.append(" | ".join(values))
                    if sum(map(len, parts)) >= MAX_FILE_CHARS:
                        stopped_early = True
                        break
            return _joined(parts, exact=not stopped_early)
        if suffix == ".pptx":
            from pptx import Presentation

            parts = []
            for index, slide in enumerate(Presentation(str(path)).slides, start=1):
                parts.append(f"[Slide {index}]")
                parts.extend(
                    shape.text for shape in slide.shapes
                    if getattr(shape, "has_text_frame", False) and shape.text
                )
            return _joined(parts)
        # 바이트가 아니라 글자 수로 자른다 (한글은 한 글자가 3바이트라 바이트로 자르면 1/3만 남는다)
        full = path.read_bytes().decode("utf-8", errors="replace")
        return FileText(full[:MAX_FILE_CHARS], len(full))
    except Exception as exc:
        raise CloudFileError(f"Cannot extract text from {path.name}: {type(exc).__name__}") from exc


@lru_cache(maxsize=64)
def _measured(path: str, modified_ns: int, size: int) -> FileText:
    return read_file_text(Path(path))


def measure_upload(uploaded: models.UploadedFile) -> FileText | None:
    """업로드 파일을 블록이 읽을 때 얼마나 들어가는지 미리 잰다(실행 전 검사용). 읽을 수 없으면 None.

    검사는 화면에서 자주 불리므로 같은 파일은 다시 읽지 않는다.
    """
    path = UPLOAD_DIR / uploaded.stored_name
    try:
        stat = path.stat()
        return _measured(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, CloudFileError):
        return None


def cloud_file_context(db: Session, user_id: int, node: dict, notes: list[str] | None = None) -> str:
    """클라우드 블록에 붙은 파일의 글. 상한에서 잘린 파일은 글 끝에 표시하고 notes에 안내를 남긴다."""
    file_ids = [value for value in node.get("uploaded_file_ids", []) if isinstance(value, int)]
    if not file_ids:
        return ""
    if len(file_ids) > MAX_FILES:
        raise CloudFileError(f"Cloud nodes support at most {MAX_FILES} attached files.")
    rows = db.query(models.UploadedFile).filter(
        models.UploadedFile.user_id == user_id,
        models.UploadedFile.id.in_(file_ids),
    ).all()
    by_id = {row.id: row for row in rows}
    parts = []
    for file_id in file_ids:
        uploaded = by_id.get(file_id)
        if uploaded is None:
            raise CloudFileError(f"Attached file {file_id} is unavailable.")
        path = UPLOAD_DIR / uploaded.stored_name
        if not path.is_file():
            raise CloudFileError(f"Stored file {uploaded.original_name} is unavailable.")
        extracted = read_file_text(path)
        content = extracted.text
        if not content.strip():
            raise CloudFileError(f"No extractable text in {uploaded.original_name}.")
        if extracted.cut:
            content = f"{content}\n{cut_marker(extracted)}"
            if notes is not None:
                notes.append(cut_note(uploaded.original_name, extracted))
        parts.append(f"[Attached file text: {uploaded.original_name}]\n{content}")
    return "\n\n".join(parts)
