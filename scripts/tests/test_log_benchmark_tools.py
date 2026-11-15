from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


splitter = load_module("split_log_chunks", "split_log_chunks.py")
grader = load_module("grade_bgl_predictions", "grade_bgl_predictions.py")
preparer = load_module("prepare_bgl_unlabeled", "prepare_bgl_unlabeled.py")


class SplitLogTests(unittest.TestCase):
    def test_splits_and_writes_manifest(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "sample.log"
            source.write_text("".join(f"line {number}\n" for number in range(1, 206)))

            manifest_path = splitter.split_log(source, root / "chunks")
            manifest = json.loads(manifest_path.read_text())

            self.assertEqual(manifest["total_lines"], 205)
            self.assertEqual(len(manifest["chunks"]), 3)
            self.assertEqual(manifest["chunks"][0]["start_line"], 1)
            self.assertEqual(manifest["chunks"][0]["end_line"], 100)
            self.assertEqual(manifest["chunks"][2]["line_count"], 5)
            last_chunk = root / "chunks" / manifest["chunks"][2]["file"]
            self.assertEqual(len(last_chunk.read_text().splitlines()), 5)


class PrepareBglTests(unittest.TestCase):
    def test_removes_only_the_leading_label_and_preserves_lines(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "BGL_2k.log"
            source.write_text(
                "- 1117838570 RAS KERNEL INFO cache corrected\n"
                "APPREAD 1117838571 RAS KERNEL FATAL application error\n\n",
                encoding="utf-8",
            )
            output = root / "BGL_2k_input_unlabeled.log"

            line_count = preparer.remove_bgl_labels(source, output)

            self.assertEqual(line_count, 3)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "1117838570 RAS KERNEL INFO cache corrected\n"
                "1117838571 RAS KERNEL FATAL application error\n\n",
            )


class GradePredictionsTests(unittest.TestCase):
    def write_gold(self, path: Path) -> None:
        with path.open("w", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=["LineId", "Label"])
            writer.writeheader()
            for line_id, label in enumerate(["-", "APPREAD", "KERNDTLB", "-", "APPREAD"], 1):
                writer.writerow({"LineId": line_id, "Label": label})

    def test_grades_boolean_predictions(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "sample.log"
            source.write_text("".join(f"line {number}\n" for number in range(1, 6)))
            chunks = root / "chunks"
            manifest = splitter.split_log(source, chunks, lines_per_chunk=3)
            gold = root / "gold.csv"
            self.write_gold(gold)
            predictions = root / "predictions"
            predictions.mkdir()
            (predictions / "sample.part_001.json").write_text(
                json.dumps({"predictions": [False, True, False]})
            )
            (predictions / "sample.part_002.json").write_text(
                json.dumps([True, {"is_alert": True}])
            )

            summary = grader.grade(gold, manifest, predictions, root / "scores")

            self.assertEqual(summary["correct"], 3)
            self.assertEqual(summary["true_positive"], 2)
            self.assertEqual(summary["true_negative"], 1)
            self.assertEqual(summary["false_positive"], 1)
            self.assertEqual(summary["false_negative"], 1)
            self.assertEqual(summary["accuracy"], 0.6)
            self.assertTrue((root / "scores" / "details.csv").is_file())
            self.assertTrue((root / "scores" / "summary.json").is_file())

    def test_missing_chunk_counts_as_missing_predictions(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "sample.log"
            source.write_text("".join(f"line {number}\n" for number in range(1, 6)))
            manifest = splitter.split_log(source, root / "chunks", lines_per_chunk=3)
            gold = root / "gold.csv"
            self.write_gold(gold)
            predictions = root / "predictions"
            predictions.mkdir()
            (predictions / "sample.part_001.json").write_text(
                json.dumps([False, True, True])
            )

            summary = grader.grade(gold, manifest, predictions, root / "scores")

            self.assertEqual(summary["correct"], 3)
            self.assertEqual(summary["missing_predictions"], 2)
            self.assertEqual(len(summary["invalid_chunks"]), 1)


if __name__ == "__main__":
    unittest.main()
