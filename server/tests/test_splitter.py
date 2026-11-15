"""파일 나누기 순수 함수 단위 테스트."""

import pytest

from app.services import splitter


def numbered(count: int) -> str:
    return "".join(f"line {index}\n" for index in range(1, count + 1))


class TestPartSizes:
    def test_remainder_goes_to_leading_parts(self):
        assert splitter.part_sizes(2000, 3) == [667, 667, 666]

    def test_never_more_parts_than_items(self):
        assert splitter.part_sizes(3, 10) == [1, 1, 1]

    def test_empty_input_has_no_parts(self):
        assert splitter.part_sizes(0, 4) == []


class TestAutoParts:
    def test_uses_worker_count_for_small_files(self):
        assert splitter.auto_parts(5_000, workers=3, max_chars=12_000) == 3

    def test_uses_size_when_it_needs_more_parts_than_workers(self):
        assert splitter.auto_parts(50_000, workers=2, max_chars=12_000) == 5

    def test_is_at_least_one(self):
        assert splitter.auto_parts(0, workers=0, max_chars=12_000) == 1


class TestSplitLines:
    def test_every_line_is_a_target_exactly_once(self):
        pieces = splitter.split_lines(numbered(2000), 3)
        assert [piece.count for piece in pieces] == [667, 667, 666]
        assert [(piece.start, piece.end) for piece in pieces] == [(1, 667), (668, 1334), (1335, 2000)]
        assert "".join(piece.text for piece in pieces) == numbered(2000)

    def test_more_parts_than_lines_makes_one_piece_per_line(self):
        pieces = splitter.split_lines(numbered(3), 10)
        assert [piece.text for piece in pieces] == ["line 1\n", "line 2\n", "line 3\n"]

    def test_file_without_trailing_newline_and_blank_lines_keep_line_numbers(self):
        pieces = splitter.split_lines("a\n\nb\nc", 2)
        assert [(piece.start, piece.end) for piece in pieces] == [(1, 2), (3, 4)]
        assert pieces[0].text == "a\n\n"
        assert pieces[1].text == "b\nc\n"

    def test_overlap_is_context_only_and_targets_do_not_overlap(self):
        pieces = splitter.split_lines(numbered(2000), 3, overlap=20)
        first, second, third = pieces
        assert first.context_start is None
        assert first.text.startswith("[처리 대상: 1~667줄]\nline 1\n")
        assert (second.context_start, second.context_end) == (648, 667)
        assert second.text.startswith("[참고 문맥: 648~667줄. 이해에만 쓰고 판정하지 마세요]\nline 648\n")
        assert "\n[처리 대상: 668~1334줄]\nline 668\n" in second.text
        # 처리 대상 범위는 겹치지 않고 전체를 한 번씩 덮는다
        assert [(piece.start, piece.end) for piece in pieces] == [(1, 667), (668, 1334), (1335, 2000)]
        target = third.text.split("[처리 대상: 1335~2000줄]\n", 1)[1]
        assert target == "".join(f"line {index}\n" for index in range(1335, 2001))

    def test_overlap_longer_than_previous_piece_stops_at_file_start(self):
        pieces = splitter.split_lines(numbered(4), 2, overlap=50)
        assert (pieces[1].context_start, pieces[1].context_end) == (1, 2)


class TestSplitCsv:
    CSV = "id,answer\n" + "".join(f"{index},답안 {index}\n" for index in range(1, 61))

    def test_header_on_every_piece_and_rows_once(self):
        pieces = splitter.split_csv(self.CSV, 4)
        assert [piece.count for piece in pieces] == [15, 15, 15, 15]
        rows: list[str] = []
        for piece in pieces:
            lines = piece.text.splitlines()
            assert lines[0] == "id,answer"
            rows += lines[1:]
        assert rows == [f"{index},답안 {index}" for index in range(1, 61)]

    def test_quoted_newline_stays_in_one_row(self):
        text = 'id,answer\n1,"첫 줄\n둘째 줄"\n2,짧은 답\n3,끝\n'
        pieces = splitter.split_csv(text, 3)
        assert [piece.count for piece in pieces] == [1, 1, 1]
        assert pieces[0].text == 'id,answer\n1,"첫 줄\n둘째 줄"\n'

    def test_blank_lines_are_not_rows(self):
        assert splitter.csv_row_count("id\n1\n\n2\n\n") == 2

    def test_more_parts_than_rows(self):
        pieces = splitter.split_csv("id\n1\n2\n", 5)
        assert [piece.text for piece in pieces] == ["id\n1\n", "id\n2\n"]


