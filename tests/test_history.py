import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from history import load_history, mark_published, published_paper_ids, save_history


class HistoryTests(unittest.TestCase):
    def test_mark_published_adds_paper_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "history.json"
            save_history(path, {"2609.00001"})
            count = mark_published(
                path,
                [{"arxiv_id": "2609.00002"}, {"arxiv_id": "2609.00001"}],
            )
            self.assertEqual(count, 2)
            self.assertEqual(load_history(path), {"2609.00001", "2609.00002"})
            self.assertEqual(
                json.loads(path.read_text()), ["2609.00001", "2609.00002"]
            )

    def test_published_ids_are_extracted_from_review_pages_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki = Path(temp_dir)
            (wiki / "2026-09-27-Weekly-AI-Paper-Review.md").write_text(
                "- **arXiv**: [2609.00001](https://arxiv.org/abs/2609.00001)\n"
                "- **arXiv**: [2609.00002](https://arxiv.org/abs/2609.00002)\n",
                encoding="utf-8",
            )
            (wiki / "Home.md").write_text(
                "- **arXiv**: [ignored](https://arxiv.org/abs/ignored)\n",
                encoding="utf-8",
            )
            self.assertEqual(
                published_paper_ids(wiki), {"2609.00001", "2609.00002"}
            )

    def test_load_history_rejects_non_string_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "history.json"
            path.write_text('["2609.00001", 3]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_history(path)


if __name__ == "__main__":
    unittest.main()
