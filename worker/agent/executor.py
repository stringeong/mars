"""작업 실행기 — 로컬 Ollama로 에이전트 프롬프트를 실행한다."""

import json
import os
import re
from pathlib import Path

import httpx

from . import sandbox

FILE_CONTEXT_LIMIT = 10  # 직접 첨부를 우선해 컨텍스트에 포함할 최대 파일 수
FILE_CONTEXT_CHARS = 30_000  # 파일별 최대 입력 길이
FILE_CHUNK_CHARS = 4_000  # 긴 문서는 구간을 나눠 경계를 명확히 표시
PREVIEW_CHARS = 500  # 파일 선별 시 LLM에게 보여줄 미리보기 길이


def _max_output_tokens() -> int:
    """Keep local generations bounded so CPU Workers finish in a practical time."""
    try:
        return max(1, int(os.getenv("MARS_MAX_OUTPUT_TOKENS", "4096")))
    except ValueError:
        return 4096


def _directory_paths(task: dict) -> list[str]:
    """Return server-resolved paths permitted for this task."""
    return task.get("directory_paths") or []


def _uploaded_file_paths(task: dict) -> list[str]:
    """Paths downloaded from the file vault for this specific agent.

    sandbox.list_files가 돌려주는 경로와 같은 모양(심볼릭 링크를 푼 절대 경로)으로 맞춘다.
    macOS는 임시 폴더가 /var -> /private/var 링크라서, 맞추지 않으면 같은 파일이 '올린 파일'과
    '폴더에서 찾은 파일'로 두 번 들어간다.
    """
    return [str(Path(str(path)).expanduser().resolve()) for path in task.get("uploaded_file_paths") or []]


