#!/usr/bin/env python3
"""Remove the leading BGL alert label without changing line order or count."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a BGL log for model input by removing only the first "
            "alert-label field from every non-empty line."
        )
    )
    parser.add_argument("input", type=Path, help="Original BGL_2k.log file")
    parser.add_argument("output", type=Path, help="Unlabelled log to create")
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Source and output text encoding (default: utf-8)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the output file when it already exists",
    )
    return parser.parse_args()


def _split_newline(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    if line.endswith("\r"):
        return line[:-1], "\r"
    return line, ""


def remove_bgl_labels(
    input_path: Path,
    output_path: Path,
    *,
    encoding: str = "utf-8",
    overwrite: bool = False,
) -> int:
    """Write ``input_path`` without each BGL line's leading alert label.

    Empty lines are copied unchanged so that source line numbers still match
    LogHub's structured CSV and the benchmark's chunk manifest.
    """
    if not input_path.is_file():
        raise FileNotFoundError(f"Input log does not exist: {input_path}")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path} (use --overwrite)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    line_count = 0
    with input_path.open("r", encoding=encoding, newline="") as source, output_path.open(
        "w", encoding=encoding, newline=""
    ) as target:
        for line_number, line in enumerate(source, start=1):
            line_count = line_number
            body, newline = _split_newline(line)
            if not body.strip():
                target.write(line)
                continue

            label, separator, remainder = body.partition(" ")
            if not separator or not remainder:
                raise ValueError(
                    f"Line {line_number} has no data after its BGL alert label: {label!r}"
                )
            target.write(remainder.lstrip(" \t") + newline)
    return line_count


def main() -> int:
    args = parse_args()
    try:
        line_count = remove_bgl_labels(
            args.input,
            args.output,
            encoding=args.encoding,
            overwrite=args.overwrite,
        )
    except (FileExistsError, FileNotFoundError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}")
        return 2

    print(f"Created {args.output} from {line_count} lines.")
    print("Removed only the leading BGL alert-label field; timestamps and log content remain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
