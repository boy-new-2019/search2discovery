"""Integrated-v6 installation tests (replaces old v6 standalone assumptions).

V6 standalone originally assumed the reader MUST NOT be bundled; the user now
requires the exact original v4.4 reader to be installed by the same archive.
"""
from __future__ import annotations
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import install_v6

class InstallTests(unittest.TestCase):
    def test_non_destructive_original_reader_and_idempotent_install(self):
        with tempfile.TemporaryDirectory() as d:
            ws=pathlib.Path(d)
            (ws/'goal.md').write_text('Known immutable research contract',encoding='utf8')
            (ws/'input').mkdir();(ws/'input'/'important.md').write_text('Private data',encoding='utf8')
            one=install_v6.install(ws)
            self.assertEqual(one['status'],'FULL_STACK_INSTALLED')
            self.assertTrue(one['original_v44_source'])
            self.assertEqual(len(list((ws/'.codex/agents').glob('rce_*.toml'))),11)
            self.assertEqual(len(list((ws/'.codex/agents').glob('bpd_*.toml'))),16)
            self.assertTrue((ws/'.agents/skills/batch-paper-deepread-desktop/scripts/deepread.py').is_file())
            self.assertTrue((ws/'.agents/skills/research-cognition-engine/SKILL.md').is_file())
            self.assertTrue((ws/'.agents/skills/search2discovery/SKILL.md').is_file())
            self.assertEqual((ws/'input/important.md').read_text('utf8'),'Private data')
            two=install_v6.install(ws)
            self.assertEqual(two['status'],'FULL_STACK_INSTALLED')
            self.assertEqual(two['installed'],[])
            self.assertEqual(len(two['unchanged']),len(install_v6._check_bundle()))
    def test_upgrade_backups_and_preserves_project_data(self):
        with tempfile.TemporaryDirectory() as d:
            ws=pathlib.Path(d)
            (ws/'goal.md').write_text('Do not edit manuscript core',encoding='utf8')
            install_v6.install(ws)
            old=ws/'.agents/skills/research-cognition-engine/SKILL.md'
            old.write_text('OLD_RCE_SKILL_TO_BACKUP','utf8')
            (ws/'output').mkdir(exist_ok=True)
            (ws/'output'/'saved_result.md').write_text('External research results','utf8')
            blocked=install_v6.install(ws)
            self.assertEqual(blocked['status'],'BLOCKED_EXISTING_COMPONENTS_UNCHANGED')
            self.assertEqual(old.read_text('utf8'),'OLD_RCE_SKILL_TO_BACKUP')
            result=install_v6.install(ws,upgrade=True)
            self.assertEqual(result['status'],'FULL_STACK_INSTALLED')
            self.assertIn('research-cognition-engine',old.read_text('utf8'))
            backups=list((ws/'output'/'unified_v6_install_backups').rglob('SKILL.md'))
            self.assertTrue(any(p.read_text('utf8')=='OLD_RCE_SKILL_TO_BACKUP' for p in backups))
            self.assertEqual((ws/'output'/'saved_result.md').read_text('utf8'),'External research results')
            self.assertEqual((ws/'goal.md').read_text('utf8'),'Do not edit manuscript core')
    def test_original_reader_installed_in_one_package(self):
        with tempfile.TemporaryDirectory() as d:
            ws=pathlib.Path(d)
            result=install_v6.install(ws)
            self.assertEqual(result['status'],'FULL_STACK_INSTALLED')
            self.assertTrue((ws/'.agents/skills/batch-paper-deepread-desktop/SKILL.md').is_file())
            self.assertTrue((ws/'.agents/skills/paper-discovery-preflight/SKILL.md').is_file())
            self.assertTrue((ws/'.agents/skills/research-cognition-engine/SKILL.md').is_file())

if __name__=='__main__':unittest.main()
