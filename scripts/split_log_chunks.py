#!/usr/bin/env python3
"""Split a text log into fixed-size chunks and write a JSON manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split a log file into fixed-size chunks (100 lines by default)."
    )
    parser.add_argument("input", type=Path, help="Source log file")
    parser.add_argument("output_dir", type=Path, help="Directory for chunk files")
    parser.add_argument(
        "--lines-per-chunk",
        type=int,
        default=100,
        help="Number of source lines per chunk (default: 100)",
    )
    parser.add_argument(
        "--prefix",
        help="Chunk filename prefix (default: source filename stem)",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Source and output text encoding (default: utf-8)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace chunk files and manifest created with the same prefix",
    )
    return parser.parse_args()


def _open_chunk(
    output_dir: Path,
    prefix: str,
    suffix: str,
    chunk_number: int,
    encoding: str,
    overwrite: bool,
) -> tuple[Path, TextIO]:
    path = output_dir / f"{prefix}.part_{chunk_number:03d}{suffix}"
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {path} (use --overwrite)")
    return path, path.open("w", encoding=encoding, newline="")


def split_log(
    input_path: Path,
    output_dir: Path,
    *,
    lines_per_chunk: int = 100,
    prefix: str | None = None,
    encoding: str = "utf-8",
    overwrite: bool = False,
) -> Path:
    if lines_per_chunk <= 0:
        raise ValueError("lines_per_chunk must be greater than zero")
    if not input_path.is_file():
        raise FileNotFoundError(f"Input log does not exist: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    chunk_prefix = prefix or input_path.stem
    suffix = input_path.suffix or ".log"
    manifest_path = output_dir / f"{chunk_prefix}.manifest.json"
    if manifest_path.exists() and not overwrite:
        raise FileExistsError(
            f"Manifest already exists: {manifest_path} (use --overwrite)"
        )

    chunks: list[dict[str, int | str]] = []
    chunk_file: TextIO | None = None
    chunk_path: Path | None = None
    chunk_number = 0
    chunk_line_count = 0
    total_lines = 0

    try:
        with input_path.open("r", encoding=encoding, newline="") as source:
            for total_lines, line in enumerate(source, start=1):
                if chunk_file is None or chunk_line_count == lines_per_chunk:
                    if chunk_file is not None and chunk_path is not None:
                        chunk_file.close()
                        chunks.append(
                            {
                                "number": chunk_number,
                                "file": chunk_path.name,
                                "start_line": total_lines - chunk_line_count,
                                "end_line": total_lines - 1,
                                "line_count": chunk_line_count,
                            }
                        )
                    chunk_number += 1
                    chunk_line_count = 0
                    chunk_path, chunk_file = _open_chunk(
                        output_dir,
                        chunk_prefix,
                        suffix,
                        chunk_number,
                        encoding,
                        overwrite,
                    )

                chunk_file.write(line)
                chunk_line_count += 1
    finally:
        if chunk_file is not None:
            chunk_file.close()

    if chunk_path is not None and chunk_line_count:
        chunks.append(
            {
                "number": chunk_number,
                "file": chunk_path.name,
                "start_line": total_lines - chunk_line_count + 1,
                "end_line": total_lines,
                "line_count": chunk_line_count,
            }
        )

    manifest = {
        "source": str(input_path.resolve()),
        "encoding": encoding,
        "lines_per_chunk": lines_per_chunk,
        "total_lines": total_lines,
        "chunks": chunks,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def main() -> int:
    args = parse_args()
    try:
        manifest_path = split_log(
            args.input,
            args.output_dir,
            lines_per_chunk=args.lines_per_chunk,
            prefix=args.prefix,
            encoding=args.encoding,
            overwrite=args.overwrite,
        )
    except (FileExistsError, FileNotFoundError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}")
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print(
        f"Created {len(manifest['chunks'])} chunks from "
        f"{manifest['total_lines']} lines."
    )
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
