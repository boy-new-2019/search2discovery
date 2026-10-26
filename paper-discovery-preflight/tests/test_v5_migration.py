"""v4.5 -> v5.0 metadata-preserving migration and Desktop installer.
All work records are synthetic and no network/LLM is used.
"""
from __future__ import annotations
import copy
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import paper_discovery as engine
import install_into_codex_project as installer
from test_preflight import fake_work


class V5MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ws=pathlib.Path(self.tmp.name)
        self.old=engine.read(ROOT/'references'/'legacy_v45_config.example.json')
        self.old['as_of_date']='2026-10-25'
        (self.ws/'goal.md').write_text('Confirmed streaming 3D occupancy baseline and temporal memory.','utf-8')
        (self.ws/'input').mkdir()
        (self.ws/'input'/'user_owned.pdf').write_bytes(b'USER_OWNED_PAPER_KEEP')
        (self.ws/'output').mkdir()
        (self.ws/'output'/'user_notes.md').write_text('USER_NOTES_KEEP','utf-8')
        engine.write(self.ws/'discovery_config.json',self.old)
        contract={'config_sha256':engine.sha(self.old),
                  'goal_sha256':engine.sha(engine.goal_contract(self.ws,self.old)),
                  'venue_shortlist_sha256':engine.sha(engine.read(ROOT/self.old['venue_shortlist_file'])),
                  'as_of_date':'2026-10-25'}
        paper=engine.work_normalized(fake_work('old-core',121,cat='core'),'core','','streaming occupancy')
        self.metadata=paper
        task='LEGACY_REQUEST_ALREADY_FINISHED'
        state={'schema_version':1,'version':'1.0.0','contract':contract,'created_at':'2026-10-25T00:00:00+00:00',
               'queries_done':{task:{'band':'RECENT_3Y','category':'core','domain':'','query':'streaming occupancy','page':1,'at':'2026-10-25'}},
               'windows_completed':['RECENT_3Y'],'catalog_commit_band':'RECENT_3Y',
               'works':{paper['id']:paper},'api_calls':7,'attempt_log':[{'status':'OK','task':task}],
               'download_log':{paper['id']:{'status':'FULLTEXT_READY','relative_path':'input/real_old.pdf','sha256':'a'*64}},
               'selection':{'OLD_LOCKED':'NOT_V5_COMPLIANT'},'last_status':'CATALOG_250_PLUS_COMPLETE'}
        engine.write(engine.root_out(self.ws)/'state.json',state)
        (engine.root_out(self.ws)/'discovery_report.md').write_text('LEGACY_RESEARCH_REPORT','utf-8')
        self.original_pdf=(self.ws/'input'/'user_owned.pdf').read_bytes()
        self.old_goal=(self.ws/'goal.md').read_bytes()
    def tearDown(self):self.tmp.cleanup()

    def test_explicit_migrate_preserves_all_raw_metadata_and_log(self):
        with self.assertRaisesRegex(ValueError,'migrate-v5'):
            engine.init(self.ws)
        migrated=engine.migrate_v5(self.ws)
        self.assertEqual(migrated['status'],'V5_MIGRATED_RESUME_NEW_FIELDS')
        self.assertEqual(migrated['retained_metadata_works'],1)
        self.assertEqual(migrated['retained_api_queries'],1)
        c=engine.config(self.ws)
        self.assertEqual(c['schema_version'],2)
        self.assertGreaterEqual(len(c['queries']['inspiration']),90)
        self.assertEqual(c['quotas'],self.old['quotas'])
        self.assertEqual(c['as_of_date'],'2026-10-25')
        current=engine.state_at(self.ws,c)
        self.assertEqual(current['api_calls'],7)
        self.assertIn(self.metadata['id'],current['works'])
        self.assertIn('LEGACY_REQUEST_ALREADY_FINISHED',current['queries_done'])
        self.assertEqual(current['download_log'][self.metadata['id']]['status'],'FULLTEXT_READY')
        self.assertIsNone(current['catalog_commit_band'])
        self.assertNotEqual(current['last_status'],'CATALOG_250_PLUS_COMPLETE')
        directory=pathlib.Path(migrated['backup_dir'])
        self.assertEqual((directory/'discovery_report.md').read_text('utf-8'),'LEGACY_RESEARCH_REPORT')
        self.assertEqual(engine.read(directory/'discovery_config.json')['schema_version'],1)
        self.assertEqual((self.ws/'goal.md').read_bytes(),self.old_goal)
        self.assertEqual((self.ws/'input'/'user_owned.pdf').read_bytes(),self.original_pdf)
        self.assertEqual((self.ws/'output'/'user_notes.md').read_text('utf-8'),'USER_NOTES_KEEP')
        self.assertEqual(engine.migrate_v5(self.ws)['status'],'ALREADY_V5')

    def test_migration_rejects_unsynced_previous_campaign_without_changes(self):
        statepath=engine.root_out(self.ws)/'state.json'
        oldstate=engine.read(statepath)
        oldstate['contract']['goal_sha256']='CHANGED'
        engine.write(statepath,oldstate)
        with self.assertRaises(ValueError):
            engine.migrate_v5(self.ws)
        self.assertEqual(engine.read(self.ws/'discovery_config.json')['schema_version'],1)
        self.assertEqual((self.ws/'goal.md').read_bytes(),self.old_goal)

    def test_user_oversized_domain_quota_requires_explicit_confirmation(self):
        custom=copy.deepcopy(self.old)
        custom['preferred_domains']={'philosophy':9}
        engine.write(self.ws/'discovery_config.json',custom)
        snap=engine.read(engine.root_out(self.ws)/'state.json')
        snap['contract']['config_sha256']=engine.sha(custom)
        engine.write(engine.root_out(self.ws)/'state.json',snap)
        with self.assertRaises(ValueError):
            engine.migrate_v5(self.ws)
        self.assertEqual(engine.read(self.ws/'discovery_config.json')['schema_version'],1)

    def test_main_skill_v45_marker_replaced_only_with_authorized_upgrade(self):
        folder=self.ws/'.agents/skills/paper-discovery-preflight'
        folder.mkdir(parents=True)
        (folder/'SKILL.md').write_text('# v4.5 OLD SKILL','utf-8')
        main=self.ws/'.agents/skills/batch-paper-deepread-desktop'
        main.mkdir(parents=True)
        original=('---\nname: batch-paper-deepread-desktop\ndescription: unchanged\n---\n'
                  '# Main Skill\nKEEP VERY IMPORTANT USER RESEARCH RULES\n'
                  +installer.MARKER+'\n## Old v4.5 integration block\n'+installer.END
                  +'\n## LAST SECTION PRESERVE ME\n')
        (main/'SKILL.md').write_text(original,'utf-8')
        result=installer.install(self.ws,upgrade=True)
        self.assertEqual(result['status'],'INSTALLED')
        self.assertTrue(result['main_skill_patched'])
        self.assertIsNotNone(result['migration'])
        target=(main/'SKILL.md').read_text('utf-8')
        self.assertIn('Mandatory v5 Discovery Preflight',target)
        self.assertIn('KEEP VERY IMPORTANT USER RESEARCH RULES',target)
        self.assertIn('LAST SECTION PRESERVE ME',target)
        self.assertEqual(target.count(installer.MARKER),1)
        self.assertTrue((main/'SKILL.md.before_discovery_v5').exists())
        self.assertTrue((self.ws/'.agents/skills/paper-discovery-preflight.old/SKILL.md').exists())
        self.assertEqual((self.ws/'input'/'user_owned.pdf').read_bytes(),self.original_pdf)
        self.assertEqual(engine.state_at(self.ws,engine.config(self.ws))['api_calls'],7)

if __name__=='__main__':unittest.main()
