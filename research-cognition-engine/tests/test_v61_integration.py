"""v6.1 offline-only integration with the actual original v4.4/v5/v6 stack."""
from __future__ import annotations
import hashlib
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
for p in (ROOT,ROOT/'research-cognition-engine'/'scripts',ROOT/'paper-discovery-preflight'/'scripts',
          ROOT/'batch-paper-deepread-desktop'/'scripts',ROOT/'batch-paper-deepread-desktop'/'tests'):
    if str(p) not in sys.path:sys.path.insert(0,str(p))
import install_v6
import research_suite as full
import store,question_retrieval as qsearch,workflow_v61 as wf
from tests_original_merge import FullOriginalMergeTests,_configure_test

GOAL='Research in autonomous driving under partially observable conditions with limited evidence memory, prediction and decision. Confirmed methods are frozen.'


def api_work(i, when='2026-05-21',title=None, doi=None):
    return {'id':f'https://openalex.org/W{i}',
            'display_name':title or 'Task-aware memory revision in autonomous driving: Evidence for long-range planning',
            'publication_date':when,'type':'article',
            'doi':doi or f'https://doi.org/10.2222/{i}',
            'authorships':[{'author':{'display_name':'Researcher X'}}],
            'primary_location':{'source':{'display_name':'IEEE Transactions on Intelligent Transportation Systems'}},
            'best_oa_location':{'pdf_url':'https://example.org/read.pdf','landing_page_url':'https://example.org/paper'},
            'open_access':{'is_oa':True},'cited_by_count':17,
            'abstract_inverted_index':{'memory':[0], 'autonomous':[1], 'driving':[2]}}


class FakeOpenAlex:
    key=False
    def __init__(self,result=None,raise_error=False):
        self.calls=[];self.data=result if result is not None else [api_work(38102)]
        self.raise_error=raise_error
    def query(self,q,start,end,page):
        self.calls.append((q,start,end,page))
        if self.raise_error:raise RuntimeError('OFFLINE simulated provider fail')
        return self.data,{'rate_remaining':'offline fixture'}


