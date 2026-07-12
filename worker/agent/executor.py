"""작업 실행기 — 로컬 Ollama로 에이전트 프롬프트를 실행한다."""

import json
import re

import httpx

from . import sandbox

FILE_CONTEXT_LIMIT = 5  # 컨텍스트에 포함할 최대 파일 수
PREVIEW_CHARS = 200  # 파일 선별 시 LLM에게 보여줄 미리보기 길이


def _chat(config: dict, model: str, messages: list[dict], temperature: float) -> str:
    resp = httpx.post(
        f"{config['ollama_url']}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=300,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    # qwen3 등 reasoning 모델의 <think> 블록 제거
    if "</think>" in content:
        content = content.split("</think>", 1)[1]
    return content.strip()


def _select_relevant_files(task: dict, files: list[str], config: dict) -> list[str]:
    """작업과 관련된 파일만 LLM으로 선별한다 (컨텍스트 오염 방지).

    허용 폴더에는 서로 무관한 개인 파일이 섞여 있을 수 있다(예: 이력서와 여행 메모).
    무엇이든 전부 프롬프트에 넣으면 무관한 개인정보가 결과물에 새어 들어가므로,
    본 작업 전에 파일 이름+미리보기만 보고 필요한 파일을 고르게 한다.
    선별도 로컬 LLM에서 수행하므로 파일 내용이 기기 밖으로 나가지 않는 원칙은 유지된다.
    실패 시에는 기존 동작(전체 포함)으로 폴백한다.
    """
    if len(files) <= 1:
        return files

    previews = []
    for path in files[:20]:
        try:
            head = sandbox.read_file(path, task.get("allowed_folders") or [])[:PREVIEW_CHARS]
        except sandbox.SandboxError:
            continue
        previews.append(f"- {path}\n  미리보기: {head!r}")
    if not previews:
        return files

    task_desc = "\n".join(
        p for p in [task.get("role_prompt", ""), task.get("run_prompt", "")] if p
    )
    system = (
        "당신은 파일 선별 담당입니다. 작업 설명과 파일 목록(미리보기 포함)을 보고, "
        "이 작업을 수행하는 데 반드시 필요한 파일의 경로만 고르세요.\n"
        "규칙:\n"
        "- 작업 설명에 직접 관련된 파일만 포함한다.\n"
        "- 관련성이 애매하거나 확실하지 않은 파일은 무조건 제외한다. "
        "(무관한 개인 파일이 결과물에 섞이는 것이 파일 하나를 빠뜨리는 것보다 훨씬 나쁘다)\n"
        "- 아무 파일도 필요 없으면 빈 배열을 출력한다.\n"
        '반드시 {"files": ["경로1", ...]} 형식의 JSON만 출력하세요.'
    )
    user = f"[작업 설명]\n{task_desc}\n\n[파일 목록]\n" + "\n".join(previews)
    try:
        content = _chat(config, config["default_model"], [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], temperature=0.0)
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        selected = json.loads(match.group(0))["files"]
        # LLM이 지어낸 경로가 섞이지 않도록 실제 목록과 교집합만 사용
        valid = [f for f in files if f in set(map(str, selected))]
        print(f"  파일 선별: {len(files)}개 중 {len(valid)}개 사용 {valid}")
        return valid
    except Exception as e:
        print(f"  파일 선별 실패(전체 포함으로 폴백): {e}")
        return files


def _build_messages(task: dict, config: dict) -> list[dict]:
    system = task.get("role_prompt") or "당신은 유능한 AI 어시스턴트입니다."
    parts: list[str] = []

    if task.get("input_context"):
        parts.append(task["input_context"])

    # 허용 폴더의 파일을 컨텍스트로 제공 (개인 자료 활용, 로컬 처리)
    # 단, 작업과 관련된 파일만 선별해 무관한 개인정보 유입을 막는다
    folders = task.get("allowed_folders") or []
    if folders:
        files = sandbox.list_files(folders)
        relevant = _select_relevant_files(task, files, config) if files else []
        if relevant:
            listing = "\n".join(f"- {f}" for f in relevant[:50])
            parts.append(f"[이 작업에 사용할 로컬 파일 목록]\n{listing}")
            snippets = []
            for path in relevant[:FILE_CONTEXT_LIMIT]:
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
    return _chat(config, model, messages, temperature=0.5)
