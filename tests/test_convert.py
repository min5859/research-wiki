import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import convert


class ConvertCleanupTests(unittest.TestCase):
    def test_existing_complete_markdown_deletes_redundant_pdf(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            markdown_dir = temp / "markdown"
            markdown_dir.mkdir()
            pdf = temp / "paper.pdf"
            pdf.write_bytes(b"pdf")
            expected = markdown_dir / "2609.00001.md"
            expected.write_text("x" * 101, encoding="utf-8")

            with patch.object(convert, "MD_DIR", markdown_dir), patch.object(
                convert.pymupdf4llm, "to_markdown"
            ) as to_markdown:
                result = convert.convert_pdf(str(pdf), "2609.00001")

            self.assertEqual(result, expected)
            self.assertFalse(pdf.exists())
            to_markdown.assert_not_called()

    def test_incomplete_markdown_keeps_pdf(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            markdown_dir = temp / "markdown"
            markdown_dir.mkdir()
            pdf = temp / "paper.pdf"
            pdf.write_bytes(b"pdf")
            (markdown_dir / "2609.00002.md").write_text("short", encoding="utf-8")

            with patch.object(convert, "MD_DIR", markdown_dir):
                convert.delete_pdf_if_converted(str(pdf), "2609.00002")

            self.assertTrue(pdf.exists())

    def test_successful_conversion_deletes_pdf_after_writing_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            markdown_dir = temp / "markdown"
            markdown_dir.mkdir()
            pdf = temp / "paper.pdf"
            pdf.write_bytes(b"pdf")

            with patch.object(convert, "MD_DIR", markdown_dir), patch.object(
                convert.pymupdf4llm, "to_markdown", return_value="한" * 101
            ):
                result = convert.convert_pdf(str(pdf), "2609.00003")

            self.assertEqual(result, markdown_dir / "2609.00003.md")
            self.assertFalse(pdf.exists())
            self.assertTrue(result.exists())


if __name__ == "__main__":
    unittest.main()
