"""Offline v6.5 regressions: deterministic round review & non-wasteful decisions."""
from __future__ import annotations
import json
import pathlib
import sys
import unittest
import tempfile
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[2]
for p in (ROOT,ROOT/'research-cognition-engine'/'scripts',ROOT/'batch-paper-deepread-desktop'/'scripts'):
    if str(p) not in sys.path:sys.path.insert(0,str(p))
import install_v6
import round_intelligence as rr
import store,engine,rce
from tests_original_merge import FullOriginalMergeTests


class CoreRoundReports(unittest.TestCase):
    def setUp(self):
        self.fx=FullOriginalMergeTests('test_clean_one_archive_all_originals')
        self.fx.setUp()
        self.ws=self.fx.ws
    def tearDown(self):self.fx.tearDown()

    def test_covers_s1_s2_and_five_rounds_replay_is_free_and_preserves_outputs(self):
        self.fx._fully_read()
        result=rr.refresh(self.ws)
        self.assertEqual(result['model_calls'],0)
        self.assertEqual(len(result['new_reports']),7,result)
        self.assertEqual(len([x for x in result['new_reports'] if x.startswith('SCREEN_')]),2)
        self.assertEqual(len([x for x in result['new_reports'] if x.startswith('DEEP_')]),5)
        self.assertFalse(result['incomplete_rounds'])
        key=next(x for x in result['new_reports'] if x.endswith('R05'))
        m=store.read(rr.home(self.ws)/'manifest.json')
        path=self.ws/m['entries'][key]['md_path']
        before=path.read_bytes()
        again=rr.refresh(self.ws)
        self.assertEqual(again['new_reports'],[])
        self.assertEqual(path.read_bytes(),before)
        report=path.read_text('utf8')
        self.assertIn('Source-page quotations',report)
        self.assertIn('Unresolved question',report)
        self.assertIn('R05',path.parent.name)

    def test_each_completed_round_only_before_next_and_no_fake_scientific_claims(self):
        from tests_original_merge import _configure_test, TEXT, _submit
        import batch,deepread as core,desktop_bridge as app
        self.fx._install()
        _configure_test(self.ws)
        (self.ws/'input'/'StudyA.md').write_text(TEXT,'utf8')
        batch.ingest(self.ws)
        # Not even screening stage complete before native experts submit.
        self.assertEqual(rr.refresh(self.ws)['new_reports'],[])
        while True:
            job=batch.next_screen(self.ws,batch.load_state(self.ws))
            if job is None:break
            info=app.prepare(self.ws);_submit(self.ws,info)
        result=rr.refresh(self.ws)
        self.assertEqual(len(result['new_reports']),2)
        batch.select_core(self.ws,batch.load_state(self.ws))
        sub=batch.seal(self.ws,batch.load_state(self.ws));ctx=core.env(sub)
        one=app.prepare(self.ws)
        self.assertEqual(one['phase'],'CORE')
        _submit(self.ws,one,ctx)
        self.assertFalse(any(x.startswith('DEEP_') for x in rr.refresh(self.ws)['new_reports']))

    def test_tamper_report_or_receipt_is_blocked_not_overwritten(self):
        ctx=self.fx._fully_read();rr.refresh(self.ws)
        m=store.read(rr.home(self.ws)/'manifest.json')
        key=next(x for x in m['entries'] if x.endswith('R01'))
        path=self.ws/m['entries'][key]['md_path']
        path.write_text('FAKE GOOD NEWS','utf8')
        with self.assertRaisesRegex(ValueError,'Committed historical research report'):rr.refresh(self.ws)
        self.assertEqual(path.read_text('utf8'),'FAKE GOOD NEWS')
        # Also ensure compromised original receipts cannot be made into a new report.
        with self.assertRaisesRegex(ValueError,'Committed historical research report'):rr.refresh(self.ws)

    def test_original_source_disappears_fail_closed(self):
        self.fx._fully_read()
        rr.refresh(self.ws)
        (self.ws/'input'/'StudyA.md').unlink()
        with self.assertRaises((ValueError,RuntimeError)):rr.refresh(self.ws)


