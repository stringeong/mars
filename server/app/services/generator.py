"""자연어 생성 프롬프트 -> MAS 워크플로우(DAG) 생성.

사용자가 고른 생성 모델(서버 로컬 Ollama, 등록된 외부 LLM API, 또는 사용자의 Worker)에 JSON
스키마로 요청한다. Worker 생성은 generation_jobs 대기열을 거쳐 같은 응답 해석 규칙(graph_from_reply)을 쓴다.
실패하면 원인(연결 실패, 응답 파싱 실패, 구성 검증 실패)을 GenerationError로 알린다.
규칙 기반 기본 워크플로우는 사용자가 고른 경우에만 만든다.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from ..config import DEFAULT_MODEL, OLLAMA_URL

logger = logging.getLogger(__name__)

# Stay within the 60-second reverse-proxy response window.
OLLAMA_TIMEOUT = httpx.Timeout(25.0, connect=3.0)
# 외부 LLM 생성도 같은 프록시 응답 시간 안에 끝나야 한다 (실행용 클라우드 호출은 120초)
CLOUD_GENERATION_TIMEOUT = httpx.Timeout(45.0, connect=5.0)

SYSTEM_PROMPT = """당신은 Multi-Agent System(MAS) 설계 전문가입니다.
사용자가 만들고 싶은 서비스 설명을 읽고, 이를 수행할 에이전트 구성과 실행 순서(DAG)를 설계하세요.

규칙:
- 에이전트는 2~6개. 각 에이전트는 한 가지 역할만 담당한다.
- edges는 방향성 비순환 그래프(DAG)여야 한다.
- 서로의 결과를 기다릴 필요가 없는 작업은 병렬로 나눈다. 같은 입력을 여러 관점에서
  보거나(예: 지출 분류와 이상 거래 탐지, 일정 짜기와 예산 계산), 여러 자료를 각각
  처리하는 경우가 그렇다. 나뉜 가지는 마지막 종합 에이전트에서 다시 합친다.
  앞 결과가 꼭 있어야 하는 단계만 일렬로 잇는다.
- 연결은 반드시 앞 단계에서 뒤 단계로 한 방향으로만 흐른다. 검토·첨삭·개선처럼
  앞 단계 결과를 다듬는 작업도 뒤에 새 에이전트를 두어 처리하고, 이전 에이전트로
  되돌아가는 연결(피드백 루프)은 절대 만들지 않는다.
- 결과를 종합하는 최종 에이전트는 정확히 1개이며 "final": true로 표시한다.
  다른 모든 에이전트의 결과는 연결을 따라 최종 에이전트에 도달해야 한다.
- 실행할 때 사용자 파일(예: 거래 내역 CSV, 보고서 PDF)을 직접 읽어야 하는 에이전트는
  "needs_file": true로 표시하고 "file_description"(어떤 내용의 파일인지)과
  "file_format"(형식과 예상 열 구성)을 적는다. 앞 단계 결과만 읽는 에이전트는 false로 둔다.
- 같은 파일을 여러 에이전트가 함께 읽으면 같은 "file_key"를 쓴다.
  예: 거래 분류와 이상 거래 탐지가 같은 신용카드 내역을 읽으면 둘 다 "credit_card".
- role_prompt는 해당 에이전트에게 줄 시스템 프롬프트로, 한국어로 구체적으로 작성한다.
- "name"은 이 워크플로우가 하는 일을 6~20자 한국어로 요약한 이름이다.
  예: "월간 카드 지출 리포트", "회의록 할 일 정리". "새 서비스", "서비스 이름"처럼
  일반적인 말이나 아래 예시의 이름을 그대로 쓰지 않는다. 에이전트 이름도 맡은 일이
  드러나게 짓는다(예: "이상 거래 탐지 에이전트").
- 반드시 아래 JSON 형식만 출력한다. 다른 텍스트는 출력하지 않는다.
  아래는 형식 예시일 뿐이므로 에이전트 수와 연결은 요청에 맞게 정한다.

