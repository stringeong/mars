"""시스템 테스트용 Ollama API 대역 서버 (D07 시스템 테스트 결과서 5.2절).

실제 모델 대신 요청에 담긴 표식어에 따라 정해진 응답을 돌려준다.

- 워크플로우 생성 요청: 에이전트 3개 DAG(JSON)
- 'BROKEN'이 들어간 생성 요청: 해석할 수 없는 문장
- Worker의 파일 선별 요청: 미리보기가 붙은 파일 경로 전부(JSON)
- 역할(system)에 'FAIL_TASK': HTTP 500
- 역할(system)에 'SLOW': SLOW_SECONDS초 지연 후 입력을 그대로 돌려줌
- 역할(system)에 'Markdown': 입력 뒤에 Markdown 요약 표를 붙여 돌려줌
- 그 밖의 작업: 받은 입력(user 메시지)을 그대로 돌려줌

그래서 모델에 실제로 무엇이 전달됐는지 실행 결과에서 확인할 수 있다.
받은 /api/chat 요청은 LOG_PATH(환경변수 FAKE_OLLAMA_LOG)에 한 줄씩 JSON으로 남긴다.

표준 라이브러리만 쓴다. 실행: python fake_ollama.py --port 11434
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODELS = ["gemma3:4b", "qwen3:8b"]
CONTEXT_LENGTH = 32768
SLOW_SECONDS = float(os.getenv("FAKE_OLLAMA_SLOW_SEC", "15"))
LOG_PATH = os.getenv("FAKE_OLLAMA_LOG", "")

# 서버 생성기(generator.SYSTEM_PROMPT)와 Worker 생성 작업이 같은 시스템 프롬프트를 쓴다
GENERATION_MARK = "Multi-Agent System(MAS) 설계"
# Worker가 공유 폴더에서 작업에 쓸 파일을 고를 때 보내는 요청(executor._select_relevant_files)
SELECTION_MARK = "파일 선별 담당"

WORKFLOW = {
    "description": "카드 내역을 분류하고 이상 거래를 찾아 월간 리포트로 정리한다",
    "nodes": [
        {
            "id": "agent1", "name": "지출 분류 에이전트",
            "role_prompt": "카드 사용 내역의 거래를 항목별로 분류한다.",
            "needs_file": True, "file_key": "credit_card",
            "file_description": "신용카드 사용 내역",
            "file_format": "CSV, 열: 거래ID, 일시, 거래처, 금액",
        },
        {
            "id": "agent2", "name": "이상 거래 탐지 에이전트",
            "role_prompt": "카드 사용 내역에서 평소와 다른 거래를 찾는다.",
            "needs_file": True, "file_key": "credit_card",
            "file_description": "신용카드 사용 내역",
            "file_format": "CSV, 열: 거래ID, 일시, 거래처, 금액",
        },
        {
            "id": "agent3", "name": "리포트 작성 에이전트",
            "role_prompt": "앞 단계 결과를 모아 월간 리포트를 Markdown으로 쓴다.",
            "needs_file": False, "final": True,
        },
    ],
    "edges": [
        {"source": "agent1", "target": "agent3"},
        {"source": "agent2", "target": "agent3"},
    ],
}

MARKDOWN_SUMMARY = "\n\n## 요약\n\n| 항목 | 값 |\n|---|---|\n| 거래 수 | 3건 |\n| 합계 | 36,950원 |\n"

_installed = list(MODELS)
_lock = threading.Lock()


def _log(entry: dict) -> None:
    if not LOG_PATH:
        return
    with _lock, open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _content(messages: list[dict], role: str) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == role)


def reply_for(body: dict) -> tuple[int, str]:
    """(HTTP 상태, 모델 응답 텍스트)"""
    messages = body.get("messages") or []
    system, user = _content(messages, "system"), _content(messages, "user")
    if SELECTION_MARK in system:
        # 실제 모델처럼 미리보기가 붙은(=Worker가 읽을 수 있는) 파일만 고른다
        paths = [line[2:].strip() for line in user.splitlines() if line.startswith("- ")]
        return 200, json.dumps({"files": paths}, ensure_ascii=False)
    if GENERATION_MARK in system:
        if "BROKEN" in user:
            return 200, "죄송하지만 요청을 이해하지 못했습니다."
        return 200, json.dumps(WORKFLOW, ensure_ascii=False)
    if "FAIL_TASK" in system:
        return 500, ""
    if "SLOW" in system:
        time.sleep(SLOW_SECONDS)
    if "Markdown" in system:
        # Markdown 결과를 쓰라는 블록(리포트 작성)은 입력 뒤에 요약 표를 붙여 렌더링을 확인할 수 있게 한다
        return 200, user + MARKDOWN_SUMMARY
    return 200, user


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _json(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}") if length else {}

    def do_GET(self):
        if self.path in ("/", "/api/version"):
            self._json({"version": "0.0.0-fake"})
        elif self.path == "/api/tags":
            with _lock:
                self._json({"models": [{"name": m, "model": m, "size": 1} for m in _installed]})
        elif self.path == "/api/ps":
            self._json({"models": []})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        body = self._body()
        if self.path == "/api/chat":
            status, text = reply_for(body)
            _log({"model": body.get("model"), "status": status, "messages": body.get("messages")})
            if status != 200:
                self._json({"error": "fake failure (FAIL_TASK)"}, status)
                return
            self._json({
                "model": body.get("model"), "done": True,
                "message": {"role": "assistant", "content": text},
                "prompt_eval_count": len(_content(body.get("messages") or [], "user")) // 4,
                "eval_count": len(text) // 4,
            })
        elif self.path == "/api/show":
            self._json({"model_info": {"fake.context_length": CONTEXT_LENGTH}})
        elif self.path == "/api/pull":
            name = body.get("model") or body.get("name") or ""
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for done in (0, 50, 100):
                line = {"status": "pulling", "total": 100, "completed": done}
                self.wfile.write((json.dumps(line) + "\n").encode())
                self.wfile.flush()
                time.sleep(0.2)
            self.wfile.write(b'{"status":"success"}\n')
            with _lock:
                if name and name not in _installed:
                    _installed.append(name)
        else:
            self._json({"error": "not found"}, 404)

    def do_DELETE(self):
        body = self._body()
        name = body.get("model") or body.get("name") or ""
        with _lock:
            if name not in _installed:
                self._json({"error": f"model '{name}' not found"}, 404)
                return
            _installed.remove(name)
        self._json({})


def main() -> None:
    parser = argparse.ArgumentParser(description="Ollama API 대역 서버")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11434)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"fake ollama: http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