class V61OriginalStack(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='rce-v61-')
        self.ws=pathlib.Path(self.t.name)
        (self.ws/'goal.md').write_text(GOAL,'utf8')
        self.assertEqual(install_v6.install(self.ws)['status'],'FULL_STACK_INSTALLED')
        self.assertEqual(full.initialize(self.ws)['status'],'INSTALL_READY')
    def tearDown(self):self.t.cleanup()
    def _q(self,qid='Q1',text='How does task-aware belief revision improve historical memory under partial observation for autonomous driving?'):
        with store.connect(self.ws) as c:
            c.execute('INSERT INTO questions VALUES(?,?,?,?,?,?,?)',(qid,text,.85,.90,'world-action','OPEN',store.utc()))

    def test_plan_three_year_windows_and_no_quota_forgery(self):
        self._q()
        before=(self.ws/'output/discovery_preflight/state.json').read_bytes() if (self.ws/'output/discovery_preflight/state.json').exists() else None
        p=qsearch.plan(self.ws)
        self.assertEqual(p['status'],'QUESTION_SEARCH_PLAN_READY')
        self.assertEqual(list(dict.fromkeys(r['band'] for r in p['queries'])),['RECENT_3Y','EXTENDED_3_TO_5Y','FOUNDATIONAL_OLDER'])
        self.assertEqual(p['questions_considered'],1)
        fake=FakeOpenAlex()
        with self.assertRaisesRegex(ValueError,'--online'):qsearch.search(self.ws,online=False,fetcher=fake)
        self.assertEqual(fake.calls,[])
        result=qsearch.search(self.ws,online=True,max_requests=1,fetcher=fake)
        self.assertEqual(result['new_bibliographic_works'],1)
        self.assertTrue(result['v5_disjoint_catalogue_untouched'])
        self.assertEqual(len(fake.calls),1)
        with store.connect(self.ws) as c:
            doc=c.execute('SELECT * FROM works WHERE work_id=?',('https://openalex.org/W38102',)).fetchone()
            self.assertEqual(doc['source_status'],'BIB_ONLY')
            self.assertEqual(doc['category'],'question_candidate')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM claims').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM question_papers').fetchone()[0],1)
        after=(self.ws/'output/discovery_preflight/state.json').read_bytes() if (self.ws/'output/discovery_preflight/state.json').exists() else None
        self.assertEqual(before,after)
        self.assertEqual(qsearch.plan(self.ws)['completed_queries'],1)
        self.assertEqual(qsearch.search(self.ws,online=True,max_requests=1,fetcher=FakeOpenAlex()).get('new_bibliographic_works'),0)

    def test_duplicate_by_doi_preserves_original_catalogue_identity(self):
        self._q()
        with store.connect(self.ws) as c:
            c.execute('INSERT INTO works VALUES(?,?,?,?,?,?,?,?,?)',
                      ('https://openalex.org/W900','Original study title','core','10.2222/38102',2025,'Journal','', 'fixture','BIB_ONLY'))
        resp=qsearch.search(self.ws,online=True,max_requests=1,fetcher=FakeOpenAlex())
        self.assertEqual(resp['new_bibliographic_works'],0)
        self.assertEqual(resp['known_metadata_duplicates'],1)
        with store.connect(self.ws) as c:
            pair=c.execute('SELECT work_id,search_openalex_id FROM question_papers').fetchone()
            self.assertEqual(pair['work_id'],'https://openalex.org/W900')
            self.assertEqual(pair['search_openalex_id'],'https://openalex.org/W38102')

    def test_chinese_question_requires_reviewed_query_and_goal_signature(self):
        self._q(text='如何根据当前观测证据修订有限容量的历史状态以改善驾驶动作？')
        p=qsearch.plan(self.ws)
        self.assertEqual(p['status'],'QUERY_REVIEW_REQUIRED')
        self.assertEqual(p['queries'],[])
        self.assertEqual(wf.choose(self.ws)['status'],'NEEDS_QUESTION_QUERY_REVIEW')
        reviewed={'schema_version':1,'goal_sha':qsearch._goal_sha(self.ws),
                  'questions':[{'question_id':'Q1','question_sha':store.hashobj('如何根据当前观测证据修订有限容量的历史状态以改善驾驶动作？'),
                                'queries':['task-aware historical evidence memory revision autonomous driving']} ]}
        store.write(qsearch.root(self.ws)/'reviewed_queries.json',reviewed)
        self.assertEqual(qsearch.plan(self.ws)['status'],'QUESTION_SEARCH_PLAN_READY')
        self.assertEqual(qsearch.search(self.ws,online=True,max_requests=1,fetcher=FakeOpenAlex())['requests'],1)
        (self.ws/'goal.md').write_text(GOAL+' Major change unapproved.','utf8')
        with self.assertRaisesRegex(ValueError,'Macro research goal changed'):qsearch.plan(self.ws)

    def test_failed_api_budget_counts_retries_and_resumable(self):
        self._q()
        r=qsearch.search(self.ws,online=True,max_requests=1,fetcher=FakeOpenAlex(raise_error=True))
        self.assertEqual(r['status'],'QUESTION_SEARCH_PARTIAL_ERRORS')
        with store.connect(self.ws) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM question_query_attempts').fetchone()[0],1)
            self.assertEqual(c.execute("SELECT status FROM question_queries").fetchone()[0],'ERROR')
        self.assertEqual(qsearch.search(self.ws,online=True,max_requests=1,fetcher=FakeOpenAlex())['requests'],1)
        self.assertEqual(qsearch.plan(self.ws)['completed_queries'],1)
        with store.connect(self.ws) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM question_query_attempts').fetchone()[0],2)

    def test_scheduler_pauses_without_network_and_can_resume_after_search(self):
        self._q()
        self.assertEqual(wf.choose(self.ws)['status'],'NEEDS_QUESTION_DRIVEN_SEARCH')
        no=wf.run(self.ws,max_steps=3)
        self.assertEqual(no['status'],'PAUSED_FOR_PERMISSION_OR_EXTERNAL_WORK')
        self.assertEqual(no['performed'],[])
        self.assertEqual(wf._state(self.ws)['research_goal_sha256'],store.hashbytes((self.ws/'goal.md').read_bytes()))
        qsearch.search(self.ws,online=True,max_requests=3,fetcher=FakeOpenAlex())
        # Existing reader/goal state untouched; may still want more foundation queries.
        self.assertIn(wf.choose(self.ws)['status'],('NEEDS_QUESTION_DRIVEN_SEARCH','NEEDS_DISCOVERY'))
        self.assertEqual(wf.auto_sync(self.ws)['status'],'NO_COMMITTED_CORE_EVIDENCE')
        self.assertEqual(wf.run(self.ws,max_steps=2)['status'],'PAUSED_FOR_PERMISSION_OR_EXTERNAL_WORK')

    def test_question_find_then_v5_catalogue_later_reconciles_without_overwriting(self):
        self._q()
        qsearch.search(self.ws,online=True,max_requests=1,fetcher=FakeOpenAlex())
        wid='https://openalex.org/W38102'
        library={'selected':{'core':[{'id':wid,'title':'Task-aware memory revision in autonomous driving: Evidence for long-range planning',
                             'doi':'10.2222/38102','year':2026,'venue':'IEEE Transactions on Intelligent Transportation Systems'}],
                             'related':[],'inspiration':[]}}
        store.write(self.ws/'output/discovery_preflight/paper_library.json',library)
        first=wf.sync_discovery(self.ws)
        self.assertEqual(first['status'],'V5_CATALOGUE_AND_SOURCE_SYNCED')
        self.assertEqual(first['question_promoted_to_v5'],1)
        second=wf.sync_discovery(self.ws)
        self.assertEqual(second['status'],'V5_ALREADY_SYNCED')
        with store.connect(self.ws) as c:
            self.assertEqual(c.execute('SELECT category FROM works WHERE work_id=?',(wid,)).fetchone()[0],'core')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM question_papers WHERE work_id=?',(wid,)).fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM claims').fetchone()[0],0)

    def test_unified_local_auto_prepares_real_reader_job_and_stops_for_app(self):
        _configure_test(self.ws)
        from tests_original_merge import TEXT
        f=self.ws/'input'/'paper.md'
        f.parent.mkdir(parents=True,exist_ok=True)
        f.write_text(TEXT,'utf8')
        out=wf.run(self.ws,max_steps=4,allow_incomplete_discovery=True,
                   allow_ingest=True,prepare_native=True)
        self.assertEqual(out['status'],'PAUSED_FOR_PERMISSION_OR_EXTERNAL_WORK')
        actions=[x['action'] for x in out['performed']]
        self.assertEqual(actions,['NEEDS_ORIGINAL_V44_INGEST','NEEDS_V5_EVIDENCE_SYNC','PREPARE_NATIVE_READER_TASK'])
        self.assertEqual(wf.choose(self.ws,allow_incomplete_discovery=True)['status'],'WAIT_FOR_NATIVE_READER_SUBAGENTS')
        self.assertEqual(wf.run(self.ws,max_steps=3,allow_incomplete_discovery=True)['performed'],[])
        manifest=self.ws/'output/native/tasks/S1_B00001/manifest.json'
        self.assertTrue(manifest.is_file())

    def test_non_tamper_install_upgrade_and_original_v44_manifest(self):
        self.assertEqual(full.doctor(self.ws)['status'],'ORIGINAL_V44_VERIFIED')
        path=self.ws/'.agents/skills/research-cognition-engine/scripts/workflow_v61.py'
        self.assertTrue(path.is_file())
        (self.ws/'output'/'protected.txt').write_text('CANNOT OVERWRITE','utf8')
        (self.ws/'input'/'protected.md').write_text('CANNOT OVERWRITE','utf8')
        self.assertEqual(install_v6.install(self.ws)['status'],'FULL_STACK_INSTALLED')
        self.assertEqual((self.ws/'input'/'protected.md').read_text(),'CANNOT OVERWRITE')
        self.assertEqual((self.ws/'output'/'protected.txt').read_text(),'CANNOT OVERWRITE')