class TestSplitText:
    def test_auto_follows_worker_count(self):
        pieces = splitter.split_text(numbered(2000), "line", parts=None, workers=3, max_chars=30_000)
        assert [piece.count for piece in pieces] == [667, 667, 666]

    def test_auto_adds_parts_until_every_piece_fits(self):
        # 앞쪽 줄만 길어서 균등하게 나누면 첫 조각이 한도를 넘는다
        text = "".join("x" * 400 + "\n" for _ in range(20)) + "".join("y\n" for _ in range(180))
        pieces = splitter.split_text(text, "line", parts=None, workers=2, max_chars=2_000)
        assert len(pieces) > 2
        assert max(len(piece.text) for piece in pieces) <= 2_000
        assert sum(piece.count for piece in pieces) == 200

    def test_auto_rejects_files_that_need_too_many_parts(self):
        with pytest.raises(splitter.SplitError) as error:
            splitter.split_text(numbered(20_000), "line", parts=None, workers=2, max_chars=1_000)
        assert error.value.code == "split_too_large"

    def test_single_line_longer_than_worker_limit_is_rejected(self):
        with pytest.raises(splitter.SplitError) as error:
            splitter.split_text("x" * 40_000 + "\n", "line", parts=None, workers=2, max_chars=30_000)
        assert error.value.code == "split_too_large"

    def test_manual_parts_reject_pieces_the_worker_would_truncate(self):
        text = "".join("z" * 99 + "\n" for _ in range(1000))
        with pytest.raises(splitter.SplitError) as error:
            splitter.split_text(text, "line", parts=2, workers=2)
        assert error.value.code == "split_too_large"

    def test_empty_file_is_rejected(self):
        with pytest.raises(splitter.SplitError) as error:
            splitter.split_text("", "line", parts=None, workers=2)
        assert error.value.code == "split_empty"

    def test_csv_ignores_overlap(self):
        pieces = splitter.split_text("id\n1\n2\n3\n4\n", "csv", parts=2, workers=1, overlap=20)
        assert [piece.text for piece in pieces] == ["id\n1\n2\n", "id\n3\n4\n"]


class TestHelpers:
    def test_detect_unit(self):
        assert splitter.detect_unit(["BGL_2k.log"]) == "line"
        assert splitter.detect_unit(["answers.CSV"]) == "csv"
        assert splitter.detect_unit(["rows.jsonl"]) == "line"
        assert splitter.detect_unit(["report.pdf"]) is None
        assert splitter.detect_unit(["a.pdf", "b.txt"]) == "file"
        assert splitter.detect_unit([]) is None

    def test_distribute_round_robin(self):
        assert splitter.distribute([1, 2, 3, 4, 5], 2) == [[1, 3, 5], [2, 4]]
        assert splitter.distribute([1, 2], 5) == [[1], [2]]

    def test_labels_and_names(self):
        assert splitter.range_label(668, 1334, "line") == "668~1334줄"
        assert splitter.range_label(21, 40, "csv") == "21~40행"
        assert splitter.range_label(7, 7, "line") == "7줄"
        assert splitter.piece_name("BGL_2k.log", 2, 3) == "BGL_2k.part02of03.log"


class TestSplitJson:
    ITEMS = [{"id": i, "answer": f"답안 {i}"} for i in range(1, 11)]

    def test_array_items_are_split_into_valid_json_pieces(self):
        import json
        pieces = splitter.split_json(json.dumps(self.ITEMS, ensure_ascii=False), 3)
        assert [(p.start, p.end) for p in pieces] == [(1, 4), (5, 7), (8, 10)]
        restored = [item for p in pieces for item in json.loads(p.text)]
        assert restored == self.ITEMS

    def test_object_with_one_array_keeps_its_key(self):
        import json
        text = json.dumps({"answers": self.ITEMS, "meta": {"class": "A"}}, ensure_ascii=False)
        pieces = splitter.split_json(text, 2)
        assert [list(json.loads(p.text)) for p in pieces] == [["answers"], ["answers"]]
        assert sum(len(json.loads(p.text)["answers"]) for p in pieces) == 10

    def test_unsplittable_json_is_rejected(self):
        for text in ('{"a": 1}', '{"a": [1], "b": [2]}', "not json", '"text"'):
            with pytest.raises(splitter.SplitError) as error:
                splitter.split_json(text, 2)
            assert error.value.code == "split_unsupported"

    def test_detect_and_label(self):
        assert splitter.detect_unit(["answers.json"]) == "json"
        assert splitter.range_label(1, 50, "json") == "1~50번 항목"
        assert splitter.unit_count('[1, 2, 3]', "json") == 3

    def test_split_text_supports_json(self):
        pieces = splitter.split_text("[1, 2, 3, 4, 5]", "json", parts=None, workers=2)
        assert [p.count for p in pieces] == [3, 2]