{
  "name": "월간 카드 지출 리포트",
  "description": "카드 내역을 분류하고 이상 거래를 찾아 월간 리포트로 정리한다",
  "nodes": [
    {"id": "agent1", "name": "지출 분류 에이전트", "role_prompt": "...",
     "needs_file": true, "file_key": "credit_card",
     "file_description": "신용카드 사용 내역",
     "file_format": "CSV, 열: 거래ID, 일시, 거래처, 금액"},
    {"id": "agent2", "name": "이상 거래 탐지 에이전트", "role_prompt": "...",
     "needs_file": true, "file_key": "credit_card",
     "file_description": "신용카드 사용 내역",
     "file_format": "CSV, 열: 거래ID, 일시, 거래처, 금액"},
    {"id": "agent3", "name": "리포트 작성 에이전트", "role_prompt": "...",
     "needs_file": false, "final": true}
  ],
  "edges": [
    {"source": "agent1", "target": "agent3"},
    {"source": "agent2", "target": "agent3"}
  ]
}"""

# 모델이 이름을 비우거나 예시 문구를 그대로 내면 요청 문장에서 이름을 만든다
PLACEHOLDER_NAMES = {"새 서비스", "서비스 이름", "서비스", "워크플로우", "월간 카드 지출 리포트"}


def name_from_prompt(prompt: str, limit: int = 24) -> str:
    """요청 문장의 앞부분을 어절 단위로 잘라 워크플로우 이름으로 쓴다."""
    text = re.sub(r"\s+", " ", prompt.strip())
    if not text:
        return "새 워크플로우"
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] if " " in text[:limit] else text[:limit]
    return cut.rstrip(",. ") + "…"


@dataclass(frozen=True)
class GeneratorChoice:
    """워크플로우를 생성할 LLM. location: local(서버 Ollama) | cloud(등록된 외부 LLM API) | worker(사용자 Worker)."""

    location: str = "local"
    provider: str = "ollama"
    model: str = ""
    api_key: str = field(default="", repr=False)
    device_name: str = ""

    @property
    def resolved_model(self) -> str:
        return self.model or (DEFAULT_MODEL if self.location == "local" else "")


class GenerationError(RuntimeError):
    """사용자가 고른 모델로 워크플로우를 만들지 못했다. stage: connection | parse | validation"""

    def __init__(self, stage: str, message: str, choice: GeneratorChoice):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.choice = choice

    def detail(self) -> dict:
        return {
            "stage": self.stage,
            "message": self.message,
            "location": self.choice.location,
            "provider": self.choice.provider,
            "model": self.choice.resolved_model,
        }


def _extract_json(text: str) -> dict:
    """LLM 출력에서 첫 JSON 오브젝트를 추출한다."""
    # <think>...</think> 등 추론 블록 제거
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("JSON을 찾을 수 없음")
    return json.loads(match.group(0))


def _fallback_graph(prompt: str) -> dict:
    """LLM을 사용할 수 없을 때의 규칙 기반 3단계 워크플로우.

    생성 프롬프트는 역할 프롬프트에 붙이지 않고 goal로 두어 시작 블록 컨텍스트로만 전달한다.
    """
    return {
        "name": name_from_prompt(prompt),
        "description": prompt.strip(),
        "goal": prompt.strip(),
        "nodes": [
            {
                "id": "collector",
                "name": "정보 수집 에이전트",
                "role_prompt": (
                    "당신은 정보 수집 담당입니다. 서비스 목표와 사용자의 요청, 제공된 자료를 바탕으로 "
                    "필요한 정보를 항목별로 정리해 나열하세요."
                ),
            },
            {
                "id": "analyzer",
                "name": "분석 에이전트",
                "role_prompt": (
                    "당신은 분석 담당입니다. 이전 단계에서 수집된 정보를 비교·분석하고 "
                    "핵심 인사이트를 도출하세요."
                ),
            },
            {
                "id": "writer",
                "name": "정리 에이전트",
                "role_prompt": (
                    "당신은 최종 보고 담당입니다. 앞선 분석 결과를 사용자가 읽기 쉬운 "
                    "구조화된 최종 결과물로 정리하세요."
                ),
            },
        ],
        "edges": [
            {"source": "collector", "target": "analyzer"},
            {"source": "analyzer", "target": "writer"},
        ],
    }


def _truthy(value) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _agent_node(node: dict, index: int) -> dict:
    """Return the canonical shape expected by the API and web editor."""
    return {
        "id": str(node.get("id") or f"agent{index}"),
        "type": "agent",
        "name": node.get("name") or f"에이전트 {index + 1}",
        "role_prompt": node.get("role_prompt") or "",
        "model": node.get("model") or "",
        "worker_id": node.get("worker_id"),
        "directory_ids": node.get("directory_ids") or [],
        "uploaded_file_ids": node.get("uploaded_file_ids") or [],
        "final": _truthy(node.get("final")),
        "needs_file": _truthy(node.get("needs_file")),
        # 생성기가 정한 값은 hint로 보관하고, 실제 값은 dag.apply_auto_flags가 정한다
        "final_hint": _truthy(node.get("final_hint", node.get("final"))),
        "needs_file_hint": _truthy(node.get("needs_file_hint", node.get("needs_file"))),
        "final_manual": bool(node.get("final_manual")),
        "needs_file_manual": bool(node.get("needs_file_manual")),
        "input_slot_ids": list(node.get("input_slot_ids") or []),
        "text_input_enabled": bool(node.get("text_input_enabled")),
        "text_input": str(node.get("text_input") or ""),
        **({"position": node["position"]} if node.get("position") is not None else {}),
    }


def _input_slots(raw_nodes: list[dict], nodes: list[dict]) -> list[dict]:
    """needs_file 블록의 파일 안내를 슬롯으로 묶는다. 같은 file_key를 쓰는 블록은 한 슬롯을 함께 읽는다.

    생성기가 설명을 주지 않은 블록(들어오는 연결이 없어 자동으로 파일이 필요해진 블록 등)은
    "〈블록 이름〉 입력 파일" 슬롯을 받는다.
    """
    slots: dict[str, dict] = {}
    first_names: dict[str, str] = {}
    for raw, node in zip(raw_nodes, nodes):
        if not node["needs_file"]:
            continue
        key = str(raw.get("file_key") or raw.get("file_description") or node["id"]).strip()
        slot = slots.setdefault(key, {
            "id": f"slot{len(slots) + 1}",
            "description": "",
            "format": "",
            "file_ids": [],
            "directory_ids": [],
        })
        first_names.setdefault(slot["id"], node["name"])
        slot["description"] = slot["description"] or str(raw.get("file_description") or "").strip()
        slot["format"] = slot["format"] or str(raw.get("file_format") or "").strip()
        node["input_slot_ids"] = [slot["id"]]
    for slot in slots.values():
        slot["description"] = slot["description"] or f"{first_names[slot['id']]} 입력 파일"
    return list(slots.values())


def _workflow_edge(edge: dict) -> dict:
    """Return the canonical workflow-edge shape."""
    return {
        "source": str(edge["source"]),
        "target": str(edge["target"]),
        "relation": "workflow",
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _chat(choice: GeneratorChoice, system: str, user: str, temperature: float) -> tuple[str, dict]:
    """고른 생성 모델에 한 번 묻고 (응답 텍스트, 토큰 사용량)을 돌려준다."""
    if choice.location == "cloud":
        from .cloud_executor import _call

        return await asyncio.to_thread(
            _call, choice.provider, choice.api_key, choice.resolved_model, system, user, CLOUD_GENERATION_TIMEOUT
        )
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": choice.resolved_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": temperature},
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"], {}


async def _generate_once(prompt: str, choice: GeneratorChoice, temperature: float) -> tuple[dict, dict]:
    """LLM을 1회 호출해 그래프를 만들고 DAG 검증까지 통과시킨다. 실패 시 예외."""
    content, usage = await _chat(choice, SYSTEM_PROMPT, prompt, temperature)
    return graph_from_reply(content, prompt), usage


def _workflow_name(name: object, prompt: str) -> str:
    text = str(name or "").strip()
    return name_from_prompt(prompt) if not text or text in PLACEHOLDER_NAMES else text


def graph_from_reply(content: str, prompt: str) -> dict:
    """LLM 응답 텍스트를 실행 가능한 워크플로우 그래프로 바꾼다.

    해석하지 못하면 ValueError/KeyError/TypeError, 실행할 수 없는 구성이면 dag.DagError.
    """
    from . import dag

    data = _extract_json(content)
    raw_nodes = data.get("nodes") or []
    if not raw_nodes:
        raise ValueError("에이전트가 비어 있음")
    graph = {
        "name": _workflow_name(data.get("name"), prompt),
        "description": data.get("description") or prompt,
        "nodes": [_agent_node(n, i) for i, n in enumerate(raw_nodes)],
        "edges": [
            _workflow_edge(e)
            for e in (data.get("edges") or [])
            if e.get("source") and e.get("target")
        ],
    }
    # LLM이 순환 그래프 등 실행 불가능한 구성을 제안하면 여기서 예외 발생
    dag.validate_graph(graph)
    # 최종 블록은 정확히 하나로, 들어오는 연결이 없는 블록은 파일 필요로 맞춘 뒤 슬롯을 만든다
    graph = dag.apply_auto_flags(graph)
    graph["input_slots"] = _input_slots(raw_nodes, graph["nodes"])
    return graph


def reply_error(exc: Exception, choice: GeneratorChoice) -> GenerationError:
    """graph_from_reply의 실패를 사용자에게 보여줄 원인으로 바꾼다."""
    from . import dag

    if isinstance(exc, dag.DagError):
        return GenerationError("validation", f"생성된 구성을 실행할 수 없습니다: {exc}", choice)
    return GenerationError("parse", f"모델 응답을 워크플로우로 해석하지 못했습니다: {exc}", choice)


# 1회차 온도와, 응답을 해석하지 못했을 때 다시 묻는 2회차 온도
GENERATION_TEMPERATURES = (0.3, 0.1)


def _connection_message(exc: httpx.HTTPError, choice: GeneratorChoice) -> str:
    where = "서버 로컬 LLM(Ollama)" if choice.location == "local" else f"외부 LLM API({choice.provider})"
    if isinstance(exc, httpx.TimeoutException):
        return f"{where} 응답 시간이 초과되었습니다."
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            reason = exc.response.json().get("error")
            reason = reason.get("message") if isinstance(reason, dict) else reason
        except (ValueError, AttributeError):
            reason = None
        suffix = f": {str(reason)[:200]}" if reason else ""
        return f"{where}가 {exc.response.status_code} 오류를 반환했습니다{suffix}"
    return f"{where}에 연결할 수 없습니다. 실행 상태와 네트워크를 확인해 주세요."


async def generate_workflow(prompt: str, choice: GeneratorChoice | None = None) -> tuple[dict, dict]:
    """(graph_dict, generation_info) 반환.

    LLM 출력이 잘못되면(JSON 파싱 실패, 순환 그래프 등) 온도를 낮춰 1회 재시도한다.
    그래도 실패하거나 모델에 연결할 수 없으면 GenerationError를 던진다. 기본 워크플로우로
    바꿀지는 사용자가 원인을 보고 고른다(fallback_workflow).
    """
    from . import dag

    choice = choice or GeneratorChoice()
    last_error: GenerationError | None = None
    for attempt, temperature in enumerate(GENERATION_TEMPERATURES, start=1):
        try:
            graph, usage = await _generate_once(prompt, choice, temperature)
        except httpx.HTTPError as exc:
            logger.warning("Workflow generation model unavailable: %s", exc)
            raise GenerationError("connection", _connection_message(exc, choice), choice) from exc
        except (dag.DagError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Invalid workflow response (attempt %s): %s", attempt, exc)
            last_error = reply_error(exc, choice)
        except Exception as exc:
            logger.exception("Unexpected workflow generation failure")
            raise GenerationError("connection", f"모델 호출 중 오류가 발생했습니다: {type(exc).__name__}", choice) from exc
        else:
            info = {
                "source": "llm",
                "location": choice.location,
                "provider": choice.provider if choice.location == "cloud" else "ollama",
                "model": choice.resolved_model,
                "generated_at": _now(),
            }
            if usage:
                info["usage"] = usage
            return graph, info
    raise last_error


def fallback_workflow(prompt: str, reason: str = "") -> tuple[dict, dict]:
    """사용자가 생성 실패 후 고른 규칙 기반 기본 워크플로우."""
    from . import dag

    fb = _fallback_graph(prompt)
    graph = dag.apply_auto_flags({
        "name": fb["name"],
        "description": fb["description"],
        "goal": fb["goal"],
        "nodes": [_agent_node(n, i) for i, n in enumerate(fb["nodes"])],
        "edges": [_workflow_edge(edge) for edge in fb["edges"]],
    })
    graph["input_slots"] = _input_slots(fb["nodes"], graph["nodes"])
    info = {"source": "fallback", "location": None, "provider": None, "model": None, "generated_at": _now()}
    if reason.strip():
        info["fallback_reason"] = reason.strip()[:300]
    return graph, info


async def list_local_models() -> dict:
    """서버 로컬 Ollama에 설치된 모델 목록."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            resp.raise_for_status()
        names = sorted({str(m["name"]) for m in resp.json().get("models", []) if m.get("name")})
        return {"available": True, "models": names, "default_model": DEFAULT_MODEL, "error": None}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return {
            "available": False,
            "models": [],
            "default_model": DEFAULT_MODEL,
            "error": "서버 로컬 LLM(Ollama)에 연결할 수 없습니다.",
        }


