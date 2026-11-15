#!/usr/bin/env python3
"""Grade chunked BGL alert predictions against LogHub's structured CSV."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GoldRow:
    line_id: int
    label: str

    @property
    def is_alert(self) -> bool:
        return self.label.strip() != "-"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare per-line BGL alert predictions with the Label column in "
            "BGL_2k.log_structured.csv."
        )
    )
    parser.add_argument("gold_csv", type=Path, help="BGL structured ground-truth CSV")
    parser.add_argument("manifest", type=Path, help="Manifest from split_log_chunks.py")
    parser.add_argument(
        "predictions_dir",
        type=Path,
        help="Directory containing one JSON prediction file per chunk",
    )
    parser.add_argument("output_dir", type=Path, help="Directory for score outputs")
    parser.add_argument(
        "--fail-below",
        type=float,
        metavar="RATE",
        help="Exit with status 1 when accuracy is below RATE (0.0 to 1.0)",
    )
    return parser.parse_args()


def load_gold(path: Path) -> list[GoldRow]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"LineId", "Label"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Gold CSV must contain LineId and Label columns")
        rows = [
            GoldRow(line_id=int(row["LineId"]), label=row["Label"])
            for row in reader
        ]

    for expected, row in enumerate(rows, start=1):
        if row.line_id != expected:
            raise ValueError(
                f"Gold CSV LineId must be continuous from 1; expected {expected}, "
                f"got {row.line_id}"
            )
    return rows


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest.get("chunks"), list):
        raise ValueError("Manifest must contain a chunks list")
    return manifest


def prediction_path(predictions_dir: Path, chunk_file: str) -> Path:
    return predictions_dir / f"{Path(chunk_file).stem}.json"


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "t", "1", "alert", "anomaly"}:
            return True
        if normalized in {"false", "f", "0", "normal", "-"}:
            return False
    if isinstance(value, dict) and "is_alert" in value:
        return parse_bool(value["is_alert"])
    raise ValueError(f"Unsupported prediction value: {value!r}")


def load_predictions(path: Path) -> list[bool]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        if "predictions" not in payload:
            raise ValueError("Prediction object must contain a predictions list")
        payload = payload["predictions"]
    if not isinstance(payload, list):
        raise ValueError("Prediction JSON must be a list or contain a predictions list")
    return [parse_bool(item) for item in payload]


def safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def grade(
    gold_csv: Path,
    manifest_path: Path,
    predictions_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    gold_rows = load_gold(gold_csv)
    manifest = load_manifest(manifest_path)
    if manifest.get("total_lines") != len(gold_rows):
        raise ValueError(
            "Manifest total_lines does not match the gold CSV row count: "
            f"{manifest.get('total_lines')} != {len(gold_rows)}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    details: list[dict[str, Any]] = []
    invalid_chunks: list[dict[str, str]] = []
    unexpected_predictions = 0

    for chunk in manifest["chunks"]:
        chunk_file = str(chunk["file"])
        start_line = int(chunk["start_line"])
        expected_count = int(chunk["line_count"])
        path = prediction_path(predictions_dir, chunk_file)
        predictions: list[bool] = []
        error = ""

        try:
            predictions = load_predictions(path)
        except (FileNotFoundError, json.JSONDecodeError, UnicodeError, ValueError) as exc:
            error = str(exc)
            invalid_chunks.append({"chunk": chunk_file, "error": error})

        if len(predictions) > expected_count:
            unexpected_predictions += len(predictions) - expected_count

        for offset in range(expected_count):
            line_id = start_line + offset
            gold = gold_rows[line_id - 1]
            predicted = predictions[offset] if offset < len(predictions) else None
            if predicted is None:
                status = "invalid" if error else "missing"
                passed = False
            else:
                status = "correct" if predicted == gold.is_alert else "incorrect"
                passed = predicted == gold.is_alert
            details.append(
                {
                    "chunk": chunk_file,
                    "line_id": line_id,
                    "gold_label": gold.label,
                    "gold_is_alert": gold.is_alert,
                    "predicted_is_alert": predicted,
                    "passed": passed,
                    "status": status,
                    "error": error,
                }
            )

    tp = sum(
        1
        for row in details
        if row["gold_is_alert"] is True and row["predicted_is_alert"] is True
    )
    tn = sum(
        1
        for row in details
        if row["gold_is_alert"] is False and row["predicted_is_alert"] is False
    )
    fp = sum(
        1
        for row in details
        if row["gold_is_alert"] is False and row["predicted_is_alert"] is True
    )
    fn = sum(
        1
        for row in details
        if row["gold_is_alert"] is True and row["predicted_is_alert"] is False
    )
    missing = sum(1 for row in details if row["predicted_is_alert"] is None)
    correct = tp + tn
    total = len(details)
    precision = safe_ratio(tp, tp + fp)
    recall = safe_ratio(tp, tp + fn)
    f1 = safe_ratio(2 * precision * recall, precision + recall)

    summary = {
        "total": total,
        "correct": correct,
        "incorrect": total - correct,
        "accuracy": safe_ratio(correct, total),
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "missing_predictions": missing,
        "unexpected_predictions": unexpected_predictions,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "invalid_chunks": invalid_chunks,
    }

    details_path = output_dir / "details.csv"
    with details_path.open("w", encoding="utf-8", newline="") as target:
        fieldnames = [
            "chunk",
            "line_id",
            "gold_label",
            "gold_is_alert",
            "predicted_is_alert",
            "passed",
            "status",
            "error",
        ]
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(details)

    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    args = parse_args()
    if args.fail_below is not None and not 0.0 <= args.fail_below <= 1.0:
        print("error: --fail-below must be between 0.0 and 1.0")
        return 2

    try:
        summary = grade(
            args.gold_csv,
            args.manifest,
            args.predictions_dir,
            args.output_dir,
        )
    except (FileNotFoundError, json.JSONDecodeError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}")
        return 2

    print(f"Accuracy: {summary['accuracy']:.2%} ({summary['correct']}/{summary['total']})")
    print(
        "TP={true_positive} TN={true_negative} FP={false_positive} "
        "FN={false_negative} missing={missing_predictions}".format(**summary)
    )
    print(f"Scores: {args.output_dir}")

    if args.fail_below is not None and summary["accuracy"] < args.fail_below:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