def _chunk_document(path: str, content: str, cut_marker: str = "") -> list[str]:
    """파일 내용을 구간으로 나눈다. 상한에서 잘렸으면 마지막 구간 끝에 cut_marker를 붙여 모델도 알게 한다."""
    content = content[:FILE_CONTEXT_CHARS]
    total = max(1, -(-len(content) // FILE_CHUNK_CHARS))
    chunks = [
        f"### {path} (part {index + 1}/{total})\n"
        + content[start : start + FILE_CHUNK_CHARS]
        for index, start in enumerate(range(0, len(content), FILE_CHUNK_CHARS))
    ]
    if cut_marker and chunks:
        chunks[-1] += f"\n{cut_marker}"
    return chunks


def _display_name(path: str, uploaded: set[str]) -> str:
    """사용자에게 보여줄 파일 이름. 올린 파일은 내려받을 때 붙인 '파일id_'를 뗀다."""
    name = Path(path).name
    return re.sub(r"^\d+_", "", name) if path in uploaded else name


def _cut_texts(name: str, total: int, exact: bool) -> tuple[str, str]:
    """파일이 상한에서 잘렸을 때 (프롬프트에 넣을 표시, 실행 기록에 남길 안내)."""
    used = FILE_CONTEXT_CHARS
    if exact:
        return (
            f"[여기까지만 포함됨: 전체 {total:,}자 중 앞 {used:,}자. 이후 {total - used:,}자는 생략됨]",
            f"{name}: 전체 {total:,}자 중 앞 {used:,}자만 읽었어요. 뒤 {total - used:,}자는 빠졌어요.",
        )
    return (
        f"[여기까지만 포함됨: 전체 {total:,}자 이상 중 앞 {used:,}자. 이후는 생략됨]",
        f"{name}: {total:,}자가 넘는 파일이라 앞 {used:,}자만 읽었어요. 나머지는 빠졌어요.",
    )


_MIN_CONTEXT_TOKENS = 8192


def _max_context_tokens() -> int:
    """한 번에 쓸 최대 문맥 길이. 문맥이 길수록 Ollama가 메모리를 더 쓰므로 기기에 맞게 줄일 수 있다."""
    try:
        return max(_MIN_CONTEXT_TOKENS, int(os.getenv("MARS_MAX_CONTEXT", "32768")))
    except ValueError:
        return 32768


_MODEL_LIMITS: dict[tuple[str, str], int] = {}


def model_context_limit(config: dict, model: str) -> int | None:
    """모델이 한 번에 읽을 수 있는 최대 토큰 수(Ollama /api/show). 알 수 없으면 None.

    모델 한계보다 큰 num_ctx를 보내면 Ollama가 말없이 줄이므로, 보내기 전에 한계를 알아 둔다.
    """
    key = (config["ollama_url"], model)
    if key not in _MODEL_LIMITS:
        try:
            resp = httpx.post(f"{config['ollama_url']}/api/show", json={"model": model}, timeout=15)
            resp.raise_for_status()
            info = resp.json().get("model_info") or {}
            limits = [
                value for name, value in info.items()
                if name.endswith(".context_length") and isinstance(value, int) and value > 0
            ]
        except Exception:
            limits = []
        if not limits:
            return None
        _MODEL_LIMITS[key] = min(limits)
    return _MODEL_LIMITS[key]


def _context_limit(model_limit: int | None) -> int:
    """이 요청에 쓸 수 있는 문맥 상한: 기기 설정(MARS_MAX_CONTEXT)과 모델 한계 중 작은 값."""
    limit = _max_context_tokens()
    return min(limit, model_limit) if model_limit else limit


def _round_up(tokens: int) -> int:
    return -(-tokens // 1024) * 1024


def context_tokens(messages: list[dict], model_limit: int | None = None) -> int:
    """이번 요청에 필요한 문맥 길이(num_ctx).

    지정하지 않으면 Ollama 기본값(4096 등)으로 떠서 긴 입력의 앞부분을 말없이 잘라 버린다.
    로그·CSV처럼 숫자가 많은 글은 글자 하나가 토큰 하나 가까이 되므로 글자 수를 그대로 토큰 수로 잡는다.
    """
    estimate = sum(len(str(message.get("content") or "")) for message in messages)
    # num_ctx는 입력과 출력을 함께 담는다. 로컬 출력 상한만큼 답변 공간을 예약한다.
    rounded = _round_up(estimate + _max_output_tokens())
    limit = _context_limit(model_limit)
    if estimate > limit:
        print(f"  입력이 커서 문맥 상한({limit:,}토큰)을 넘을 수 있습니다: 약 {estimate:,}자")
    return min(max(_MIN_CONTEXT_TOKENS, rounded), limit)


_OVERFLOW = re.compile(r"request \((\d+) tokens\) exceeds the available context size")


def _chat(
    config: dict, model: str, messages: list[dict], temperature: float,
    response_format: str | None = None, notes: list[str] | None = None,
) -> str:
    """Ollama에 한 번 묻는다. 입력이 문맥보다 길어 잘린 채 실행되면 notes에 안내를 남긴다."""
    model_limit = model_context_limit(config, model)
    num_ctx = context_tokens(messages, model_limit)
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        # Ollama는 문맥을 넘는 입력을 말없이 절반으로 잘라 버린다. 자르지 말고 거절하게 해서 넘침을 알아챈다
        "truncate": False,
        "options": {"temperature": temperature, "num_predict": _max_output_tokens(), "num_ctx": num_ctx},
    }
    if response_format:
        payload["format"] = response_format
    url = f"{config['ollama_url']}/api/chat"
    resp = httpx.post(url, json=payload, timeout=300)
    if resp.status_code == 400:
        # 거절 사유에 실제 토큰 수가 들어 있다. 글자 수 어림이 모자랐던 것이면 문맥을 늘려 다시 보내고,
        # 상한으로도 모자라면 예전처럼 잘린 채로 실행하되 그 사실을 남긴다
        match = _OVERFLOW.search(resp.text)
        tokens = int(match.group(1)) if match else None
        if tokens is not None:
            num_ctx = min(_round_up(tokens + _max_output_tokens()), _context_limit(model_limit))
            payload["options"]["num_ctx"] = num_ctx
        del payload["truncate"]
        resp = httpx.post(url, json=payload, timeout=300)
        if resp.status_code == 200 and (tokens is None or tokens > num_ctx):
            size = f"입력이 {tokens:,}토큰인데" if tokens else "입력이 너무 길어서,"
            note = f"{size} 이 워커는 한 번에 {num_ctx:,}토큰까지만 읽을 수 있어요. 입력 앞부분이 빠진 채 실행됐어요."
            print(f"  [WARN] {note}")
            if notes is not None:
                notes.append(note)
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    # qwen3 등 reasoning 모델의 <think> 블록 제거
    if "</think>" in content:
        content = content.split("</think>", 1)[1]
    return content.strip()


def generate_workflow_reply(config: dict, job: dict) -> str:
    """서버가 맡긴 워크플로우 생성 요청을 이 기기의 Ollama로 처리하고 JSON 응답 텍스트를 돌려준다.

    응답 해석과 구성 검증은 서버가 한다.
    """
    model = job.get("model") or config.get("default_model", "")
    messages = [
        {"role": "system", "content": job["system"]},
        {"role": "user", "content": job["prompt"]},
    ]
    return _chat(config, model, messages, float(job.get("temperature", 0.3)), response_format="json")


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
            head = sandbox.read_file(path, _directory_paths(task))[:PREVIEW_CHARS]
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


def _build_messages(task: dict, config: dict, notes: list[str] | None = None) -> list[dict]:
    """프롬프트를 조립한다. 파일을 끝까지 넣지 못했으면 그 사실을 프롬프트와 notes 양쪽에 남긴다."""
    notes = notes if notes is not None else []
    system = task.get("role_prompt") or "당신은 유능한 AI 어시스턴트입니다."
    parts: list[str] = []

    if task.get("input_context"):
        parts.append(task["input_context"])

    # 허용 폴더의 파일을 컨텍스트로 제공 (개인 자료 활용, 로컬 처리)
    # 단, 작업과 관련된 파일만 선별해 무관한 개인정보 유입을 막는다
    folders = _directory_paths(task)
    if folders:
        uploaded = _uploaded_file_paths(task)
        uploaded_set = set(uploaded)
        shared_files = [
            path for path in sandbox.list_files(folders) if path not in uploaded_set
        ]
        relevant_shared = (
            _select_relevant_files(task, shared_files, config) if shared_files else []
        )
        ordered_files = list(dict.fromkeys([*uploaded, *relevant_shared]))
        selected_files = ordered_files[:FILE_CONTEXT_LIMIT]
        dropped = ordered_files[FILE_CONTEXT_LIMIT:]
        if dropped:
            names = ", ".join(_display_name(path, uploaded_set) for path in dropped[:5])
            more = f" 외 {len(dropped) - 5}개" if len(dropped) > 5 else ""
            notes.append(
                f"파일 {len(ordered_files)}개 중 {FILE_CONTEXT_LIMIT}개만 읽었어요. 빠진 파일: {names}{more}"
            )
        if selected_files:
            listing = "\n".join(
                f"- {path}{' (direct upload)' if path in uploaded_set else ''}"
                for path in selected_files
            )
            parts.append(f"[이 작업에 사용할 파일 목록]\n{listing}")
            snippets = []
            errors = []
            for path in selected_files:
                try:
                    content = sandbox.read_file(path, folders)
                except sandbox.SandboxError as exc:
                    errors.append(f"- {path}: {exc}")
                    notes.append(f"{_display_name(path, uploaded_set)}: 읽지 못했어요. {exc}")
                    continue
                cut_marker = ""
                if len(content) > FILE_CONTEXT_CHARS:
                    total, exact = sandbox.full_length(path, content)
                    cut_marker, note = _cut_texts(_display_name(path, uploaded_set), total, exact)
                    notes.append(note)
                snippets.extend(_chunk_document(path, content, cut_marker))
            if snippets:
                parts.append("[파일 내용]\n" + "\n\n".join(snippets))
            if errors:
                parts.append("[읽지 못한 파일]\n" + "\n".join(errors))

    parts.append("위 정보를 바탕으로 당신의 역할을 수행하고 결과만 출력하세요.")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def run_task(task: dict, config: dict, notes: list[str] | None = None) -> str:
    """작업을 실행하고 출력 텍스트를 반환한다. 실패 시 예외.

    notes를 주면 입력이 빠진 채 실행된 사정(파일 잘림, 문맥 넘침)을 사람이 읽을 문장으로 담아 준다.
    """
    model = task.get("model") or config["default_model"]
    messages = _build_messages(task, config, notes)
    return _chat(config, model, messages, temperature=0.5, notes=notes)