class EfficiencyJudgement(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ws=pathlib.Path(self.tmp.name)
        (self.ws/'goal.md').write_text('Research partially observable driving tasks, belief state and limited evidence memory. All confirmed algorithms remain frozen.','utf8')
        install_v6.install(self.ws)
        rce.init(self.ws)
    def tearDown(self):self.tmp.cleanup()
    def _completed(self):
        state=engine.get_state(self.ws)
        state['cycles']=[{'id':'RC0001','stage':'COMPLETE','completed_stages':list(engine.STAGES)}]
        store.write(engine.statefile(self.ws),state)

    def test_no_past_cycle_never_waives_quality_stages(self):
        result=rr.next_decision(self.ws)
        self.assertEqual(result['decision'],'CONTINUE_REQUIRED_STAGES')

    def test_completed_cycle_never_automatically_repeats_without_new_evidence(self):
        self._completed()
        self.assertEqual(rr.record_cycle_baseline(self.ws)['status'],'CYCLE_BASELINE_SAVED')
        self.assertEqual(rr.record_cycle_baseline(self.ws)['status'],'BASELINE_ALREADY_RECORDED')
        check=rr.next_decision(self.ws)
        self.assertEqual(check['decision'],'DO_NOT_START_RESEARCH_CYCLE')
        self.assertEqual(check['new_claims'],0)
        self.assertEqual(check['model_calls'],0)
        self.assertTrue((rr.home(self.ws)/'latest_next_decision.json').exists())

    def test_added_metadata_alone_does_not_force_expensive_cycle(self):
        self._completed();rr.record_cycle_baseline(self.ws)
        with store.connect(self.ws) as c:
            c.execute('INSERT INTO works(work_id,title,category,doi,year,venue,url,record_sha) VALUES (?,?,?,?,?,?,?,?)',
                      ('W1','Bibliography only','related','',2026,'','','HASH'))
        self.assertEqual(rr.next_decision(self.ws)['decision'],'DO_NOT_START_RESEARCH_CYCLE')

    def test_new_source_triggers_triage_not_auto_spending(self):
        self._completed();rr.record_cycle_baseline(self.ws)
        p=self.ws/'source.md';p.write_text('test scientific source material. '*70,'utf8')
        with store.connect(self.ws) as c:
            c.execute('INSERT INTO works(work_id,title,category,doi,year,venue,url,record_sha) VALUES (?,?,?,?,?,?,?,?)',
                      ('W1','Scientific verified source','core','',2026,'','','HASH'))
        store.import_source(self.ws,'W1',p)
        out=rr.next_decision(self.ws)
        self.assertEqual(out['decision'],'HUMAN_OR_AGENT_TRIAGE_FIRST')
        self.assertEqual(out['new_sources'],1)

    def test_legacy_finished_cycle_requires_provenance_review(self):
        self._completed()
        self.assertEqual(rr.next_decision(self.ws)['decision'],'PAUSE_AND_REVIEW')

    def test_corrupted_registered_source_blocks_scientific_reuse(self):
        self._completed()
        w=self.ws/'paper.md';w.write_text('Some validated source statement '*70,'utf8')
        with store.connect(self.ws) as c:
            c.execute('INSERT INTO works(work_id,title,category,doi,year,venue,url,record_sha) VALUES (?,?,?,?,?,?,?,?)',
                      ('W2','Found paper','core','',2026,'','','HASH2'))
        store.import_source(self.ws,'W2',w)
        rr.record_cycle_baseline(self.ws)
        w.write_text(w.read_text()+'changed','utf8')
        with self.assertRaises(ValueError):rr.next_decision(self.ws)



if __name__=='__main__':unittest.main()

class CognitionRoundReports(unittest.TestCase):
    def setUp(self):
        source=ROOT/'research-cognition-engine'/'tests'
        if str(source) not in sys.path:sys.path.insert(0,str(source))
        from test_e2e import CognitionE2E
        self.fx=CognitionE2E('test_complete_research_cycle_with_real_anchor_validation')
        self.fx.setUp()
        self.ws=self.fx.ws
    def tearDown(self):self.fx.tearDown()

    def _finish(self):
        engine.new_cycle(self.ws,self.fx.config)
        for stage in engine.STAGES:
            task=self.fx.task()
            self.fx.submit(task,self.fx.response)

    def test_all_seven_stages_have_precise_reports_and_independent_novelty(self):
        self._finish()
        result=rr.refresh(self.ws)
        self.assertEqual(len(result['new_reports']),7,result)
        self.assertTrue((rr.home(self.ws)/'INDEX.md').is_file())
        self.assertIn('COGNITION_RC0001_NOVELTY',result['new_reports'])
        index=store.read(rr.home(self.ws)/'manifest.json')
        novelty=self.ws/index['entries']['COGNITION_RC0001_NOVELTY']['md_path']
        text=novelty.read_text('utf8')
        self.assertIn('rce_skeptic_astra',text)
        self.assertIn('rce_novelty_sol',text)
        self.assertIn('UNCERTAIN',text)
        self.assertEqual(rr.refresh(self.ws)['new_reports'],[])
        self.assertEqual(rr.record_cycle_baseline(self.ws)['status'],'CYCLE_BASELINE_SAVED')
        self.assertEqual(rr.next_decision(self.ws)['decision'],'DO_NOT_START_RESEARCH_CYCLE')

    def test_cognition_report_tampering_refuses_silent_overwrite(self):
        self._finish();rr.refresh(self.ws)
        index=store.read(rr.home(self.ws)/'manifest.json')
        s=self.ws/index['entries']['COGNITION_RC0001_MECHANISM']['md_path']
        s.write_text('FAKE AI Summary','utf8')
        with self.assertRaisesRegex(ValueError,'Committed historical research report'):rr.refresh(self.ws)

    def test_genuine_direct_cli_cycle_gate_does_not_refire_without_changes(self):
        self._finish();rr.record_cycle_baseline(self.ws)
        from contextlib import redirect_stdout,redirect_stderr
        from io import StringIO
        o=StringIO();e=StringIO()
        with redirect_stdout(o),redirect_stderr(e):
            code=rce.execute(['new-cycle','--workspace',str(self.ws)])
        self.assertEqual(code,2)
        self.assertIn('REFUSE_REDUNDANT_RESEARCH_CYCLE',e.getvalue())
        self.assertEqual(len(engine.get_state(self.ws)['cycles']),1)


class AutomaticCommitHooks(unittest.TestCase):
    def test_native_launcher_creates_reports_after_original_completed_jobs(self):
        from tests_original_merge import FullOriginalMergeTests
        from native_v44_launcher import main as launch
        import contextlib,io
        fixture=FullOriginalMergeTests('test_clean_one_archive_all_originals')
        fixture.setUp()
        try:
            fixture._fully_read()
            # Simulate a restart in Codex: wrapper checks all original committed stages.
            sink=io.StringIO()
            with contextlib.redirect_stdout(sink):
                code=launch(['prepare','--workspace',str(fixture.ws)])
            self.assertEqual(code,0)
            self.assertEqual(len(store.read(rr.home(fixture.ws)/'manifest.json')['entries']),7)
            self.assertTrue((rr.home(fixture.ws)/'efficiency_dashboard.md').is_file())
            self.assertIn('ROUND_REPORTS_UPDATED',str(rr.refresh(fixture.ws)['status']))
        finally:fixture.tearDown()

    def test_rce_commit_emits_map_report_from_cli_without_extra_subagents(self):
        import contextlib,io
        source=ROOT/'research-cognition-engine'/'tests'
        if str(source) not in sys.path:sys.path.insert(0,str(source))
        from test_e2e import CognitionE2E
        fixture=CognitionE2E('test_complete_research_cycle_with_real_anchor_validation')
        fixture.setUp()
        try:
            w=fixture.ws
            engine.new_cycle(w,fixture.config)
            task=fixture.task();role=task['roles'][0]
            p=engine.taskdir(w,task['job_id'])/'model.json'
            store.write(p,fixture.response('MAP',role))
            engine.collect(w,task['job_id'],role,p,'valid-native-map-'+role)
            before=rce.budget(w,fixture.config)['reserved_assignments']
            with contextlib.redirect_stdout(io.StringIO()) as out:
                status=rce.execute(['commit','--workspace',str(w),'--job-id',task['job_id']])
            self.assertEqual(status,0,out.getvalue())
            self.assertIn('COGNITION_RC0001_MAP',store.read(rr.home(w)/'manifest.json')['entries'])
            self.assertEqual(rce.budget(w,fixture.config)['reserved_assignments'],before)
        finally:fixture.tearDown()
