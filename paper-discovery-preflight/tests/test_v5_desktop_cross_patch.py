"""Project-local Codex Desktop cross-domain compatibility checks for V5."""
from __future__ import annotations
import importlib.util
import pathlib
import sys
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import install_into_codex_project as installer
import paper_discovery as d


class DesktopCrossDomainCompatibility(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ws=pathlib.Path(self.tmp.name)
        self.main=self.ws/'.agents/skills/batch-paper-deepread-desktop'
        (self.main/'scripts').mkdir(parents=True)
        (self.main/'SKILL.md').write_text('---\nname: batch-paper-deepread-desktop\n---\n# Existing Main Skill\nKeep exact scientific quality rules.\n','utf8')
        self.native=self.ws/'native_config.json'
        d.write(self.native,{'cross_domain':{'enabled':True,'domains':['nobel_economics','philosophy']},
                             'budget':{'max_assignments_per_cycle':40},'keep_other_user_settings':'unchanged'})
        (self.ws/'goal.md').write_text('The frozen research topic is temporal occupancy prediction.','utf8')
        (self.ws/'input').mkdir()
        (self.ws/'input'/'old.pdf').write_bytes(b'PAPER_BYTES_NOT_TO_BE_REMOVED')
        self.script=self.main/'scripts'/'cross_domain.py'
        self.script.write_text('''from pathlib import Path
DEFAULT = {'domains':['nobel_economics','philosophy']}
DOMAIN_QUERIES = {'nobel_economics':['economic theory'],'philosophy':['knowledge justification']}
STAGES = ('AFTER_R2',)
def prefs(config):
    domains=config['domains']
    if len(domains) > 20:return False
    return set(domains).issubset(DOMAIN_QUERIES)
''','utf8')
    def tearDown(self):self.tmp.cleanup()

    def test_installer_extends_main_native_pool_without_changing_existing_work(self):
        before_script=self.script.read_bytes()
        before_native=self.native.read_bytes()
        result=installer.install(self.ws)
        self.assertEqual(result['main_cross_domain']['status'],'MAIN_CROSS_DOMAIN_WIDENED')
        self.assertTrue((self.main/'scripts/cross_domain.py.before_v5_wide').exists())
        self.assertEqual((self.main/'scripts/cross_domain.py.before_v5_wide').read_bytes(),before_script)
        self.assertEqual((self.ws/'native_config.json.before_v5_wide').read_bytes(),before_native)
        self.assertEqual(d.read(self.native)['keep_other_user_settings'],'unchanged')
        self.assertGreaterEqual(len(d.read(self.native)['cross_domain']['domains']),93)
        path=self.script
        spec=importlib.util.spec_from_file_location('test_generated_cross_domain',path)
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(mod.prefs(d.read(self.native)['cross_domain']))
        self.assertIn('musicology',mod.DOMAIN_QUERIES)
        self.assertIn('astronomy',mod.DOMAIN_QUERIES)
        self.assertIn('culinary_science',mod.DOMAIN_QUERIES)
        self.assertEqual((self.ws/'input'/'old.pdf').read_bytes(),b'PAPER_BYTES_NOT_TO_BE_REMOVED')
        self.assertEqual((self.ws/'goal.md').read_text('utf8'),'The frozen research topic is temporal occupancy prediction.')
        self.assertEqual(installer.extend_main_cross_domain(self.ws)['status'],'ALREADY_WIDE')

    def test_in_flight_tasks_cannot_be_reconfigured(self):
        tmp=self.ws/'output/native/tasks/JOB_UNFINISHED'
        tmp.mkdir(parents=True)
        d.write(tmp/'manifest.json',{'job_id':'JOB_UNFINISHED'})
        with self.assertRaises(ValueError):
            installer.extend_main_cross_domain(self.ws)
        self.assertEqual(d.read(self.native)['cross_domain']['domains'],['nobel_economics','philosophy'])
        self.assertNotIn(installer.MAIN_WIDE_MARKER,self.script.read_text('utf8'))

    def test_refuses_unknown_main_reader_schema(self):
        self.script.write_text('print("unexpected reader version")\n','utf8')
        with self.assertRaises(ValueError):
            installer.extend_main_cross_domain(self.ws)

if __name__=='__main__':unittest.main()
