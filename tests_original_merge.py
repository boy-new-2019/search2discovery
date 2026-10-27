"""Offline integration: user's byte-identical ORIGINAL v4.4 + v5 + v6.

Responses are synthetic fixtures. No genuine Codex models or scholarly claims are
verified by these tests; only task/evidence/installer invariants are validated.
"""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'batch-paper-deepread-desktop'/'scripts'))
sys.path.insert(0,str(ROOT/'research-cognition-engine'/'scripts'))
sys.path.insert(0,str(ROOT/'batch-paper-deepread-desktop'/'tests'))

import install_v6
import research_suite as suite
import batch
import deepread as core
import desktop_bridge as desktop
import quota_guard as quota
import rce
import store
import v44_original_adapter as adapter
import test_deepread as synthetic

TEXT=("We study streaming 3D occupancy prediction under incomplete observations from cameras. "
      "An autonomous driving memory representation stores temporal scene evidence and updates historical state. "
      "The method reports occupancy scores on nuScenes and examines temporal ablations and known limitations.\n")*17


def _configure_test(ws):
    c=batch.cfg_at(ws)
    c.update({'core_min':1,'core_target':1,'core_max':1,'screen_batch_size':2,
              'min_supplemental_pdfs':0,'min_supplemental_qualified':0,
              'max_discovery_waves':0})
    for row in c['coverage_themes']:row['min_core']=0
    c['coverage_themes'][0]['min_core']=1
    core.jwrite(ws/'selection_config.json',c)
    native=desktop.native_cfg(ws)
    native['allow_native_model_calls']=True
    native['cross_domain']['enabled']=False
    native['budget']['max_assignments_per_cycle']=80
    native['budget']['max_prompt_chars_per_cycle']=5000000
    core.jwrite(ws/'native_config.json',native)


def _screen_reply(ws,job):
    state=batch.load_state(ws)
    prompt,byid=batch.make_screen_prompt(ws,state,job)
    rows=[]
    for pid in job['group']['paper_ids']:
        excerpt=byid[pid][0]
        rows.append({'paper_id':pid,'summary':job['stage']+' genuine streaming occupancy memory methodology',
                     'verdict':'LIKELY_RELEVANT','theme':'3D Occupancy/BEV',
                     'scores':{'topic':4.8,'method':4.6,'trajectory':4.5,'evidence_quality':4.8},
                     'evidence':[{'page':excerpt['page'],'quote':excerpt['text'][:63]}],
                     'uncertainty':'none','reason':job['stage']+' method fits the locked original task'})
    return {'stage':job['stage'],'papers':rows}


def _submit(ws,disp,ctx=None):
    jid=disp['job_id'];manifest=core.jread(desktop.task_dir(ws,jid)/'manifest.json');job=manifest['job']
    for role in disp['roles']:
        result=_screen_reply(ws,job) if job['type']=='screen' else synthetic.response(ctx,job)
        path=desktop.task_dir(ws,jid)/'answers'/(role+'.json')
        core.jwrite(path,result)
        desktop.collect(ws,jid,role,path,f'actual-independent-desktop-test-{jid}-{role}')
    result=desktop.commit(ws,jid)
    if result['status']=='NEED_CAPTAIN':
        path=desktop.task_dir(ws,jid)/'captain_answer.json'
        content=_screen_reply(ws,job) if job['type']=='screen' else synthetic.response(ctx,job)
        core.jwrite(path,content)
        result=desktop.commit(ws,jid,path,f'captain-{jid}') if job['type']=='cross' else desktop.commit(ws,jid,path)
    if result['status']=='NEED_SECOND_OPINION':
        next_role=result['role']; path=desktop.task_dir(ws,jid)/'answers'/(next_role+'.json')
        core.jwrite(path,_screen_reply(ws,job));desktop.collect(ws,jid,next_role,path,f'actual-independent-second-{jid}')
        result=desktop.commit(ws,jid)
    if result['status']!='COMMITTED':
        raise AssertionError('Unexpected main reader pipeline state '+str(result))
    return jid


class FullOriginalMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='original-v44-merge-')
        self.ws=pathlib.Path(self.temp.name)
        (self.ws/'goal.md').write_text('Autonomous driving streaming 3D occupancy, limited evidence memory and world-action prediction. Confirmed algorithms remain frozen.',encoding='utf-8')
    def tearDown(self):self.temp.cleanup()
    def _install(self):
        result=install_v6.install(self.ws)
        self.assertEqual(result['status'],'FULL_STACK_INSTALLED')
        init=suite.initialize(self.ws)
        self.assertEqual(init['status'],'INSTALL_READY',init)
    def _fully_read(self):
        self._install()
        _configure_test(self.ws)
        file=self.ws/'input'/'StudyA.md'
        file.write_text(TEXT,encoding='utf-8')
        batch.ingest(self.ws)
        self.assertEqual(suite.next_action(self.ws,allow_incomplete_discovery=True)['status'],'READ_SCREENING')
        stages=[]
        for _ in range(10):
            job=batch.next_screen(self.ws,batch.load_state(self.ws))
            if job is None:break
            disp=desktop.prepare(self.ws)
            stages.append(disp['kind'])
            _submit(self.ws,disp)
        self.assertEqual(stages,['screen','screen'])
        self.assertEqual(suite.next_action(self.ws,allow_incomplete_discovery=True)['status'],'READY_FOR_ORIGINAL_V44_SELECT')
        selected=batch.select_core(self.ws,batch.load_state(self.ws))
        self.assertEqual(selected['counts']['CORE'],1)
        self.assertEqual(suite.next_action(self.ws,allow_incomplete_discovery=True)['status'],'READY_TO_SEAL_ORIGINAL_V44')
        sub=batch.seal(self.ws,batch.load_state(self.ws))
        ctx=core.env(sub)
        # Crucial difference between raw batch IDs and original frozen v4.4 core IDs.
        self.assertNotEqual(batch.load_state(self.ws)['frozen']['paper_ids'][0],ctx['paper_ids'][0])
        jobs=[]
        for _ in range(150):
            nextjob=core.next_job(ctx)
            if nextjob is None:break
            disp=desktop.prepare(self.ws)
            jobs.append(_submit(self.ws,disp,ctx))
        else:self.fail('original reader never completed')
        self.assertEqual(core.run_status(ctx)['status'],'COMPLETE')
        self.assertTrue(any(x.startswith('R05_') and x.endswith('_C001') for x in jobs))
        self.assertTrue(any(x.startswith('AUDIT_') for x in jobs))
        return ctx
    def test_clean_one_archive_all_originals(self):
        self._install()
        check=suite.doctor(self.ws)
        self.assertEqual(check['status'],'PATCHED_V44_VERIFIED',check)
        self.assertEqual(check['source_file_count'],35)
        self.assertEqual(check['role_counts'],{'bpd_':16,'rce_':11})
        self.assertEqual(install_v6.install(self.ws)['status'],'FULL_STACK_INSTALLED')
        self.assertEqual(suite.next_action(self.ws)['status'],'NEEDS_DISCOVERY')
    def test_installer_default_conflicts_preflight_and_upgrade_backups(self):
        self._install()
        main=self.ws/'.agents/skills/batch-paper-deepread-desktop/SKILL.md'
        main.write_text('MY CUSTOM RESEARCH SKILL','utf-8')
        (self.ws/'input'/'private.md').write_text('Private research raw text','utf-8')
        (self.ws/'output'/'important.txt').write_text('PROVEN EXPERIMENT','utf-8')
        before=self.ws/'goal.md';original=before.read_bytes()
        blocked=install_v6.install(self.ws)
        self.assertEqual(blocked['status'],'BLOCKED_EXISTING_COMPONENTS_UNCHANGED')
        self.assertEqual(blocked['installed'],[])
        self.assertEqual(main.read_text(),'MY CUSTOM RESEARCH SKILL')
        installed=install_v6.install(self.ws,upgrade=True)
        self.assertEqual(installed['status'],'FULL_STACK_INSTALLED')
        self.assertTrue(installed['backups'])
        self.assertEqual(suite.doctor(self.ws)['status'],'PATCHED_V44_VERIFIED')
        self.assertEqual(before.read_bytes(),original)
        self.assertEqual((self.ws/'input'/'private.md').read_text(),'Private research raw text')
        self.assertEqual((self.ws/'output'/'important.txt').read_text(),'PROVEN EXPERIMENT')
        self.assertTrue(any((pathlib.Path(x)/'SKILL.md').read_text()=='MY CUSTOM RESEARCH SKILL' for x in installed['backups'] if pathlib.Path(x).is_dir() and (pathlib.Path(x)/'SKILL.md').is_file()))
    def test_rce_and_original_v44_share_one_real_reservation_ledger(self):
        self._install()
        cfg=rce.config(self.ws)
        result=rce._reserve(self.ws,cfg,{'RC0001_MAP:rce_cartographer_sol':750})
        self.assertTrue(result['linked_v44_budget'])
        old=quota.status(self.ws,desktop.native_cfg(self.ws)['budget'])
        self.assertEqual(old['reserved_assignments'],1)
        self.assertEqual(rce._reserve(self.ws,cfg,{'RC0001_MAP:rce_cartographer_sol':750})['new_reservations'],0)
        self.assertEqual(quota.status(self.ws,desktop.native_cfg(self.ws)['budget'])['reserved_assignments'],1)
    def test_v5_93_domain_runtime_uses_original_v44_source_unchanged(self):
        self._install()
        import subprocess
        launcher=self.ws/'.agents/skills/research-cognition-engine/scripts/native_v44_launcher.py'
        self.assertTrue(launcher.is_file())
        settings=desktop.native_cfg(self.ws)
        self.assertEqual(len(settings['cross_domain']['domains']),93)
        from paper_discovery import read
        patcher=self.ws/'.agents/skills/paper-discovery-preflight/scripts/install_into_codex_project.py'
        spec=importlib.util.spec_from_file_location('p_v5_installer',patcher)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        guarded=mod.extend_main_cross_domain(self.ws)
        self.assertEqual(guarded['status'],'WIDE_VIA_UNIFIED_RUNTIME_ADAPTER')
        # The original v4.4 cross-domain sidecar requires the primary batch
        # candidate corpus state to exist, even when browsing unrelated works.
        (self.ws/'input'/'Main.md').write_text(TEXT+' independently sourced main corpus',encoding='utf-8')
        batch.ingest(self.ws)
        folder=self.ws/'cross_domain_input'/'musicology';folder.mkdir(parents=True)
        (folder/'a.md').write_text('Music analysis investigates temporal organization and structural pattern recognition.\n'*18,encoding='utf8')
        cmd=[sys.executable,str(launcher),'cross-ingest','--workspace',str(self.ws)]
        done=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
        self.assertEqual(done.returncode,0,done.stderr)
        result=json.loads(done.stdout)
        self.assertEqual(result['added'],1,result)
        self.assertEqual(suite.doctor(self.ws)['status'],'PATCHED_V44_VERIFIED')
    def test_source_pagination_collision_gets_distinct_v44_anchor(self):
        self._fully_read()
        state=batch.load_state(self.ws);paper=next(x for x in state['papers'] if x['status']=='READY')
        workid='LOCAL_ORIGINAL_V44_'+paper['sha256'][:18]
        with store.connect(self.ws) as con:
            con.execute('INSERT INTO works(work_id,title,category,doi,year,venue,url,record_sha) VALUES (?,?,?,?,?,?,?,?)',
                        (workid,'LOCAL_FOR_TEST','core','',None,'','',paper['sha256']))
        # v6 text parser preserves the entire MD as one page; original v4.4
        # splits into 4500-char virtual pages. Same SHA but DIFFERENT anchors.
        source=store.import_source(self.ws,workid,self.ws/'input'/'StudyA.md')
        original_cache=store.read(pathlib.Path(store.listrows(self.ws,'sources')[0]['extract_path']))
        self.assertEqual(len(original_cache['pages']),1)
        imported=suite.adapter.sync(self.ws)
        self.assertEqual(imported['new_anchor_checked_claims']>=5,True)
        self.assertTrue(imported['papers'][0]['source_id'].endswith('-V44'))
        self.assertEqual(len(store.listrows(self.ws,'sources')),2)
        second=suite.adapter.sync(self.ws)
        self.assertEqual(second['new_anchor_checked_claims'],0)
        self.assertEqual(store.read(pathlib.Path(store.listrows(self.ws,'sources')[0]['extract_path']))['pages'],original_cache['pages'])

    def test_full_actual_v44_five_rounds_and_idempotent_rce_sync(self):
        ctx=self._fully_read()
        synced=suite.adapter.sync(self.ws)
        self.assertEqual(synced['status'],'SOURCE_EVIDENCE_SYNCED')
        self.assertTrue(synced['original_v44'])
        self.assertGreaterEqual(synced['new_anchor_checked_claims'],5)
        self.assertEqual(synced['pending_leaf_jobs'],0)
        second=suite.adapter.sync(self.ws)
        self.assertEqual(second['new_anchor_checked_claims'],0)
        with store.connect(self.ws) as c:
            count=c.execute('SELECT COUNT(*) FROM claims').fetchone()[0]
            statuses={x[0] for x in c.execute('SELECT DISTINCT status FROM claims')}
        self.assertEqual(count,synced['new_anchor_checked_claims'])
        self.assertEqual(statuses,{'ANCHOR_CHECKED_SEMANTICS_NOT_AUDITED'})
        self.assertEqual(suite.next_action(self.ws,allow_incomplete_discovery=True)['status'],'READY_FOR_RCE_CYCLE')
        self.assertTrue((self.ws/'output/research_cognition/research_memory.sqlite3').is_file())
    def test_tampering_in_native_reader_receipt_fails_closed(self):
        ctx=self._fully_read()
        jid=f'R01_{ctx["paper_ids"][0]}_C001'
        p=desktop.task_dir(self.ws,jid)/'receipts'/'bpd_topic_luna.json'
        self.assertTrue(p.exists())
        v=core.jread(p);v['requested_model']='SPOOFED';core.jwrite(p,v)
        with self.assertRaises(ValueError):
            suite.adapter.sync(self.ws)
    def test_missing_real_original_source_blocks_sync(self):
        ctx=self._fully_read()
        (self.ws/'input'/'StudyA.md').unlink()
        with self.assertRaises(ValueError):
            suite.adapter.sync(self.ws)


if __name__=='__main__':unittest.main(verbosity=2)
