"""폴더 화이트리스트 강제 (최소 권한 원칙, 요구사항 2.4/2.5).

서버가 어떤 경로를 지시하더라도 여기서 검증을 통과하지 못하면 접근을 거부한다.
"""

from pathlib import Path

MAX_FILE_BYTES = 200_000  # 파일당 읽기 상한 (프롬프트 폭주 방지)
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log", ".py", ".html"}


class SandboxError(PermissionError):
    pass


def _normalize(folders: list[str]) -> list[Path]:
    result = []
    for f in folders:
        try:
            result.append(Path(f).expanduser().resolve())
        except OSError:
            continue
    return result


def is_allowed(path: str | Path, allowed_folders: list[str]) -> bool:
    try:
        target = Path(path).expanduser().resolve()
    except OSError:
        return False
    for base in _normalize(allowed_folders):
        if target == base or base in target.parents:
            return True
    return False


def read_file(path: str, allowed_folders: list[str]) -> str:
    if not is_allowed(path, allowed_folders):
        raise SandboxError(f"허용된 폴더 밖의 경로입니다: {path}")
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise SandboxError(f"파일이 아닙니다: {path}")
    data = p.read_bytes()[:MAX_FILE_BYTES]
    return data.decode("utf-8", errors="replace")


def list_files(allowed_folders: list[str], max_entries: int = 200) -> list[str]:
    """허용 폴더 내 텍스트 파일 목록 (에이전트 컨텍스트 제공용)."""
    entries: list[str] = []
    for base in _normalize(allowed_folders):
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS:
                entries.append(str(p))
                if len(entries) >= max_entries:
                    return entries
    return entries