class V61OriginalEvidence(unittest.TestCase):
    def setUp(self):
        self.origin=FullOriginalMergeTests('test_clean_one_archive_all_originals')
        self.origin.setUp()
        self.ws=self.origin.ws
    def tearDown(self):self.origin.tearDown()
    def test_auto_sync_original_commits_and_idempotency(self):
        self.origin._fully_read()
        first=wf.auto_sync(self.ws)
        self.assertEqual(first['status'],'EVIDENCE_AUTO_SYNCED')
        self.assertGreater(first['new_claims'],0)
        second=wf.auto_sync(self.ws)
        self.assertEqual(second['status'],'EVIDENCE_ALREADY_SYNCED')
        with store.connect(self.ws) as c:count=c.execute('SELECT COUNT(*) FROM claims').fetchone()[0]
        self.assertEqual(wf.auto_sync(self.ws,force=True)['status'],'EVIDENCE_AUTO_SYNCED')
        with store.connect(self.ws) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM claims').fetchone()[0],count)
    def test_frozen_original_without_any_question_search_table_can_choose(self):
        self.origin._fully_read()
        first=wf.auto_sync(self.ws)
        self.assertEqual(first['status'],'EVIDENCE_AUTO_SYNCED')
        wf.sync_discovery(self.ws)
        choice=wf.choose(self.ws,allow_incomplete_discovery=True)
        self.assertIn(choice['status'],('READY_FOR_RCE_CYCLE','NEEDS_RCE_INIT','PREPARE_RCE_NATIVE_TASK',
                                       'SCIENTIFIC_RECOMMENDATION_PENDING_USER_APPROVAL'))
        with store.connect(self.ws) as c:
            self.assertIsNotNone(c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='question_papers'").fetchone())

    def test_disappearing_original_commits_cannot_erase_verified_provenance(self):
        self.origin._fully_read()
        self.assertEqual(wf.auto_sync(self.ws)['status'],'EVIDENCE_AUTO_SYNCED')
        task_dir=self.ws/'output/native/tasks'
        for folder in task_dir.iterdir():
            if folder.is_dir() and folder.name.startswith('R0') and '_C' in folder.name:
                (folder/'commit.json').unlink(missing_ok=True)
        with self.assertRaises(ValueError):
            wf.choose(self.ws,allow_incomplete_discovery=True)
        with self.assertRaises(ValueError):
            wf.auto_sync(self.ws)

    def test_reader_commit_wrong_hash_stops_next_sync(self):
        self.origin._fully_read()
        wf.auto_sync(self.ws)
        old=wf._state(self.ws)['last_evidence_fingerprint']
        folder=next(x for x in (self.ws/'output/native/tasks').iterdir() if x.name.startswith('R01_') and '_C001' in x.name)
        receipt=next((folder/'receipts').glob('*.json'))
        receipt.write_text('TAMPERED','utf8')
        with self.assertRaises((ValueError,RuntimeError,KeyError,json.JSONDecodeError)):
            wf.auto_sync(self.ws)
        self.assertEqual(wf._state(self.ws)['last_evidence_fingerprint'],old)

if __name__=='__main__':unittest.main()
