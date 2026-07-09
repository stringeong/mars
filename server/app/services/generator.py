"""자연어 생성 프롬프트 -> MAS 워크플로우(DAG) 생성.

1차: Ollama LLM에게 JSON 스키마로 요청.
실패 시: 규칙 기반 폴백(수집 -> 분석 -> 정리 3단계)으로 항상 결과를 보장한다.
"""

import json
import re

import httpx

from ..config import DEFAULT_MODEL, OLLAMA_URL

SYSTEM_PROMPT = """당신은 Multi-Agent System(MAS) 설계 전문가입니다.
사용자가 만들고 싶은 서비스 설명을 읽고, 이를 수행할 에이전트 구성과 실행 순서(DAG)를 설계하세요.

규칙:
- 에이전트는 2~6개. 각 에이전트는 한 가지 역할만 담당한다.
- edges는 방향성 비순환 그래프(DAG)여야 한다. 병렬 분기가 자연스러우면 사용한다.
- role_prompt는 해당 에이전트에게 줄 시스템 프롬프트로, 한국어로 구체적으로 작성한다.
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


def _extract_json(text: str) -> dict:
    """LLM 출력에서 첫 JSON 오브젝트를 추출한다."""
    # <think>...</think> 등 추론 블록 제거
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("JSON을 찾을 수 없음")
    return json.loads(match.group(0))


def _fallback_graph(prompt: str) -> dict:
    """LLM을 사용할 수 없을 때의 규칙 기반 3단계 워크플로우."""
    topic = prompt.strip()[:40]
    return {
        "name": f"{topic} 서비스",
        "description": prompt.strip(),
        "nodes": [
            {
                "id": "collector",
                "name": "정보 수집 에이전트",
                "role_prompt": (
                    "당신은 정보 수집 담당입니다. 사용자의 요청과 제공된 자료를 바탕으로 "
                    "필요한 정보를 항목별로 정리해 나열하세요. 요청: " + prompt
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


async def generate_workflow(prompt: str) -> tuple[dict, str]:
    """(graph_dict, source) 반환. source는 'llm' 또는 'fallback'."""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": DEFAULT_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.3},
                },
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            data = _extract_json(content)

        nodes = data.get("nodes") or []
        if not nodes:
            raise ValueError("에이전트가 비어 있음")
        graph = {
            "name": data.get("name") or "새 서비스",
            "description": data.get("description") or prompt,
            "nodes": [
                {
                    "id": str(n.get("id") or f"agent{i}"),
                    "name": n.get("name") or f"에이전트 {i + 1}",
                    "role_prompt": n.get("role_prompt") or "",
                    "model": "",
                    "allowed_folders": [],
                }
                for i, n in enumerate(nodes)
            ],
            "edges": [
                {"source": str(e["source"]), "target": str(e["target"])}
                for e in (data.get("edges") or [])
                if e.get("source") and e.get("target")
            ],
        }
        return graph, "llm"
    except Exception:
        fb = _fallback_graph(prompt)
        graph = {
            "name": fb["name"],
            "description": fb["description"],
            "nodes": [
                {**n, "model": "", "allowed_folders": []} for n in fb["nodes"]
            ],
            "edges": fb["edges"],
        }
        return graph, "fallback"
