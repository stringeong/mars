"""executor 검증 — Ollama 호출 래핑, 파일 선별, 프롬프트 조립.

Ollama HTTP 호출(httpx.post)은 monkeypatch로 대체한다.
"""

import json

import httpx
import pytest

from agent import executor

CONFIG = {"ollama_url": "http://ollama.test", "default_model": "기본모델"}


@pytest.fixture()
def fake_ollama(monkeypatch):
    """httpx.post를 가짜로 바꾸고 (호출 기록, 응답 설정)을 돌려준다."""
    calls: list[dict] = []
    state = {"content": "응답"}

    def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json})
        return httpx.Response(
            200,
            json={"message": {"content": state["content"]}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(executor.httpx, "post", fake_post)
    return calls, state


class TestChat:
    def test_returns_stripped_content(self, fake_ollama):
        calls, state = fake_ollama
        state["content"] = "  결과 텍스트  "
        out = executor._chat(CONFIG, "모델", [{"role": "user", "content": "질문"}], 0.5)
        assert out == "결과 텍스트"

    def test_think_block_removed(self, fake_ollama):
        calls, state = fake_ollama
        state["content"] = "<think>추론 과정...</think>\n최종 답변"
        out = executor._chat(CONFIG, "모델", [], 0.5)
        assert out == "최종 답변"

    def test_request_payload(self, fake_ollama):
        calls, state = fake_ollama
        messages = [{"role": "user", "content": "질문"}]
        executor._chat(CONFIG, "qwen3:8b", messages, 0.2)
        assert calls[0]["url"] == "http://ollama.test/api/chat"
        assert calls[0]["json"]["model"] == "qwen3:8b"
        assert calls[0]["json"]["messages"] == messages
        assert calls[0]["json"]["options"]["temperature"] == 0.2
        assert calls[0]["json"]["stream"] is False


class TestRunTask:
    def test_uses_task_model_when_set(self, fake_ollama):
        calls, state = fake_ollama
        executor.run_task({"model": "커스텀모델", "role_prompt": "역할"}, CONFIG)
        assert calls[0]["json"]["model"] == "커스텀모델"

    def test_falls_back_to_default_model(self, fake_ollama):
        calls, state = fake_ollama
        executor.run_task({"model": "", "role_prompt": "역할"}, CONFIG)
        assert calls[0]["json"]["model"] == "기본모델"


@pytest.fixture()
def folder(tmp_path):
    base = tmp_path / "docs"
    base.mkdir()
    return base


class TestSelectRelevantFiles:
    def _task(self, folder):
        return {"role_prompt": "이력서를 다듬어라", "allowed_folders": [str(folder)]}

    def test_single_file_skips_llm(self, folder, monkeypatch):
        def boom(*a, **kw):
            raise AssertionError("파일이 1개면 LLM을 호출하지 않아야 한다")

        monkeypatch.setattr(executor, "_chat", boom)
        files = [str(folder / "only.txt")]
        assert executor._select_relevant_files(self._task(folder), files, CONFIG) == files

    def test_llm_selection_intersected_with_real_files(self, folder, monkeypatch):
        """LLM이 지어낸 경로는 걸러지고, 원본 목록의 순서가 유지된다."""
        for name in ("a.txt", "b.txt", "c.txt"):
            (folder / name).write_text(name)
        files = [str(folder / n) for n in ("a.txt", "b.txt", "c.txt")]

        monkeypatch.setattr(
            executor, "_chat",
            lambda *a, **kw: json.dumps(
                {"files": [files[2], files[0], "/tmp/지어낸파일.txt"]}
            ),
        )
        selected = executor._select_relevant_files(self._task(folder), files, CONFIG)
        assert selected == [files[0], files[2]]

    def test_llm_failure_falls_back_to_all(self, folder, monkeypatch):
        for name in ("a.txt", "b.txt"):
            (folder / name).write_text(name)
        files = [str(folder / n) for n in ("a.txt", "b.txt")]

        def boom(*a, **kw):
            raise RuntimeError("Ollama 다운")

        monkeypatch.setattr(executor, "_chat", boom)
        assert executor._select_relevant_files(self._task(folder), files, CONFIG) == files

    def test_llm_garbage_reply_falls_back_to_all(self, folder, monkeypatch):
        for name in ("a.txt", "b.txt"):
            (folder / name).write_text(name)
        files = [str(folder / n) for n in ("a.txt", "b.txt")]

        monkeypatch.setattr(executor, "_chat", lambda *a, **kw: "JSON 아님")
        assert executor._select_relevant_files(self._task(folder), files, CONFIG) == files


class TestBuildMessages:
    def test_without_folders(self):
        task = {"role_prompt": "요약 담당", "input_context": "[이전 결과]\n내용"}
        messages = executor._build_messages(task, CONFIG)
        assert messages[0] == {"role": "system", "content": "요약 담당"}
        assert "[이전 결과]\n내용" in messages[1]["content"]

    def test_default_system_prompt_when_role_empty(self):
        messages = executor._build_messages({"role_prompt": ""}, CONFIG)
        assert messages[0]["content"] == "당신은 유능한 AI 어시스턴트입니다."

    def test_file_context_included_and_capped(self, folder, monkeypatch):
        # 선별 단계는 통과시키고(전체 반환) 갯수 상한만 검증한다
        monkeypatch.setattr(
            executor, "_select_relevant_files", lambda task, files, config: files
        )
        n_files = executor.FILE_CONTEXT_LIMIT + 2
        for i in range(n_files):
            (folder / f"f{i}.txt").write_text(f"파일 {i} 내용")

        task = {"role_prompt": "역할", "allowed_folders": [str(folder)]}
        messages = executor._build_messages(task, CONFIG)
        user = messages[1]["content"]

        assert "[이 작업에 사용할 로컬 파일 목록]" in user
        assert user.count("- " + str(folder)) == n_files  # 목록에는 전부
        assert user.count("### ") == executor.FILE_CONTEXT_LIMIT  # 발췌는 상한까지만

    def test_file_content_truncated_to_4000_chars(self, folder, monkeypatch):
        monkeypatch.setattr(
            executor, "_select_relevant_files", lambda task, files, config: files
        )
        (folder / "big.txt").write_text("가" * 5000)
        task = {"role_prompt": "역할", "allowed_folders": [str(folder)]}
        user = executor._build_messages(task, CONFIG)[1]["content"]
        assert "가" * 4000 in user
        assert "가" * 4001 not in user

    def test_empty_folder_adds_no_file_sections(self, folder):
        task = {"role_prompt": "역할", "allowed_folders": [str(folder)]}
        user = executor._build_messages(task, CONFIG)[1]["content"]
        assert "로컬 파일" not in user
