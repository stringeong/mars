"""작업 실행기 — 로컬 Ollama로 에이전트 프롬프트를 실행한다."""

import httpx

from . import sandbox

FILE_CONTEXT_LIMIT = 5  # 컨텍스트에 포함할 최대 파일 수


def _build_messages(task: dict, config: dict) -> list[dict]:
    system = task.get("role_prompt") or "당신은 유능한 AI 어시스턴트입니다."
    parts: list[str] = []

    if task.get("input_context"):
        parts.append(task["input_context"])

    # 허용 폴더의 파일 목록/내용을 컨텍스트로 제공 (개인 자료 활용, 로컬 처리)
    folders = task.get("allowed_folders") or []
    if folders:
        files = sandbox.list_files(folders)
        if files:
            listing = "\n".join(f"- {f}" for f in files[:50])
            parts.append(f"[접근 가능한 로컬 파일 목록]\n{listing}")
            snippets = []
            for path in files[:FILE_CONTEXT_LIMIT]:
                try:
                    content = sandbox.read_file(path, folders)
                except sandbox.SandboxError:
                    continue
                snippets.append(f"### {path}\n{content[:4000]}")
            if snippets:
                parts.append("[로컬 파일 내용 발췌]\n" + "\n\n".join(snippets))

    parts.append("위 정보를 바탕으로 당신의 역할을 수행하고 결과만 출력하세요.")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def run_task(task: dict, config: dict) -> str:
    """작업을 실행하고 출력 텍스트를 반환한다. 실패 시 예외."""
    model = task.get("model") or config["default_model"]
    messages = _build_messages(task, config)
    resp = httpx.post(
        f"{config['ollama_url']}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.5},
        },
        timeout=300,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    # qwen3 등 reasoning 모델의 <think> 블록 제거
    if "</think>" in content:
        content = content.split("</think>", 1)[1]
    return content.strip()
