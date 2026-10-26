"""v4.4 quota-first native desktop controls, offline only; synthetic reports."""
from __future__ import annotations
import pathlib,sys,tempfile,unittest,threading,concurrent.futures
SKILL=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL/'scripts'))
import desktop_bridge as app, deepread as core, batch, quota_guard as quota, local_synthesis

TEXT=('Streaming 3D occupancy from cameras. Method maintains Gaussian memory for temporally consistent predictions. '
      'Experiment on nuScenes reports IoU, mIoU and ablations. Evaluation uses temporal scenes and splits.\n')*13

class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.ws=pathlib.Path(self.temp.name)
        self.assertEqual(app.main(['init','--workspace',str(self.ws)]),0)
        (self.ws/'input'/'A.txt').write_text(TEXT,'utf8')
        self.cfg=app.native_cfg(self.ws)
    def tearDown(self):self.temp.cleanup()
    def ready(self):
        app.apply_patch(self.ws,{'research':{'goal_text':'streaming occupancy memory',
            'selection':{'core_min':1,'core_target':1,'core_max':1,
                         'min_supplemental_pdfs':0,'min_supplemental_qualified':0,
                         'coverage_themes':[{'name':'3D Occupancy/BEV','min_core':1}]}},
            'native':{'allow_native_model_calls':True}})
        batch.ingest(self.ws)
    def response(self,job,verdict='LIKELY_RELEVANT',unc='none',score=4.7):
        state=batch.load_state(self.ws);_,ex=batch.make_screen_prompt(self.ws,state,job)
        return {'stage':job['stage'],'papers':[{'paper_id':pid,'summary':job['stage']+' topic mapping',
            'verdict':verdict,'theme':'3D Occupancy/BEV',
            'scores':{'topic':score,'method':4.3,'trajectory':4.4,'evidence_quality':4.4},
            'evidence':[{'page':ex[pid][0]['page'],'quote':ex[pid][0]['text'][:62]}],
            'uncertainty':unc,'reason':job['stage']+' original evidence'} for pid in job['group']['paper_ids']]}
    def submit(self,dispatch,roles=None,**kwargs):
        job=core.jread(app.task_dir(self.ws,dispatch['job_id'])/'manifest.json')['job']
        for idx,role in enumerate(roles if roles is not None else dispatch['roles']):
            f=app.task_dir(self.ws,job['id'])/'answers'/(role+'.json')
            core.jwrite(f,self.response(job,**kwargs))
            app.collect(self.ws,job['id'],role,f,f'thread-{job["id"]}-{role}')
        return job
    def test_default_economy_five_rounds_and_strict_switch(self):
        self.assertEqual(self.cfg['budget']['profile'],'economy')
        self.assertEqual(core.config_for(self.ws)['rounds'],5)
        self.assertEqual(len(app.roster({'id':'s1','type':'screen','stage':'S1'},self.cfg)),1)
        self.assertEqual(len(app.roster({'id':'s2','type':'screen','stage':'S2'},self.cfg)),1)
        self.assertEqual([len(app.roster({'id':'X','type':'leaf','round':r},self.cfg)) for r in range(1,6)],[1,1,1,2,1])
        roles={role for r in range(1,6) for role in app.roster({'id':'X','type':'leaf','round':r},self.cfg)}
        self.assertGreaterEqual(len(roles),3)
        strict={**self.cfg,'budget':{**self.cfg['budget'],'profile':'strict'}}
        self.assertEqual([len(app.roster({'id':'X','type':'leaf','round':r},strict)) for r in range(1,6)],[3]*5)
    def test_pre_dispatch_reservation_is_idempotent(self):
        self.ready()
        info=app.prepare(self.ws)
        self.assertEqual(info['roles'],['bpd_topic_luna'])
        self.assertEqual(quota.status(self.ws,app.native_cfg(self.ws)['budget'])['reserved_assignments'],1)
        again=app.prepare(self.ws)
        self.assertEqual(info['job_id'],again['job_id'])
        self.assertEqual(quota.status(self.ws,app.native_cfg(self.ws)['budget'])['reserved_assignments'],1)
        self.assertTrue((app.task_dir(self.ws,info['job_id'])/'dispatch.json').is_file())
    def test_pauses_before_dispatch_even_when_no_receipts(self):
        self.ready()
        app.apply_patch(self.ws,{'native':{'budget':{'max_prompt_chars_per_cycle':1000}}})
        with self.assertRaises(quota.QuotaExceeded):app.prepare(self.ws)
        self.assertEqual(quota.status(self.ws,app.native_cfg(self.ws)['budget'])['reserved_assignments'],0)
        self.assertFalse((self.ws/'output/native/tasks/S1_B00001/dispatch.json').exists())
    def test_S2_risk_requires_independent_second_opinion(self):
        self.ready()
        d=app.prepare(self.ws);jid=d['job_id'];self.submit(d)
        self.assertEqual(app.commit(self.ws,jid)['route'],'SINGLE_INDEPENDENT_STAGE_READING')
        d=app.prepare(self.ws);jid=d['job_id'];self.assertEqual(d['roles'],['bpd_method_sol'])
        self.submit(d,verdict='BORDERLINE',unc='need experimental verification',score=2.2)
        gate=app.commit(self.ws,jid)
        self.assertEqual(gate['status'],'NEED_SECOND_OPINION')
        self.assertEqual(gate['role'],'bpd_skeptic_sol')
        self.assertEqual(quota.status(self.ws,app.native_cfg(self.ws)['budget'])['reserved_assignments'],3)
        # In-flight upgrade may be resumed without changing the source contract.
        reopened=app.prepare(self.ws)
        self.assertEqual(len(reopened['roles']),2)
        self.submit(reopened,roles=['bpd_skeptic_sol'],verdict='LIKELY_RELEVANT',unc='none',score=4.5)
        self.assertEqual(app.commit(self.ws,jid)['status'],'NEED_CAPTAIN')
    def test_budget_cycle_requires_explicit_real_renewal(self):
        cfg=self.cfg['budget']
        quota.reserve(self.ws,cfg,{'A:reader:X':2200})
        with self.assertRaises(ValueError):
            quota.renew(self.ws,cfg,'cycle-002')
        got=quota.renew(self.ws,cfg,'cycle-002',user_authorized=True)
        self.assertEqual(got['reserved_assignments'],0)
        self.assertEqual(got['lifetime_reserved_assignments'],1)
        with self.assertRaises(ValueError):
            quota.renew(self.ws,cfg,'cycle-002',user_authorized=True)
    def test_concurrent_reservation_never_exceeds_limit(self):
        conf={**self.cfg['budget'],'max_assignments_per_cycle':4}
        def one(i):
            try:quota.reserve(self.ws,conf,{f'TASK{i}':1500});return 'OK'
            except quota.QuotaExceeded:return 'PAUSED'
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            out=list(pool.map(one,range(18)))
        self.assertEqual(out.count('OK'),4)
        self.assertEqual(quota.status(self.ws,conf)['reserved_assignments'],4)
    def test_budget_override_after_prepare_does_not_change_identity_contract(self):
        self.ready();old=app.prepare(self.ws)
        app.apply_patch(self.ws,{'native':{'budget':{'max_assignments_per_cycle':90}}})
        new=app.prepare(self.ws)
        self.assertEqual(new['job_id'],old['job_id'])
    def test_explicit_legacy_migration_keeps_no_campaign_loss(self):
        self.ready()
        (self.ws/'native_config.json').write_text(core.dump({k:v for k,v in app.native_cfg(self.ws).items() if k!='budget'}),'utf8')
        self.assertEqual(app.main(['init','--workspace',str(self.ws)]),0)
        self.assertEqual(app.native_cfg(self.ws)['budget']['profile'],'economy')
        self.assertEqual(len(batch.load_state(self.ws)['papers']),1)
    def test_planner_with_one_paper_is_not_provider_usage(self):
        self.ready()
        result=quota.plan(self.ws,self.cfg['budget'])
        self.assertIn('estimated_min_total_assignments',result)
        self.assertGreaterEqual(result['estimated_min_total_assignments'],8)
        self.assertIn('does NOT observe',result['source'])

