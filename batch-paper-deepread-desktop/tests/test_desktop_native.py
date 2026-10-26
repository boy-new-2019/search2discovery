from __future__ import annotations
import json, pathlib, sys, tempfile, unittest
SKILL=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL/'scripts'))
import desktop_bridge as app
import batch, deepread as core, profiles

TEXT=(
    'Streaming occupancy and evidence-memory update for visual autonomous driving.\n'
    'Abstract: We predict 3D occupancy from cameras in an online fashion.\n'
    'Method: We maintain temporally coherent state by updating past evidence using visual observation.\n'
    'Experiment: nuScenes IoU and mIoU are compared across temporal memory ablations.\n'
) * 8

class DesktopNativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ws=pathlib.Path(self.temp.name)
        self.assertEqual(app.main(['init','--workspace',str(self.ws)]),0)
        (self.ws/'input'/'one_paper.txt').write_text(TEXT,'utf-8')
        self.assertEqual(app.native_cfg(self.ws)['allow_native_model_calls'],False)
        self.patch={'native':{'allow_native_model_calls':True,'budget':{'profile':'strict'}},'research':{'goal_text':'视觉3D Occupancy与时序记忆',
            'selection':{'core_min':1,'core_target':1,'core_max':1,
                         'min_supplemental_pdfs':0,'min_supplemental_qualified':0,
                         'coverage_themes':[{'name':'3D Occupancy/BEV','min_core':1}]}}}
    def tearDown(self):self.temp.cleanup()
    def ready(self):
        app.apply_patch(self.ws,self.patch)
        batch.ingest(self.ws)
    def screen_report(self, job,stage,low_quality=False,verdict='LIKELY_RELEVANT'):
        state=batch.load_state(self.ws)
        prompt,ex=batch.make_screen_prompt(self.ws,state,{'id':job['id'],'stage':job['stage'],'group':job['group']})
        data=[]
        for pid,pieces in ex.items():
            part=next(p for p in pieces if len(p['text'])>70)
            data.append({'paper_id':pid,'summary':stage+' 本文涉及流式时序记忆',
                         'verdict':verdict,'theme':'3D Occupancy/BEV',
                         'scores':{'topic':4.5,'method':4.4,'trajectory':4.6,
                                   'evidence_quality':2.8 if low_quality else 4.5},
                         'evidence':[{'page':part['page'],'quote':part['text'][0:50]}],
                         'uncertainty':'none','reason':stage+' 提到相机与记忆的方法'})
        return {'stage':stage,'papers':data}
    def test_profiles_windows_native(self):
        files=list((self.ws/'.codex/agents').glob('bpd_*.toml'))
        self.assertEqual(len(files),16)
        self.assertEqual(profiles.toml_string('中文'), '"中文"')
        self.assertEqual(app.status(self.ws)['status'],'NOT_INGESTED')
    def test_authorization_and_independent_thread_gate(self):
        batch.ingest(self.ws)
        with self.assertRaises(ValueError):
            app.prepare(self.ws)
        # Existing campaign forbids a semantic goal change after ingest: use run-only permission.
        app.apply_patch(self.ws,{'native':{'allow_native_model_calls':True,'budget':{'profile':'strict'}}})
        info=app.prepare(self.ws)
        manifest=core.jread(app.task_dir(self.ws,info['job_id'])/'manifest.json')
        answer=self.screen_report(manifest['job'],'S1')
        file=app.task_dir(self.ws,info['job_id'])/'answers'/(info['roles'][0]+'.json')
        core.jwrite(file,answer)
        with self.assertRaises(ValueError):
            app.collect(self.ws,info['job_id'],info['roles'][0],file)
        got=app.collect(self.ws,info['job_id'],info['roles'][0],file,'thread-a')
        self.assertEqual(got['status'],'VERIFIED')
        with self.assertRaises(ValueError):
            f=app.task_dir(self.ws,info['job_id'])/'answers'/(info['roles'][1]+'.json');core.jwrite(f,answer)
            app.collect(self.ws,info['job_id'],info['roles'][1],f,'thread-a')
    def test_screen_consensus_and_disagreement(self):
        self.ready()
        info=app.prepare(self.ws)
        jid=info['job_id'];job=core.jread(app.task_dir(self.ws,jid)/'manifest.json')['job']
        for i,role in enumerate(info['roles']):
            data=self.screen_report(job,'S1',low_quality=False)
            f=app.task_dir(self.ws,jid)/'answers'/(role+'.json');core.jwrite(f,data)
            app.collect(self.ws,jid,role,f,f'thread-{i}')
        self.assertEqual(app.commit(self.ws,jid)['route'],'STRICT_DETERMINISTIC_CONSENSUS')
        nxt=app.prepare(self.ws);self.assertEqual(nxt['kind'],'screen')
        jid=nxt['job_id'];job=core.jread(app.task_dir(self.ws,jid)/'manifest.json')['job']
        for i,role in enumerate(nxt['roles']):
            data=self.screen_report(job,'S2',low_quality=(i==1))
            f=app.task_dir(self.ws,jid)/'answers'/(role+'.json');core.jwrite(f,data)
            app.collect(self.ws,jid,role,f,f'stage2-thread-{i}')
        needed=app.commit(self.ws,jid)
        self.assertEqual(needed['status'],'NEED_CAPTAIN')
        self.assertTrue(pathlib.Path(needed['captain_prompt']).is_file())
    def test_change_model_requires_reload(self):
        self.ready()
        app.apply_patch(self.ws,{'native':{'model_pins':{'bpd_topic_luna':{'model':'gpt-6.1-sol','effort':'high'}}}})
        with self.assertRaises(ValueError):
            app.prepare(self.ws)
        ack=app.main(['ack-profiles','--workspace',str(self.ws)])
        self.assertEqual(ack,0)
        self.assertEqual(app.prepare(self.ws)['status'],'READY')
        self.assertEqual(app.model_profile(self.ws,'bpd_topic_luna')['model_requested'],'gpt-6.1-sol')
    def test_audit_veto_cannot_be_overridden(self):
        job={'id':'AUDIT_v0','type':'audit','revision':0}
        checked=['P1','P2']
        views={'evidence':{'verdict':'PASS','checked_papers':checked,'coverage_confidence':'high','issues':[]},
               'methods':{'verdict':'VETO','checked_papers':checked,'coverage_confidence':'medium','issues':[
                    {'severity':'major','claim':'实验缺对照','reason':'不能直接比较','support':[],'repair':'补充方法限制'}]}}
        merged=app.audit_fuse(job,views)
        self.assertEqual(merged['verdict'],'VETO')
        self.assertEqual(merged['coverage_confidence'],'medium')
    def test_rounds_cannot_drop_below_five(self):
        self.ready()
        with self.assertRaises(RuntimeError):
            app.apply_patch(self.ws,{'research':{'reading':{'rounds':4}}})

if __name__=='__main__':unittest.main()
