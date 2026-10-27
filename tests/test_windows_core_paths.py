import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("longpath_reader", ROOT / "batch-paper-deepread-desktop/scripts/deepread.py")
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)

class CorePathTests(unittest.TestCase):
    def test_ordinary_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            reader.jwrite(path, {"evidence": "checked"})
            self.assertEqual(reader.jread(path), {"evidence": "checked"})
            self.assertEqual(reader.file_hash(path), hashlib.sha256(path.read_bytes()).hexdigest())

    def test_render_source_page_in_nested_core_directory(self):
        try:
            import fitz
        except ImportError:
            self.skipTest("Optional source-page renderer unavailable")
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "input").mkdir()
            with fitz.open() as doc:
                doc.new_page()
                doc.save(workspace / "input/source.pdf")
            run = workspace / ("nested-run-" * 20)
            ctx = {"run": run, "ws": workspace, "papers": [{"id": "paper-" * 12, "file": "source.pdf"}]}
            reader.render_pdf(ctx, "paper-" * 12, [1], 72)
            destination = reader.filesystem_path(run / "visual_pages" / ("paper-" * 12))
            png = destination / "p0001.png"
            self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            png.unlink()
            destination.rmdir()
            destination.parent.rmdir()
            destination.parent.parent.rmdir()

    @unittest.skipUnless(os.name == "nt", "Win32 extended-path regression")
    def test_nested_core_answer_and_receipt_over_max_path(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / ("core" * 20) / ("run" * 20)
            job_id = "R01_" + "a" * 110
            ctx = {"run": run}
            answer = reader.ans_path(ctx, job_id)
            receipt = reader.rec_path(ctx, job_id)
            self.assertGreater(len(str(run / "answers" / (job_id + ".json"))), 260)
            reader.jwrite(answer, {"id": job_id})
            reader.jwrite(receipt, {"answer_sha256": reader.file_hash(answer)})
            self.assertTrue(answer.exists())
            self.assertTrue(receipt.exists())
            self.assertEqual(reader.jread(answer)["id"], job_id)
            self.assertEqual(reader.jread(receipt)["answer_sha256"], reader.file_hash(answer))
            self.assertEqual(reader.filesystem_path(answer), answer)
            answer.unlink()
            receipt.unlink()
            answer.parent.rmdir()
            receipt.parent.rmdir()
            reader.filesystem_path(run).rmdir()
            reader.filesystem_path(run.parent).rmdir()

if __name__ == "__main__":
    unittest.main()