class LocalCompilerTests(unittest.TestCase):
    def test_merge_only_reuses_cited_original_observations(self):
        with tempfile.TemporaryDirectory() as d:
            ws=pathlib.Path(d);core.init(ws)
            (ws/'input'/'a.md').write_text(TEXT,'utf8')
            core.ingest(ws);ctx=core.env(ws)
            job=core.next_job(ctx)
            self.assertEqual(job['type'],'leaf')
            pid=job['paper_id'];quote=core.paper_pages(ctx,pid)[0][:65]
            points=[{'claim':f'原文可验证观察{k}','category':'method','status':'reported','confidence':'medium',
                     'evidence':[{'page':1,'quote':quote}]} for k in (1,2)]
            result={'round':1,'paper_id':pid,'chunk_id':job['chunk_id'],'brief':'第一轮阅读全文',
                    'observations':points,'open_questions':[],'visual_flags':[],'empty_reason':''}
            p=ws/'a.json';core.jwrite(p,result);core.submit_file(ctx,job['id'],p)
            nxt=core.next_job(ctx)
            self.assertEqual(nxt['type'],'merge')
            compiled=local_synthesis.make(ctx,nxt)
            self.assertEqual([q['claim'] for q in compiled['key_points']],[p['claim'] for p in points])
            self.assertEqual(core.validate(ctx,nxt,compiled)['validated_citations'],2)

if __name__=='__main__':unittest.main()

class SixHundredPaperBudgetPlan(unittest.TestCase):
    def test_600_candidate_plan_warns_budget_shortfall_without_spawning(self):
        with tempfile.TemporaryDirectory() as folder:
            ws=pathlib.Path(folder)
            app.main(['init','--workspace',str(ws)])
            for i in range(600):
                (ws/'input'/f'paper_{i}.txt').write_text(TEXT+f'\nSource identity ID: {i}\n',encoding='utf8')
            batch.ingest(ws)
            p=quota.plan(ws,app.native_cfg(ws)['budget'])
            self.assertEqual(p['candidate_papers'],600)
            self.assertEqual(p['screening_batches'],38)
            self.assertEqual(p['screening_two_pass_reader_assignments'],76)
            self.assertEqual(p['cycle_sufficiency_check'],'BELOW_ESTIMATED_NEED')
            self.assertFalse((ws/'output/native/tasks').exists())
