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


# 홈 폴더처럼 큰 경로가 허용되어도 순회 폭주하지 않도록 건너뛰는 디렉터리
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    "Library", "Applications", ".Trash", ".cache", "AppData",
}
MAX_DIRS_VISITED = 2_000  # 순회할 디렉터리 수 상한 (안전장치)


def list_files(allowed_folders: list[str], max_entries: int = 200) -> list[str]:
    """허용 폴더 내 텍스트 파일 목록 (에이전트 컨텍스트 제공용).

    rglob 전체 순회 대신 디렉터리 단위로 돌면서 상한에 도달하면 즉시 멈춘다 —
    사용자가 홈 폴더처럼 큰 경로를 허용해도 워커가 몇 분씩 멈추지 않는다.
    """
    entries: list[str] = []
    visited = 0
    for base in _normalize(allowed_folders):
        if not base.is_dir():
            continue
        stack = [base]
        while stack:
            if len(entries) >= max_entries or visited >= MAX_DIRS_VISITED:
                return entries
            current = stack.pop()
            visited += 1
            try:
                children = sorted(current.iterdir())
            except (PermissionError, OSError):
                continue
            for p in children:
                if p.name.startswith(".") or p.name in SKIP_DIRS:
                    continue
                if p.is_dir():
                    stack.append(p)
                elif p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS:
                    entries.append(str(p))
                    if len(entries) >= max_entries:
                        return entries
    return entries
