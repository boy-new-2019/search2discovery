from __future__ import annotations
import copy
import pathlib
import sys
import tempfile
import unittest

SKILL=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL/'scripts'))
import batch
import deepread as core
import desktop_bridge as app
import direction_evolution as direction

TEXT=('Streaming autonomous driving evidence and temporal memory for scene occupancy.\n'
      'Abstract: partial observation and task-oriented state retention.\n'
      'Methods: recurrent features integrate older history with current visual input.\n'
      'Results: occupancy prediction and temporal context are studied.\n')*12

class DirectionEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ws=pathlib.Path(self.tmp.name)
        batch.init(self.ws)
        app.main(['init','--workspace',str(self.ws)])
        for name in ('memory_a.txt','memory_b.txt','occupancy_c.txt'):
            (self.ws/'input'/name).write_text(name+'\n'+TEXT,encoding='utf-8')
        app.apply_patch(self.ws,{'native':{'allow_native_model_calls':True},
            'research':{'selection':{'screen_batch_size':2,'core_min':1,'core_target':2,'core_max':3,
                                     'min_supplemental_pdfs':0,'min_supplemental_qualified':0,
                                     'coverage_themes':[{'name':'Streaming/Temporal Memory','min_core':1},
                                                        {'name':'3D Occupancy/BEV','min_core':1}]}}})
        batch.ingest(self.ws)
    def tearDown(self):self.tmp.cleanup()
    def do_screen(self):
        while True:
            state=batch.load_state(self.ws)
            job=batch.next_screen(self.ws,state)
            if not job:break
            _,ex=batch.make_screen_prompt(self.ws,state,job)
            data=[]
            for pid in job['group']['paper_ids']:
                paper=next(x for x in state['papers'] if x['id']==pid)
                part=next(x for x in ex[pid] if x['text'])
                theme='Streaming/Temporal Memory' if 'memory_' in paper['file'] else '3D Occupancy/BEV'
                data.append({'paper_id':pid,'summary':job['stage']+' streaming observation state information',
                             'verdict':'LIKELY_RELEVANT','theme':theme,
                             'scores':{'topic':4.2,'method':4.1,'trajectory':4.3,'evidence_quality':4.8},
                             'evidence':[{'page':part['page'],'quote':part['text'][:55]}],
                             'uncertainty':'none','reason':job['stage']+' related topic and method'})
            f=self.ws/'output'/'batch'/'test_screen.json';core.jwrite(f,{'stage':job['stage'],'papers':data})
            batch.screen_submit(self.ws,state,job['id'],f)
        return batch.select_core(self.ws,batch.load_state(self.ws))
    def proposal(self):
        state=batch.load_state(self.ws)
        papers=[x for x in state['papers'] if 'memory_' in x['file']]
        return {'operation':'REFINE_FOCUS','parent_theme':'Streaming/Temporal Memory',
                'focus':'在Streaming/Temporal Memory中研究观测证据与固定容量记忆更新',
                'priority_delta':0,'rationale':'两篇论文都强调观测约束与历史信息，值得缩小到固定容量证据记忆管理这个具体技术切口。',
                'evidence':[{'paper_id':x['id'],'page':1,'quote':TEXT[:75]} for x in papers],
                'proposer_role':'bpd_transfer_sol','proposer_thread_ref':'proposal-thread-A',
                'scope':{'macro_unchanged':True,'confirmed_paper_core_unchanged':True,
                         'justification':'仍然属于自动驾驶流式感知与记忆管理，只修改文献阅读的细分重点，不改变已确认论文的核心方法。'}}
    @staticmethod
    def reviews(p,verdict='SUPPORT'):
        sha=core.htext(core.dump(p))
        return {'reviews':[{'role':r,'proposal_sha256':sha,'thread_ref':'thread_'+str(i)+'_separate',
                            'verdict':verdict if i==0 else 'SUPPORT','macro_preserved':True,
                            'confirmed_paper_core_preserved':True,
                            'reason':'属于研究总方向内的子主题调整，现有实验、网络和创新问题保持不动，尚未发现越界。'}
                           for i,r in enumerate(direction.REVIEWERS)]}
    def test_route_evolution_targeted_recheck_and_frozen_snapshot(self):
        self.do_screen()
        goal_hash=core.file_hash(self.ws/'goal.md')
        original_recs={p.name:p.read_bytes() for p in (self.ws/'output'/'batch'/'answers').glob('*.json')}
        kit=direction.kit(self.ws,app.native_cfg(self.ws)['direction'])
        self.assertEqual(kit['status'],'PROPOSAL_READY')
        p=self.proposal();preview=direction.preview(self.ws,p,app.native_cfg(self.ws)['direction'])
        self.assertEqual(preview['affected_papers'],2)
        self.assertEqual(preview['required_s1_s2_groups'],2)
        prompts=direction.review_prompts(self.ws,p,app.native_cfg(self.ws)['direction'])
        self.assertEqual(len(prompts['review_prompts']),2)
        done=direction.apply(self.ws,p,self.reviews(p),app.native_cfg(self.ws)['direction'])
        self.assertEqual(done['revision'],1)
        self.assertEqual(done['rescreen_papers'],2)
        self.assertEqual(core.file_hash(self.ws/'goal.md'),goal_hash)
        state=batch.load_state(self.ws)
        self.assertEqual(state['selection'],{})
        self.assertEqual(len(state['groups']),3)
        job=batch.next_screen(self.ws,state)
        self.assertEqual(job['stage'],'S1')
        self.assertTrue(job['id'].startswith('S1_EV01'))
        newprompt,_=batch.make_screen_prompt(self.ws,state,job)
        self.assertIn('观测证据与固定容量记忆更新',newprompt)
        self.do_screen()
        for k,v in original_recs.items():
            self.assertEqual((self.ws/'output'/'batch'/'answers'/k).read_bytes(),v)
        sub=batch.seal(self.ws,batch.load_state(self.ws))
        self.assertIn('观测证据与固定容量记忆更新',(sub/'goal.md').read_text('utf-8'))
        self.assertEqual(core.file_hash(self.ws/'goal.md'),goal_hash)
        with self.assertRaises(ValueError):
            direction.preview(self.ws,p,app.native_cfg(self.ws)['direction'])
    def test_block_macro_theme_change_and_fake_evidence(self):
        self.do_screen()
        p=self.proposal();p['parent_theme']='Completely New Physics Domain'
        with self.assertRaises(ValueError):
            direction.preview(self.ws,p,app.native_cfg(self.ws)['direction'])
        p=self.proposal();p['evidence'][0]['quote']='fabricated evidence is not in the PDF'
        with self.assertRaises(ValueError):
            direction.preview(self.ws,p,app.native_cfg(self.ws)['direction'])
    def test_veto_is_persistent_and_blocks_resubmission(self):
        self.do_screen();p=self.proposal()
        result=direction.apply(self.ws,p,self.reviews(p,verdict='VETO'),app.native_cfg(self.ws)['direction'])
        self.assertEqual(result['status'],'REJECTED_BY_INDEPENDENT_VETO')
        with self.assertRaises(ValueError):
            direction.apply(self.ws,p,self.reviews(p),app.native_cfg(self.ws)['direction'])
        self.assertIsNone(batch.next_screen(self.ws,batch.load_state(self.ws)))
        self.assertEqual(direction.current(self.ws)['revision'],0)
    def test_too_many_affected_refuses_partial_recheck(self):
        self.do_screen();p=self.proposal()
        prefs={**app.native_cfg(self.ws)['direction'],'max_recheck_papers_per_change':1}
        with self.assertRaises(ValueError):
            direction.preview(self.ws,p,prefs)
    def test_propose_only_and_prompt_configurable(self):
        self.do_screen()
        app.apply_patch(self.ws,{'native':{'direction':{'mode':'propose_only','max_accepted_changes':5}}})
        prefs=app.native_cfg(self.ws)['direction']
        self.assertEqual(prefs['max_accepted_changes'],5)
        self.assertEqual(prefs['min_distinct_support_papers'],2)
        p=self.proposal();res=direction.apply(self.ws,p,self.reviews(p),prefs)
        self.assertEqual(res['status'],'AWAIT_USER_APPROVAL')
        self.assertEqual(direction.current(self.ws)['revision'],0)
    def test_600_papers_targeted_rescreen_not_all_600(self):
        from test_batch import make_ws,fill_screen,TEXT_REL
        with tempfile.TemporaryDirectory() as temp:
            ws=pathlib.Path(temp)
            state=make_ws(ws,n=600,relevant=120,batch_size=8,target=60,minimum=30)
            names={f'paper{i:04d}.md' for i in range(120)}
            self.assertEqual(fill_screen(ws,state,names),150)
            batch.select_core(ws,state)
            scored=batch.load_state(ws)['selection']['decisions']
            relevant=[x for x in scored if x['theme']=='Streaming/Temporal Memory']
            self.assertEqual(len(relevant),120)
            p={'operation':'SHIFT_PRIORITY','parent_theme':'Streaming/Temporal Memory',
               'focus':'','priority_delta':1,
               'rationale':'该主题的两轮原文证据与研究路线高度契合，有限提升该主题入选精读的优先级有正当理由。',
               'evidence':[{'paper_id':x['paper_id'],'page':1,'quote':TEXT_REL[:60]} for x in relevant[:2]],
               'proposer_role':'bpd_transfer_sol','proposer_thread_ref':'proposal-thread-LARGE',
               'scope':{'macro_unchanged':True,'confirmed_paper_core_unchanged':True,
                        'justification':'只修改候选名单中已经相关的流式时序记忆主题优先级，研究大方向与现有论文方法完全保持不变。'}}
            preview=direction.preview(ws,p,direction.PREFERENCE_DEFAULT)
            self.assertEqual(preview['affected_papers'],120)
            self.assertEqual(preview['required_s1_s2_groups'],30)
            outcome=direction.apply(ws,p,self.reviews(p),direction.PREFERENCE_DEFAULT)
            self.assertEqual(outcome['rescreen_group_pairs'],15)
            self.assertEqual(len(batch.load_state(ws)['groups']),90)  # 75 original + 15 targeted
    def test_recover_after_interrupted_direction_transaction(self):
        self.do_screen();p=self.proposal()
        prefs=app.native_cfg(self.ws)['direction']
        result=direction.apply(self.ws,p,self.reviews(p),prefs)
        self.assertEqual(result['status'],'ACCEPTED_RESCREEN_PENDING')
        state=batch.load_state(self.ws)
        state['groups']=[g for g in state['groups'] if not g['id'].startswith('EV01')]
        state['selection']={'STALE':'not acceptable'}
        batch.save_state(self.ws,state)
        with self.assertRaises(ValueError):
            direction.current(self.ws)
        recovered=direction.recover(self.ws)
        self.assertEqual(recovered['status'],'RECOVERED_PENDING_RECHECK')
        self.assertEqual(recovered['restored_screen_groups'],1)
        self.assertEqual(batch.load_state(self.ws)['selection'],{})
        self.assertEqual(direction.current(self.ws)['revision'],1)
    def test_native_config_upgrade_from_v4_1(self):
        f=self.ws/'native_config.json'
        old=core.jread(f);old.pop('direction')
        core.jwrite(f,old)
        self.assertEqual(app.main(['init','--workspace',str(self.ws)]),0)
        self.assertEqual(app.native_cfg(self.ws)['direction']['mode'],'bounded_auto')
        self.assertEqual(len(batch.load_state(self.ws)['papers']),3)
    def test_stale_undelivered_screen_job_blocks_shift(self):
        self.do_screen();info=app.prepare(self.ws)
        self.assertEqual(info['status'],'SCREENING_DONE')
        # A disconnected subagent job manifest without commit must not allow route change.
        tmp=self.ws/'output'/'native'/'tasks'/'unfinished_job'
        tmp.mkdir(parents=True)
        core.jwrite(tmp/'manifest.json',{'test':'inflight'})
        with self.assertRaises(ValueError):
            direction.preview(self.ws,self.proposal(),app.native_cfg(self.ws)['direction'])

if __name__=='__main__': unittest.main()