REVISE_SYSTEM_PROMPT = """당신은 Multi-Agent System(MAS) 설계 전문가입니다.
'현재 워크플로우' JSON과 사용자의 수정 지시를 읽고, 지시를 반영한 새 워크플로우 JSON을 출력하세요.

규칙:
- 수정 지시와 무관한 에이전트는 id, name, role_prompt를 그대로 유지한다.
- 기존 에이전트를 유지할 때는 반드시 같은 id를 사용한다.
- edges는 방향성 비순환 그래프(DAG)여야 한다.
- 반드시 아래 JSON 형식만 출력한다. 다른 텍스트는 출력하지 않는다.

{
  "name": "서비스 이름",
  "description": "서비스 한 줄 설명",
  "nodes": [
    {"id": "agent1", "name": "에이전트 이름", "role_prompt": "..."}
  ],
  "edges": [
    {"source": "agent1", "target": "agent2"}
  ]
}"""


async def revise_workflow(graph: dict, instruction: str) -> dict:
    """현재 그래프에 자연어 수정 지시를 반영한 새 그래프를 반환한다.

    생성과 달리 폴백이 없다 — 실패하면 예외를 던져 사용자의 기존 그래프를 보존한다.
    """
    current = {
        "nodes": [
            {"id": n["id"], "name": n.get("name", ""), "role_prompt": n.get("role_prompt", "")}
            for n in graph.get("nodes", [])
        ],
        "edges": graph.get("edges", []),
    }
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": REVISE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "현재 워크플로우:\n" + json.dumps(current, ensure_ascii=False)
                            + "\n\n수정 지시: " + instruction
                        ),
                    },
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.2},
            },
        )
        resp.raise_for_status()
        data = _extract_json(resp.json()["message"]["content"])

    nodes = data.get("nodes") or []
    if not nodes:
        raise ValueError("수정 결과에 에이전트가 없습니다.")

    # 기존 노드의 모델·허용 폴더·좌표는 LLM 출력에 없으므로 id 기준으로 보존한다
    old = {n["id"]: n for n in graph.get("nodes", [])}
    merged_nodes = []
    for i, n in enumerate(nodes):
        nid = str(n.get("id") or f"agent{i}")
        prev = old.get(nid, {})
        merged_nodes.append({
            "id": nid,
            "type": "agent",
            "name": n.get("name") or prev.get("name") or f"에이전트 {i + 1}",
            "role_prompt": n.get("role_prompt") or prev.get("role_prompt") or "",
            "model": prev.get("model", ""),
            "worker_id": prev.get("worker_id"),
            "directory_ids": prev.get("directory_ids", []),
            "uploaded_file_ids": prev.get("uploaded_file_ids", []),
            "final": bool(prev.get("final")),
            "needs_file": bool(prev.get("needs_file")),
            "final_hint": bool(prev.get("final_hint")),
            "needs_file_hint": bool(prev.get("needs_file_hint")),
            "final_manual": bool(prev.get("final_manual")),
            "needs_file_manual": bool(prev.get("needs_file_manual")),
            "input_slot_ids": prev.get("input_slot_ids", []),
            "text_input_enabled": bool(prev.get("text_input_enabled")),
            "text_input": str(prev.get("text_input") or ""),
            "position": prev.get("position"),
        })
    from . import dag

    revised = dag.apply_auto_flags({
        "nodes": merged_nodes,
        "edges": [
            _workflow_edge(e)
            for e in (data.get("edges") or [])
            if e.get("source") and e.get("target")
        ],
    })
    return {"name": data.get("name"), "description": data.get("description"), **revised}
