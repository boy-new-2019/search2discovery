"""Public packaging and BSD-licensed PDF fallback regression tests (offline)."""
from __future__ import annotations

import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'research-cognition-engine' / 'scripts'))
sys.path.insert(0, str(ROOT / 'paper-discovery-preflight' / 'scripts'))

import install
import store
import paper_discovery


class Search2DiscoveryPublicTests(unittest.TestCase):
    def test_public_name_and_native_agents(self):
        self.assertEqual((ROOT / 'VERSION').read_text('utf8').strip(), '1.0.0')
        self.assertIn('name: search2discovery', (ROOT / 'search2discovery' / 'SKILL.md').read_text('utf8'))
        self.assertEqual(len(list((ROOT / '.codex/agents').glob('*.toml'))), 27)

    def test_full_clean_install_and_private_data_preservation(self):
        with tempfile.TemporaryDirectory() as temp:
            ws = pathlib.Path(temp)
            (ws / 'goal.md').write_text('Confidential research objective', encoding='utf8')
            (ws / 'input').mkdir()
            (ws / 'input' / 'notes.txt').write_text('PRIVATE INPUT MUST SURVIVE', encoding='utf8')
            installed = install.install(ws)
            self.assertEqual(installed['status'], 'FULL_STACK_INSTALLED')
            self.assertTrue((ws / '.agents/skills/search2discovery/SKILL.md').is_file())
            self.assertTrue((ws / '.agents/skills/research-cognition-engine/SKILL.md').is_file())
            self.assertEqual(len(installed['installed']), 31) # 4 Skills + 27 native agents
            again = install.install(ws)
            self.assertEqual(again['installed'], [])
            self.assertEqual((ws / 'input/notes.txt').read_text('utf8'), 'PRIVATE INPUT MUST SURVIVE')
            self.assertEqual((ws / 'goal.md').read_text('utf8'), 'Confidential research objective')

    def test_git_safety_docs_and_source_manifest(self):
        gitignore = (ROOT / '.gitignore').read_text('utf8')
        for text in ('goal.md', 'input/', 'output/', '.env', 'cross_domain_input/'):
            self.assertIn(text, gitignore)
        self.assertIn('MIT License', (ROOT / 'LICENSE').read_text('utf8'))
        self.assertIn('R3', (ROOT / 'README.md').read_text('utf8'))
        manifest = json.loads((ROOT / 'research-cognition-engine/references/original_v44_file_manifest.json').read_text('utf8'))
        self.assertEqual(len(manifest['skill_files_sha256']), 35)

    @staticmethod
    def synthetic_pdf_bytes() -> bytes:
        # A real single-page, extractable PDF created using pypdf alone.
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({
            NameObject('/Type'): NameObject('/Font'),
            NameObject('/Subtype'): NameObject('/Type1'),
            NameObject('/BaseFont'): NameObject('/Helvetica'),
        })
        fontref = writer._add_object(font)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): fontref})})
        stream = DecodedStreamObject()
        line = ('This public synthetic text only tests offline paper parsing without experiments. ' * 12)
        stream.set_data(f'BT /F1 12 Tf 50 720 Td ({line}) Tj ET'.encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
        out = io.BytesIO(); writer.write(out); return out.getvalue()

    def test_source_store_pypdf_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / 'synthetic.pdf'
            path.write_bytes(self.synthetic_pdf_bytes())
            with mock.patch.dict(sys.modules, {'fitz': None}):
                pages = store.source_pages(path)
            self.assertEqual(len(pages), 1)
            self.assertIn('offline paper parsing', pages[0])
            self.assertGreater(len(pages[0]), 500)

    def test_oa_pdf_validation_pypdf_fallback(self):
        data = self.synthetic_pdf_bytes()
        class Stream(io.BytesIO):
            def geturl(self): return 'https://example.org/oa-paper.pdf'
        class FakeOpener:
            def open(self, request, timeout): return Stream(data)
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.dict(sys.modules, {'fitz': None}), \
             mock.patch.object(paper_discovery, 'public_dns', return_value=True), \
             mock.patch.object(paper_discovery.urllib.request, 'build_opener', return_value=FakeOpener()):
            dst = pathlib.Path(temp) / 'paper.pdf'
            paper_discovery.download_pdf('https://example.org/oa-paper.pdf', dst, maxmb=2, minchars=500)
            self.assertEqual(dst.read_bytes(), data)

if __name__ == '__main__':
    unittest.main()
