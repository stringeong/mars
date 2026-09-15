"""sandbox 폴더 화이트리스트 검증 (최소 권한 원칙, 요구사항 2.4/2.5).

계약: 서버가 어떤 경로를 지시하더라도 허용 폴더 밖 접근은 거부되어야 한다.
"""

import pytest

from agent import sandbox


@pytest.fixture()
def allowed(tmp_path):
    base = tmp_path / "docs"
    base.mkdir()
    return base


class TestIsAllowed:
    def test_file_inside_allowed_folder(self, allowed):
        f = allowed / "a.txt"
        f.write_text("내용")
        assert sandbox.is_allowed(f, [str(allowed)])

    def test_nested_file_inside_allowed_folder(self, allowed):
        sub = allowed / "sub"
        sub.mkdir()
        f = sub / "a.txt"
        f.write_text("내용")
        assert sandbox.is_allowed(f, [str(allowed)])

    def test_allowed_folder_itself(self, allowed):
        assert sandbox.is_allowed(allowed, [str(allowed)])

    def test_outside_path_denied(self, allowed, tmp_path):
        outside = tmp_path / "secret.txt"
        outside.write_text("비밀")
        assert not sandbox.is_allowed(outside, [str(allowed)])

    def test_empty_whitelist_denies_everything(self, allowed):
        f = allowed / "a.txt"
        f.write_text("내용")
        assert not sandbox.is_allowed(f, [])

    def test_path_traversal_denied(self, allowed, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("비밀")
        # 허용 폴더를 경유하는 것처럼 보이지만 ..으로 밖을 가리키는 경로
        sneaky = str(allowed / ".." / "secret.txt")
        assert not sandbox.is_allowed(sneaky, [str(allowed)])

    def test_prefix_confusion_denied(self, tmp_path):
        # /x/docs 허용이 /x/docs-evil 을 허용하면 안 된다
        allowed = tmp_path / "docs"
        allowed.mkdir()
        evil = tmp_path / "docs-evil"
        evil.mkdir()
        f = evil / "a.txt"
        f.write_text("내용")
        assert not sandbox.is_allowed(f, [str(allowed)])

    def test_symlink_escape_denied(self, allowed, tmp_path):
        """허용 폴더 안의 심볼릭 링크가 밖을 가리키면 차단되어야 한다."""
        outside = tmp_path / "secret.txt"
        outside.write_text("비밀")
        link = allowed / "link.txt"
        link.symlink_to(outside)
        assert not sandbox.is_allowed(link, [str(allowed)])

    def test_symlinked_dir_escape_denied(self, allowed, tmp_path):
        outside_dir = tmp_path / "private"
        outside_dir.mkdir()
        (outside_dir / "secret.txt").write_text("비밀")
        link = allowed / "shortcut"
        link.symlink_to(outside_dir)
        assert not sandbox.is_allowed(link / "secret.txt", [str(allowed)])

    def test_expanduser_in_whitelist_and_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        docs = tmp_path / "docs"
        docs.mkdir()
        f = docs / "a.txt"
        f.write_text("내용")
        assert sandbox.is_allowed("~/docs/a.txt", ["~/docs"])

    def test_nonexistent_path_under_allowed_folder(self, allowed):
        # 존재하지 않는 경로라도 위치 판정 자체는 가능해야 한다 (읽기는 read_file에서 실패)
        assert sandbox.is_allowed(allowed / "ghost.txt", [str(allowed)])


class TestReadFile:
    def test_reads_allowed_file(self, allowed):
        f = allowed / "a.txt"
        f.write_text("안녕하세요", encoding="utf-8")
        assert sandbox.read_file(str(f), [str(allowed)]) == "안녕하세요"

    def test_denied_path_raises(self, allowed, tmp_path):
        outside = tmp_path / "secret.txt"
        outside.write_text("비밀")
        with pytest.raises(sandbox.SandboxError):
            sandbox.read_file(str(outside), [str(allowed)])

    def test_symlink_escape_raises(self, allowed, tmp_path):
        outside = tmp_path / "secret.txt"
        outside.write_text("비밀")
        link = allowed / "link.txt"
        link.symlink_to(outside)
        with pytest.raises(sandbox.SandboxError):
            sandbox.read_file(str(link), [str(allowed)])

    def test_directory_raises(self, allowed):
        with pytest.raises(sandbox.SandboxError):
            sandbox.read_file(str(allowed), [str(allowed)])

    def test_missing_file_raises(self, allowed):
        with pytest.raises(sandbox.SandboxError):
            sandbox.read_file(str(allowed / "ghost.txt"), [str(allowed)])

    def test_large_file_truncated(self, allowed):
        f = allowed / "big.txt"
        f.write_bytes(b"a" * (sandbox.MAX_FILE_BYTES + 100))
        content = sandbox.read_file(str(f), [str(allowed)])
        assert len(content) == sandbox.MAX_FILE_BYTES

    def test_truncation_mid_multibyte_char_does_not_crash(self, allowed):
        # 상한 경계가 한글(3바이트) 문자 중간에 걸려도 예외 없이 읽혀야 한다
        f = allowed / "kr.txt"
        f.write_bytes(b"a" * (sandbox.MAX_FILE_BYTES - 1) + "가".encode("utf-8"))
        content = sandbox.read_file(str(f), [str(allowed)])
        assert content.startswith("a")
        assert "�" in content  # 잘린 문자는 대체 문자로 표시된다


class TestListFiles:
    def test_only_text_extensions(self, allowed):
        (allowed / "a.txt").write_text("t")
        (allowed / "b.py").write_text("p")
        (allowed / "img.png").write_bytes(b"\x89PNG")
        (allowed / "run.exe").write_bytes(b"MZ")
        files = sandbox.list_files([str(allowed)])
        names = {f.rsplit("/", 1)[-1] for f in files}
        assert names == {"a.txt", "b.py"}

    def test_uppercase_extension_included(self, allowed):
        (allowed / "NOTES.TXT").write_text("t")
        files = sandbox.list_files([str(allowed)])
        assert len(files) == 1

    def test_hidden_files_and_dirs_skipped(self, allowed):
        (allowed / ".hidden.txt").write_text("t")
        secret_dir = allowed / ".git"
        secret_dir.mkdir()
        (secret_dir / "config.txt").write_text("t")
        assert sandbox.list_files([str(allowed)]) == []

    def test_skip_dirs_not_traversed(self, allowed):
        nm = allowed / "node_modules"
        nm.mkdir()
        (nm / "pkg.json").write_text("{}")
        (allowed / "keep.md").write_text("k")
        files = sandbox.list_files([str(allowed)])
        assert len(files) == 1
        assert files[0].endswith("keep.md")

    def test_nested_dirs_traversed(self, allowed):
        sub = allowed / "sub" / "deep"
        sub.mkdir(parents=True)
        (sub / "c.md").write_text("c")
        files = sandbox.list_files([str(allowed)])
        assert len(files) == 1
        assert files[0].endswith("c.md")

    def test_max_entries_cap(self, allowed):
        for i in range(10):
            (allowed / f"f{i}.txt").write_text("x")
        assert len(sandbox.list_files([str(allowed)], max_entries=3)) == 3

    def test_nonexistent_base_skipped(self, allowed, tmp_path):
        (allowed / "a.txt").write_text("t")
        files = sandbox.list_files([str(tmp_path / "ghost"), str(allowed)])
        assert len(files) == 1

    def test_file_as_base_yields_nothing(self, allowed):
        f = allowed / "a.txt"
        f.write_text("t")
        assert sandbox.list_files([str(f)]) == []
