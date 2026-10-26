from __future__ import annotations
import pathlib,sys,tempfile,unittest,copy
SKILL=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL/'scripts'))
import store,engine,harness,rce

FULLA=('This paper studies streaming three dimensional occupancy from temporally partial observations. '
       'It proposes a memory representation that preserves selected historical features based on current evidence. '
       'Experiments on a public benchmark compare IoU and temporal consistency and show boundary limitations.\n')*9
FULLB=('This paper examines task-aware belief revision under partial observability for a sequential decision system. '
       'The update criterion uses predicted future task utility rather than only immediate observation confidence. '
       'Failure cases arise when future objectives differ from current perceptual quality.\n')*9

class CognitionE2E(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ws=pathlib.Path(self.tmp.name)
        (self.ws/'goal.md').write_text('自动驾驶部分可观测环境下流式三维占用、固定容量时序记忆与驾驶世界—动作学习。锁定原核心算法和实测结论。','utf8')
        self.catalogue(self.ws)
        rce.init(self.ws)
        store.import_catalogue(self.ws)
        self.files=[]
        for wid,txt in [('W-occupancy',FULLA),('W-belief',FULLB)]:
            p=self.ws/(wid+'.txt');p.write_text(txt,'utf8');self.files.append(p)
            store.import_source(self.ws,wid,p)
        self.config=store.read(self.ws/rce.CONF)
        self.config['budget']['max_native_assignments_per_cycle']=20
        store.write(self.ws/rce.CONF,self.config)
    def tearDown(self):self.tmp.cleanup()
    @staticmethod
    def catalogue(ws):
        path=ws/'output/discovery_preflight/paper_library.json'
        store.write(path,{'selected':{
            'core':[{'id':'W-occupancy','title':'Streaming visual 3D occupancy and evidence memory','year':2025,'doi':'10.0101/one','venue':'TestConference','bibliographic_link':'https://example.org/1'}],
            'related':[{'id':'W-belief','title':'Task-aware belief revision with bounded observation','year':2024,'doi':'10.0101/two','venue':'TestJournal','bibliographic_link':'https://example.org/2'}],
            'inspiration':[]}})
    def task(self):return engine.prepare(self.ws,self.config,rce._reserve)
    def submit(self,task,result_generator):
        for idx,role in enumerate(task['roles']):
            obj=result_generator(task['stage'],role)
            p=engine.taskdir(self.ws,task['job_id'])/('candidate'+str(idx)+'.json')
            store.write(p,obj)
            res=engine.collect(self.ws,task['job_id'],role,p,f'codex-subagent-{task["stage"]}-{role}')
            self.assertEqual(res['status'],'VERIFIED')
        return engine.commit(self.ws,task['job_id'])
    def ready_ids(self):
        claims=store.listrows(self.ws,'claims')
        questions=store.listrows(self.ws,'questions')
        hyps=store.listrows(self.ws,'hypotheses')
        return claims,questions,hyps
    def response(self,stage,role):
        claims,questions,hyps=self.ready_ids()
        with store.connect(self.ws) as c:
            src={x['work_id']:x['source_id'] for x in c.execute('SELECT work_id,source_id FROM sources')}
        if stage=='MAP':return {'stage':stage,'questions':[{'question':'在有限观测条件下历史证据应该如何修订才能改善预测和决策的任务价值？',
            'domain':'Streaming Occupancy & World Action','impact':0.9,'uncertainty':0.8,
            'evidence_needed':'需要连续原文、对照实验和跨任务预测验证才能确定机制优势。'}]}
        if stage=='MECHANISM':
            wid='W-occupancy' if role=='rce_method_sol' else 'W-belief'
            quote=FULLA[:90] if wid=='W-occupancy' else FULLB[:90]
            return {'stage':stage,'observations':[{'source_id':src[wid],'kind':'METHOD',
              'claim':'在受限观测条件下使用历史证据更新状态，但优化目标及效果需要跨实验进一步比较确认。',
              'page':1,'quote':quote,'assumptions':'依赖原文所规定的信息可用性条件与固定的评价协议。',
              'uncertainty':'该方法在未来预测和动作任务上的实际增益未知。'}]}
        if stage=='CONTRADICTION':
            return {'stage':stage,'contradictions':[{'left_claim_id':claims[0]['claim_id'],'right_claim_id':claims[1]['claim_id'],
              'rationale':'现有历史证据保留原则与未来任务效用原则可能在状态改变时产生不同的更新策略选择。',
              'protocol_check':'先比较两项研究的任务、数据集、时间窗口和评测指标是否具有可比性。',
              'alternative':'二者并未真正冲突，可能只是在不同目标函数上研究了不同情形。',
              'discriminating_test':'在相同部分可观测数据上控制容量与协议，对比观测驱动和任务驱动更新。'}]}
        if stage=='HYPOTHESIS':
            return {'stage':stage,'hypotheses':[{'question_id':questions[0]['question_id'],
              'statement':'在相同有限容量条件下结合证据冲突与未来任务效用进行历史状态修订可能改善遮挡条件下的未来动作可靠性。',
              'mechanism':'根据当前观测反证抑制错误历史状态，并根据后续任务敏感性选择需要保留的部分历史信息。',
              'prediction':'在遮挡和机动改变子集中，新的状态修订方法相较置信度基线应降低未来轨迹误差。',
              'falsifier':'若公平基线在相同容量及计算条件下获得同等或更优成绩，则拒绝该机制的有效性假设。',
              'assumptions':'训练与推理协议一致、数据标注和历史帧对齐正确、未来任务效用可估计。',
              'linked_claim_ids':[x['claim_id'] for x in claims],
              'nearest_work_ids':['W-occupancy','W-belief'],
              'minimal_test':'构造受控的遮挡场景，比较历史证据冲突更新、纯置信度和任务效用策略的动作输出。'}]}
        if stage=='NOVELTY':
            return {'stage':stage,'assessments':[{'hypothesis_id':hyps[0]['hypothesis_id'],
              'verdict':'POTENTIAL_NEW' if role=='rce_novelty_sol' else 'UNCERTAIN',
              'nearest_work_ids':['W-occupancy','W-belief'],
              'justification':'两篇相关研究提供了不同的记忆状态更新原则，但需要另外核对最新类似研究和实际结构差异。',
              'unresolved':'还需要联网检查新近世界动作模型中的更新策略并进行原文级比较。'}]}
        if stage=='EXPERIMENT':
            return {'stage':stage,'plans':[{'hypothesis_id':hyps[0]['hypothesis_id'],
              'test':'固定历史容量和相同训练集，比较证据冲突更新与已有单纯置信度基线在遮挡、机动切换条件下的表现。',
              'baselines':['当前方法基线','等容量置信度记忆'],
              'metrics':['IoU','minADE','minFDE'],
              'reject_condition':'若连续重复实验的动作误差、占用精度未显示可信改善，或计算负担明显超额，则停止采用。',
              'data_sources':'公开nuScenes及现有合法数据集',
              'resource_budget':'先以现有算力完成小规模对照，再决定是否开展大模型实验。'}]}
        if stage=='FINAL':
            return {'stage':stage,'recommendations':[{'hypothesis_id':hyps[0]['hypothesis_id'],
              'recommendation':'建议仅作为新研究备选路线提出，先确认最新最相近文献和定义，再实施最小规模公平对照实验。',
              'risks':'实验协议和任务效用表达可能不匹配，且新颖性尚未被近期顶刊顶会全文核实。',
              'confidence':'low',
              'review_note':'任何既有论文方法、损失函数或已确认实验数据均保持冻结，须由研究负责人批准新方向。'}]}
        raise AssertionError(stage)
    def test_complete_research_cycle_with_real_anchor_validation(self):
        engine.new_cycle(self.ws,self.config)
        seen=[]
        for stage in engine.STAGES:
            task=self.task();seen.append(task['stage'])
            self.assertEqual(task['stage'],stage)
            self.assertTrue((engine.taskdir(self.ws,task['job_id'])/'allocation_receipt.json').exists())
            result=self.submit(task,self.response)
            self.assertEqual(result['next_stage'],engine.STAGES[engine.STAGES.index(stage)+1] if stage!=engine.STAGES[-1] else 'COMPLETE')
        self.assertEqual(seen,list(engine.STAGES))
        self.assertEqual(engine.stage(self.ws)[1],'COMPLETE')
        entities={key:len(store.listrows(self.ws,key)) for key in ['works','sources','claims','questions','contradictions','hypotheses','assessments','experiments','decisions']}
        self.assertEqual(entities['works'],2);self.assertEqual(entities['sources'],2)
        self.assertEqual(entities['assessments'],2);self.assertEqual(entities['contradictions'],1)
        self.assertEqual(store.listrows(self.ws,'hypotheses')[0]['novelty_status'],'NOVELTY_UNVERIFIED')
        self.assertEqual(store.listrows(self.ws,'decisions')[0]['status'],'PENDING_USER_APPROVAL')
        self.assertEqual(engine.report(self.ws)['status'],'REPORTED')
        self.assertIn('Hypotheses and falsifiers',(store.root(self.ws)/'research_state.md').read_text('utf8'))
    def test_forged_quote_and_no_source_gates(self):
        engine.new_cycle(self.ws,self.config)
        t=self.task();self.submit(t,self.response)
        t=self.task();bad=self.response('MECHANISM','rce_method_sol')
        bad['observations'][0]['quote']='A quote deliberately absent from both genuine source documents.'
        path=self.ws/'bad.json';store.write(path,bad)
        with self.assertRaisesRegex(ValueError,'not present'):
            engine.collect(self.ws,t['job_id'],'rce_method_sol',path,'independent-thread-A')
        self.assertEqual(engine.stage(self.ws)[1],'MECHANISM')
        self.assertEqual(len(store.listrows(self.ws,'claims')),0)
    def test_stale_goals_and_metadata_cannot_make_claims(self):
        engine.new_cycle(self.ws,self.config)
        (self.ws/'goal.md').write_text('新研究主线被偷偷替换为完全不相关方向。','utf8')
        with self.assertRaisesRegex(ValueError,'Macro research goal'):
            engine.prepare(self.ws,self.config,rce._reserve)
    def test_budget_pause_no_extra_subagent(self):
        config=copy.deepcopy(self.config);config['budget']['max_native_assignments_per_cycle']=1
        store.write(self.ws/rce.CONF,config)
        engine.new_cycle(self.ws,config)
        t=engine.prepare(self.ws,config,rce._reserve)
        self.submit(t,self.response)
        with self.assertRaisesRegex(rce.BudgetPause,'BUDGET_PAUSED'):
            engine.prepare(self.ws,config,rce._reserve)
        self.assertEqual(rce.budget(self.ws,config)['reserved_assignments'],1)
    def test_replay_fails_on_other_native_thread(self):
        engine.new_cycle(self.ws,self.config);task=self.task()
        obj=self.response('MAP',task['roles'][0]);p=self.ws/'map.json';store.write(p,obj)
        res=engine.collect(self.ws,task['job_id'],task['roles'][0],p,'same-thread-for-first')
        self.assertEqual(res['status'],'VERIFIED')
        self.assertEqual(engine.collect(self.ws,task['job_id'],task['roles'][0],p,'same-thread-for-first')['status'],'ALREADY_COLLECTED')
    def test_recover_db_stage_event_from_crash(self):
        engine.new_cycle(self.ws,self.config);task=self.task()
        self.submit(task,self.response)
        # Re-run after a successful commit is idempotent, not duplicate data
        old=engine.commit(self.ws,task['job_id'])
        self.assertEqual(old['status'],'COMMITTED')
        self.assertEqual(len(store.listrows(self.ws,'questions')),1)
    def test_harness_trial_rejects_guardrail_edits_and_can_adopt_with_veto_gate(self):
        engine.new_cycle(self.ws,self.config); self.submit(self.task(),self.response)
        base=rce.config(self.ws)
        with self.assertRaisesRegex(ValueError,'Only allowlisted'):
            harness.propose(self.ws,{'academic_gate':{'accept_anything':True}},'We observed a serious classification failure that repeatedly omitted task-related methods.', ['RC0001_MAP'],base,'rce-harness-proposer-thread-12345')
        patch={'ranking':{'relevance':1.5,'uncertainty':1.5,'coverage':2.5,'recency':0.7,'cost':1.0}}
        proposed=harness.propose(self.ws,patch,'Repeated keyphrase overfitting misses partial-observation mechanism papers and valuable negative evidence.',['RC0001_MAP'],base,'rce-harness-proposer-thread-12345')
        pid=proposed['proposal_id']
        run=harness.probe(self.ws,pid,base)
        self.assertTrue(run['candidate_passed_offline_probe'])
        self.assertGreater(run['improvement'],0)
        review={'proposal_id':pid,'reviewer_role':'rce_evolution_auditor_astra','thread_ref':'rce-evo-auditor-12345',
                'verdict':'PASS','reason':'The independent holdout ranking improved and no critical case regressed; approved only for prioritization weights.'}
        self.assertEqual(harness.adopt(self.ws,pid,review,base)['status'],'ADOPTED')
        new=rce.config(self.ws)
        self.assertEqual(new['ranking']['relevance'],1.5)
        self.assertEqual(harness.state(self.ws)['revision'],1)
        self.assertEqual(harness.rollback(self.ws,'Evidence regression detected during subsequent tasks.',True)['status'],'ROLLED_BACK')
        self.assertEqual(rce.config(self.ws)['ranking']['relevance'],base['ranking']['relevance'])
    def test_harness_probe_cannot_pass_unchanged_canary(self):
        engine.new_cycle(self.ws,self.config); self.submit(self.task(),self.response)
        base=rce.config(self.ws)
        patch={'ranking':{'relevance':2.7}}
        pid=harness.propose(self.ws,patch,'An isolated user task showed a ranking failure; check whether boosting keyword relevance actually helps.', ['RC0001_MAP'],base,'rce-harness-proposer-thread-67890')['proposal_id']
        probed=harness.probe(self.ws,pid,base)
        self.assertFalse(probed['candidate_passed_offline_probe'])
        review={'proposal_id':pid,'reviewer_role':'rce_evolution_auditor_astra','thread_ref':'evo-independent-12345',
                'verdict':'PASS','reason':'I favor the patch, but the holdout did not improve and must therefore reject this proposal.'}
        self.assertEqual(harness.adopt(self.ws,pid,review,base)['status'],'REJECTED')
    def test_catalogue_is_bibliographic_not_fulltext(self):
        with store.connect(self.ws) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM works WHERE source_status='TEXT_AVAILABLE'").fetchone()[0],2)
        with tempfile.TemporaryDirectory() as d:
            w=pathlib.Path(d);(w/'goal.md').write_text((self.ws/'goal.md').read_text('utf8'),'utf8')
            self.catalogue(w);rce.init(w);store.import_catalogue(w)
            with store.connect(w) as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM claims").fetchone()[0],0)
            engine.new_cycle(w,rce.config(w));t=engine.prepare(w,rce.config(w),rce._reserve)
            role=t['roles'][0];path=w/'answer.json';store.write(path,self.response('MAP',role))
            engine.collect(w,t['job_id'],role,path,'independent-map-subagent-1234')
            engine.commit(w,t['job_id'])
            with self.assertRaisesRegex(ValueError,'NO_FULLTEXT'):
                engine.prepare(w,rce.config(w),rce._reserve)

if __name__=='__main__':unittest.main()
