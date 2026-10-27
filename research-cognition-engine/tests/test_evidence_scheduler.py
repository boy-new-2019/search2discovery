"""Offline scheduler regression tests. These are framework tests, not experiments."""
import copy
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = pathlib.Path(os.environ.get('S2D_SKILL_ROOT', pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT / 'research-cognition-engine/scripts'))
import suite
import workflow_v61 as wf
import evidence_gain_scheduler as eg

class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.w = pathlib.Path(self.temp.name)
        (self.w/'output/batch').mkdir(parents=True)
        (self.w/'output/batch/state.json').write_text('{}')
        self.state = {'papers': [], 'frozen': None,
                      'selection': {'last_selected': list(range(10)), 'gaps': [{'theme': 'fairness', 'deficit': 1}]}}
        self.cfg = {'core_min': 6, 'core_target': 10, 'min_supplemental_pdfs': 0, 'min_supplemental_qualified': 0}
        self.patches = [patch.object(suite.discovery, 'status', return_value={'status':'MULTISOURCE_COVERAGE_PENDING','counts':{}}),
            patch.object(suite.original_batch, 'load_state', side_effect=lambda _: self.state),
            patch.object(suite.original_batch, 'available', return_value=[{'id':'paper'}]),
            patch.object(suite.original_batch, 'next_screen', return_value=None),
            patch.object(suite.original_batch, 'cfg_at', side_effect=lambda _:self.cfg),
            patch.object(suite.original_batch, 'can_seal', return_value=(True, [])),
            patch.object(suite.original_batch, 'supplementary_quality', return_value={'imported':0,'qualified':0}),
            patch.object(suite.original_batch, 'verify_sources')]
        for p in self.patches: p.start();self.addCleanup(p.stop)
    def test_coverage_gap_is_retained_not_seal_veto(self):
        r=suite.next_action(self.w);self.assertEqual(r['status'],'READY_TO_SEAL_ORIGINAL_V44')
        self.assertEqual(r['coverage_gaps'],self.state['selection']['gaps']);self.assertTrue(r['acquisition_gate']['pending'])
    def test_missing_reader_preserves_discovery_gate(self):
        (self.w/'output/batch/state.json').unlink();self.assertEqual(suite.next_action(self.w)['status'],'NEEDS_DISCOVERY')
    def test_minimum_is_hard(self):
        self.state['selection']['last_selected']=list(range(5));self.assertEqual(suite.next_action(self.w)['status'],'INSUFFICIENT_ELIGIBLE_CORE')
    def test_pending_s1_s2_cannot_seal(self):
        suite.original_batch.next_screen.return_value={'stage':'S2','id':'S2_X'}
        self.assertEqual(suite.next_action(self.w)['status'],'READ_SCREENING')
    def test_stagnated_strategy_blocks_new_automatic_screening(self):
        suite.original_batch.next_screen.return_value={'stage':'S2','id':'S2_X'}
        with patch.object(eg,'automatic_search_pause',return_value={'paused_gaps':{'fairness':{}}}):
            self.assertEqual(suite.next_action(self.w)['status'],'PAUSED_FOR_EVIDENCE_STRATEGY_REVIEW')
    def test_invalid_commits_do_not_seal(self):
        suite.original_batch.can_seal.return_value=(False,['missing independently verified receipt'])
        self.assertEqual(suite.next_action(self.w)['status'],'READER_SEAL_BLOCKED')
    def test_no_selection_cannot_seal(self):
        self.state['selection']=None;self.assertEqual(suite.next_action(self.w)['status'],'READY_FOR_ORIGINAL_V44_SELECT')
    def test_target_shortfall_is_hard(self):
        self.cfg['core_target']=11;self.assertEqual(suite.next_action(self.w)['status'],'READER_SEAL_BLOCKED')
    def test_supplemental_import_is_hard(self):
        self.cfg['min_supplemental_pdfs']=1;self.assertEqual(suite.next_action(self.w)['status'],'READER_SEAL_BLOCKED')
    def test_supplemental_qualification_is_hard(self):
        self.cfg['min_supplemental_qualified']=1;self.assertEqual(suite.next_action(self.w)['status'],'READER_SEAL_BLOCKED')
    def test_source_tampering_cannot_seal(self):
        suite.original_batch.verify_sources.side_effect=RuntimeError('changed PDF')
        with self.assertRaises(RuntimeError):suite.next_action(self.w)
    def core(self, reading, job=None):
        self.state['frozen']={'core_workspace':str(self.w)}
        self.enterContext(patch.object(suite.original_core,'env',return_value={}))
        self.enterContext(patch.object(suite.original_core,'run_status',return_value={'status':reading}))
        self.enterContext(patch.object(suite.original_core,'next_job',return_value=job))
    def test_reading_proceeds_without_claiming_catalog_complete(self):
        self.core('RUNNING',{'id':'R01_A_C001','type':'leaf','round':1})
        r=suite.next_action(self.w);self.assertEqual(r['status'],'READ_ORIGINAL_V44_CORE');self.assertTrue(r['acquisition_gate']['pending'])
    def test_veto_or_missing_final_audit_remains_blocking(self):
        for value in ('BLOCKED','AUDIT_FAILED','INCOMPLETE','COMPLETE_WITH_COVERAGE_GAPS'):
            with self.subTest(value=value):
                self.core(value);self.assertEqual(suite.next_action(self.w)['status'],'READER_NOT_APPROVED')
    def test_completed_reading_does_not_bypass_acquisition(self):
        self.core('COMPLETE');self.assertEqual(suite.next_action(self.w)['status'],'NEEDS_DISCOVERY')
    def test_scheduling_has_no_model_network_or_budget_write(self):
        before={str(p.relative_to(self.w)):p.read_bytes() for p in self.w.rglob('*') if p.is_file()}
        with patch.object(suite.desktop,'prepare',side_effect=AssertionError('no reservation')):
            suite.next_action(self.w)
        after={str(p.relative_to(self.w)):p.read_bytes() for p in self.w.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
    def test_workflow_prioritizes_core_over_optional_query(self):
        self.enterContext(patch.object(wf,'_readable',return_value=True))
        self.enterContext(patch.object(wf,'_commit_fingerprint',return_value=('',0,[])))
        self.enterContext(patch.object(wf,'_state',return_value={'last_evidence_fingerprint':'','last_evidence_job_ids':[]}))
        self.enterContext(patch.object(wf,'_v5_fingerprint',return_value=''))
        self.enterContext(patch.object(wf,'_question_next',side_effect=AssertionError('optional query must not starve core')))
        self.assertEqual(wf.choose(self.w)['status'],'READY_TO_SEAL_ORIGINAL_V44')

class GainTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.w=pathlib.Path(self.temp.name)
        p=self.w/'commit.json';p.write_text('{"status":"COMMITTED"}')
        self.artifacts=[{'path':'commit.json','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}]
    def event(self,n,gain=0,gap='fairness',strategy='lexical'):
        return {'batch_id':str(n),'gap_id':gap,'strategy':strategy,'effective_gain':gain,
                'gain_basis':'COMMITTED_INDEPENDENT_SCREENING_TARGET_GAP','artifacts':self.artifacts}
    def record(self,*args,**kwargs): return eg.record_batch(self.w,self.event(*args,**kwargs))
    def test_two_zero_batches_pause(self):
        self.assertFalse(self.record(1)['gaps']['fairness']['paused']);self.assertTrue(self.record(2)['gaps']['fairness']['paused'])
    def test_repeated_batch_is_idempotent(self):
        self.record(1);self.record(1);self.assertEqual(eg.status(self.w)['gaps']['fairness']['consecutive_zero_gain'],1)
    def test_conflicting_resubmission_rejected(self):
        self.record(1)
        with self.assertRaises(ValueError):self.record(1,1)
    def test_unrelated_gain_does_not_reset_gap(self):
        self.record(1);self.record(2,1,'occlusion');self.assertTrue(self.record(3)['gaps']['fairness']['paused'])
    def test_actual_target_gain_resets_zero_streak(self):
        self.record(1);self.record(2,1);self.assertEqual(self.record(3)['gaps']['fairness']['consecutive_zero_gain'],1)
    def test_unknown_is_review_not_automatic_zero(self):
        row=self.record(1,None)['gaps']['fairness'];self.assertTrue(row['paused']);self.assertEqual(row['consecutive_zero_gain'],0)
    def test_strategy_renaming_cannot_evade_gap_pause(self):
        self.record(1,strategy='titles');self.assertTrue(self.record(2,strategy='literal')['gaps']['fairness']['paused'])
    def test_changed_artifact_blocks_scheduling(self):
        self.record(1);(self.w/'commit.json').write_text('{"status":"PENDING"}')
        with self.assertRaises(ValueError):eg.status(self.w)
    def test_uncommitted_receipt_rejected(self):
        (self.w/'commit.json').write_text('{"status":"PENDING"}');self.artifacts[0]['sha256']=hashlib.sha256((self.w/'commit.json').read_bytes()).hexdigest()
        with self.assertRaises(ValueError):self.record(1)
    def test_pause_does_not_create_quota_or_model_task(self):
        self.record(1);self.record(2);self.assertIsNotNone(eg.automatic_search_pause(self.w))
        self.assertFalse((self.w/'output/native').exists())

if __name__=='__main__': unittest.main(verbosity=2)
