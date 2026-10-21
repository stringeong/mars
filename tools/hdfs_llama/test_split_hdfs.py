import tempfile
import unittest
from pathlib import Path

import split_hdfs


class SplitHdfsTests(unittest.TestCase):
    def test_groups_by_block_and_keeps_orphan(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.log"
            source.write_text(
                "x blk_1 first\n" "x blk_2 second\n" "x blk_1 third\n" "no block here\n",
                encoding="utf-8",
            )
            traces, count = split_hdfs.read_raw(source)
            self.assertEqual(count, 4)
            self.assertEqual([t.block_id for t in traces], ["blk_1", "blk_2", "__NO_BLOCK__00000001"])
            self.assertEqual(traces[0].source_lines, [1, 3])

    def test_writes_manifest_and_bounded_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sample.log"
            source.write_text("".join(f"x blk_{i} message {i}\n" for i in range(100)), encoding="utf-8")
            traces, _ = split_hdfs.read_raw(source)
            summary = split_hdfs.write_chunks(traces, root / "out", source, 512, 256, 3.0)
            self.assertGreater(summary["chunks"], 1)
            self.assertTrue((root / "out" / "manifest.jsonl").is_file())
            for chunk in (root / "out").glob("chunk_*.txt"):
                self.assertLessEqual(split_hdfs.token_estimate(chunk.read_text(), 3.0), 512)


if __name__ == "__main__":
    unittest.main()
