from __future__ import annotations
import json, pathlib, sys, tempfile, unittest
from unittest.mock import patch

SKILL=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL/'scripts'))
import batch, deepread as core, desktop_bridge as app, cross_domain as cross

PRIMARY=('Autonomous vehicle streaming 3D occupancy and evidence memory prediction. '
         'We evaluate scene understanding on nuScenes with streaming image sensors.\n')*12
ECON=('In behavioral economics bounded rationality models choices under limited information. '
      'Agents prefer satisficing procedures when knowledge is costly or incomplete.\n')*18
PHIL=('In the philosophy of science empirical evidence may underdetermine explanatory theories. '
      'Belief revision must consider alternative hypotheses and scope restrictions.\n')*18

class CrossDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.ws=pathlib.Path(self.temp.name)
        self.assertEqual(app.main(['init','--workspace',str(self.ws)]),0)
        (self.ws/'input'/'primary.txt').write_text(PRIMARY,encoding='utf-8')
        app.apply_patch(self.ws,{'research':{'goal_text':'自动驾驶流式3D占用与证据记忆管理',
                    'selection':{'core_min':1,'core_target':1,'core_max':1,
                                 'min_supplemental_pdfs':0,'min_supplemental_qualified':0,
                                 'coverage_themes':[{'name':'3D Occupancy/BEV','min_core':1}]}},
                    'native':{'allow_native_model_calls':True,'cross_domain':{
                        'checkpoints':['AFTER_S2','AFTER_R2','AFTER_R4'],
                        'max_papers_total':9,'max_papers_per_checkpoint':3,
                        'max_model_assignments':36,'max_discovery_waves':2,
                        'max_download_total':12}}})
        batch.ingest(self.ws)
    def tearDown(self): self.temp.cleanup()
    def screen_and_select(self):
        while True:
            state=batch.load_state(self.ws);job=batch.next_screen(self.ws,state)
            if job is None:break
            _,ex=batch.make_screen_prompt(self.ws,state,job)
            data=[]
            for pid in job['group']['paper_ids']:
                seg=next(x for x in ex[pid] if x['text'])
                data.append({'paper_id':pid,'summary':job['stage']+' Streaming three-dimensional occupancy with historical observations',
                            'verdict':'LIKELY_RELEVANT','theme':'3D Occupancy/BEV',
                            'scores':{'topic':4.7,'method':4.7,'trajectory':4.6,'evidence_quality':4.6},
                            'evidence':[{'page':seg['page'],'quote':seg['text'][:70]}],
                            'uncertainty':'none','reason':job['stage']+' 本篇采用streaming感知与记忆历史证据'})
            p=self.ws/'screen_result.json';core.jwrite(p,{'stage':job['stage'],'papers':data})
            batch.screen_submit(self.ws,state,job['id'],p)
        batch.select_core(self.ws,batch.load_state(self.ws))
    def local_source(self,domain='nobel_economics',name='econ.md',body=ECON):
        f=self.ws/'cross_domain_input'/domain/name
        f.parent.mkdir(parents=True,exist_ok=True);f.write_text(body,'utf-8')
        cross.ingest(self.ws,app.native_cfg(self.ws)['cross_domain'])
        return cross.load(self.ws)['sources'][-1]
    def member(self,job,role,idea=True):
        source=next(s for s in cross.load(self.ws)['sources'] if s['id']==job['source_id'])
        pages=cross.verify_source(self.ws,source)
        quote=pages[0][:75]
        body={'job_id':job['id'],'source_id':job['source_id'],'role':role,'domain_assessment':'CROSS_DOMAIN',
              'verdict':'POSSIBLE_TRANSFER' if idea else 'NO_TRANSFER',
              'source_summary':'作者讨论有限信息条件下决策机制与理论边界，并以其所属学科的证据论证学术命题。',
              'source_evidence':[{'page':1,'quote':quote}],
              'hypotheses':[{'idea':'是否可以将有限信息决策类比为历史状态保持和更新这一研究疑问',
                             'source_support':[{'page':1,'quote':quote}],
                             'mapping':'以有限理性机制类比部分可观测条件下有限证据保持',
                             'target_problem':'有限历史观察下的流式记忆维护问题',
                             'assumptions':'决策过程与记忆策略之间存在形式化的代价对应关系',
                             'breakdown':'若优化目标或信息结构不一致则类比可能完全失败',
                             'cheap_test':'构造成本约束基线并进行同数据量的受控反事实实验',
                             'confidence':'low'}] if idea else [],
              'no_transfer_reason':'' if idea else '本论文的观测对象与目标研究之间缺少清晰的机制映射，无法提出可证伪的研究假设。',
              'uncertainty':['跨域概念一致性仍然缺少论证'],'non_transferable':['不能直接把经济学因果结论认定为车辆实验表现提升']}
        return body
    def lead(self,job,source,idea=True):
        quote=cross.verify_source(self.ws,source)[0][:75]
        return {'job_id':job['id'],'source_id':job['source_id'],
                'verdict':'IDEAS' if idea else 'NO_VALID_TRANSFER',
                'ideas':[{'hypothesis':'从经济学有限理性理论激发一种在有限历史信息下决策保留的验证性研究问题',
                           'source_support':[{'page':1,'quote':quote}],
                           'source_mechanism':'有限信息与决策成本导致有限理性的选择机制',
                           'target_mapping':'用于检验车辆记忆管理中资源受限时的历史信息保留',
                           'assumptions':'两边的信息成本可定义且与决策目标兼容',
                           'failure_conditions':'任务价值函数不同使其无法建立可比的单调关系',
                           'smallest_validation':'对比随机、固定与效用策略在相同算力约束下的消融实验',
                           'confidence':'low'}] if idea else [],
                'rejected_analogies':['信息效用与认知偏差存在结构差别，不能认定对应机制已经得到证明'],
                'disagreements':['类比专家主张可作为探索，反方认为只可做前提验证'],
                'uncertainties':['真实自动驾驶任务相关性仍待证明'],
                'reason_if_none':'' if idea else '全部专家未提出具有对应结构的机制映射，仅保留失败分析备忘，不作为课题创新。',
                'macro_direction_unchanged':True,'confirmed_paper_core_unchanged':True}
    def test_no_cross_domain_paper_in_main_corpus(self):
        self.local_source()
        self.assertEqual(len(batch.load_state(self.ws)['papers']),1)
        self.assertEqual(cross.status(self.ws)['readable_sources'],1)
    def test_cross_domain_requires_s2_and_selection(self):
        self.local_source()
        self.assertEqual(app.prepare(self.ws)['phase'],'SCREEN')
        self.screen_and_select()
        j=app.prepare(self.ws)
        self.assertEqual(j['phase'],'CROSS')
        self.assertEqual(j['roles'],list(cross.MEMBERS))
        self.assertEqual(len(set(v['model_requested'] for v in j['model_requests'].values())),2)
    def test_independent_members_and_captain_commit(self):
        self.local_source();self.screen_and_select()
        task=app.prepare(self.ws);jobid=task['job_id'];job=core.jread(app.task_dir(self.ws,jobid)/'manifest.json')['job']
        for n,role in enumerate(task['roles']):
            f=app.task_dir(self.ws,jobid)/'answers'/(role+'.json')
            core.jwrite(f,self.member(job,role))
            result=app.collect(self.ws,jobid,role,f,'cross-independent-'+str(n))
            self.assertEqual(result['status'],'VERIFIED')
        captain=app.commit(self.ws,jobid)
        self.assertEqual(captain['status'],'NEED_CAPTAIN')
        self.assertTrue(pathlib.Path(captain['captain_prompt']).exists())
        source=cross._source(self.ws,job['source_id'])
        f=app.task_dir(self.ws,jobid)/'captain_answer.json';core.jwrite(f,self.lead(job,source))
        with self.assertRaises(ValueError):
            app.commit(self.ws,jobid,f)
        with self.assertRaises(ValueError):
            app.commit(self.ws,jobid,f,'cross-independent-1')
        done=app.commit(self.ws,jobid,f,'captain-independent-10')
        self.assertEqual(done['status'],'COMMITTED')
        self.assertEqual(len(cross.load(self.ws)['results']),1)
        self.assertIn('Proposed smallest validation PLAN',(self.ws/'output'/'cross_domain'/'idea_bank.md').read_text('utf-8'))
        self.assertEqual(len(batch.load_state(self.ws)['papers']),1)
        self.assertEqual(app.prepare(self.ws)['status'],'SCREENING_DONE')
    def test_false_evidence_is_rejected(self):
        source=self.local_source();job={'id':'XD_test_'+source['id'],'type':'cross','checkpoint':'AFTER_S2','source_id':source['id']}
        payload=self.member(job,'bpd_cross_scholar_sol')
        payload['source_evidence'][0]['quote']='This phrase is definitely absent from the source file.'
        with self.assertRaises(ValueError):
            cross.validate_member(self.ws,job,payload,'bpd_cross_scholar_sol')
    def test_all_reject_cannot_be_rewritten_as_innovation(self):
        source=self.local_source();job={'id':'XD_test_'+source['id'],'type':'cross','checkpoint':'AFTER_S2','source_id':source['id']}
        views={r:self.member(job,r,idea=False) for r in cross.MEMBERS}
        with self.assertRaises(ValueError):
            cross.validate_lead(self.ws,job,views,self.lead(job,source,idea=True))
        self.assertEqual(cross.validate_lead(self.ws,job,views,self.lead(job,source,idea=False))['verified_citations'],0)
    def test_discovery_requires_explicit_authorization(self):
        self.local_source()
        with self.assertRaises(ValueError):
            cross.discover(self.ws,app.native_cfg(self.ws)['cross_domain'],online=False,download=False)
    def test_metadata_not_counted_as_paper(self):
        self.local_source()
        fake={'id':'https://openalex.org/W98764321','display_name':'A new philosophical analysis of scientific reasoning',
              'doi':'10.1234/fake','publication_year':2024,
              'best_oa_location':{'pdf_url':'https://example.org/academic.pdf'}}
        with patch.object(batch,'search_openalex',return_value=[fake]):
            result=cross.discover(self.ws,app.native_cfg(self.ws)['cross_domain'],online=True,download=False)
        self.assertEqual(result['downloaded_pdf'],0)
        self.assertEqual(cross.status(self.ws)['readable_sources'],1)
        self.assertEqual(len(cross.load(self.ws)['proposals']),1)
    def test_prompt_can_control_bounds(self):
        app.apply_patch(self.ws,{'native':{'cross_domain':{'random_seed':1234,'max_papers_total':2,
                     'max_model_assignments':8,'checkpoints':['AFTER_S2'],'max_papers_per_checkpoint':2}}})
        cfg=app.native_cfg(self.ws)['cross_domain']
        self.assertEqual(cfg['random_seed'],1234)
        self.assertEqual(cfg['max_papers_total'],2)
        with self.assertRaises(ValueError):
            app.apply_patch(self.ws,{'native':{'cross_domain':{'max_papers_total':100}}})
        with self.assertRaises(ValueError):
            app.apply_patch(self.ws,{'native':{'cross_domain':{'domains':['automated_driving']}}})
    def test_repeatable_drawing_and_domain_balance(self):
        self.local_source();self.local_source('philosophy','phil.md',PHIL)
        self.screen_and_select()
        cfg={**app.native_cfg(self.ws)['cross_domain'],'max_papers_per_checkpoint':2}
        j=cross.maybe_next_job(self.ws,cfg,batch.load_state(self.ws),None)
        self.assertEqual(j['checkpoint'],'AFTER_S2')
        self.assertEqual(len(cross.load(self.ws)['checkpoints']['AFTER_S2']['jobs']),2)
        j2=cross.maybe_next_job(self.ws,cfg,batch.load_state(self.ws),None)
        self.assertEqual(j,j2)
        roots=cross.load(self.ws)['sources']
        jobs=cross.load(self.ws)['checkpoints']['AFTER_S2']['jobs']
        domains=[next(x['domain'] for x in roots if x['id']==row['source_id']) for row in jobs]
        self.assertEqual(len(set(domains)),2)
    def test_copy_pdf_to_wrong_domain_rejected(self):
        root=self.ws/'cross_domain_input';root.mkdir(parents=True)
        (root/'unclassified.md').write_text(ECON,'utf-8')
        with self.assertRaises(ValueError):
            cross.ingest(self.ws,app.native_cfg(self.ws)['cross_domain'])
    def test_no_automatic_modification_of_research_route(self):
        original=core.file_hash(self.ws/'goal.md')
        self.local_source();self.screen_and_select();cross.maybe_next_job(self.ws,app.native_cfg(self.ws)['cross_domain'],batch.load_state(self.ws),None)
        self.assertEqual(core.file_hash(self.ws/'goal.md'),original)
        self.assertFalse(batch.load_state(self.ws)['frozen'])
    def test_resume_existing_captain_at_exhausted_budget(self):
        source=self.local_source();self.screen_and_select()
        task=app.prepare(self.ws);jid=task['job_id'];job=core.jread(app.task_dir(self.ws,jid)/'manifest.json')['job']
        for idx,role in enumerate(task['roles']):
            f=app.task_dir(self.ws,jid)/'answers'/(role+'.json')
            core.jwrite(f,self.member(job,role));app.collect(self.ws,jid,role,f,'reader-thread-'+str(idx))
        captain=app.task_dir(self.ws,jid)/'captain_answer.json';core.jwrite(captain,self.lead(job,source))
        app.apply_patch(self.ws,{'native':{'max_total_subagent_invocations':4}})
        app.commit(self.ws,jid,captain,'captain-thread-unique')
        (app.task_dir(self.ws,jid)/'commit.json').unlink()
        resumed=app.commit(self.ws,jid,captain,'captain-thread-unique')
        self.assertEqual(resumed['route'],'RECOVER_EXISTING_IMMUTABLE_RESULT')

    def test_actual_pdf_fulltext_extraction(self):
        import fitz
        folder=self.ws/'cross_domain_input'/'philosophy'
        folder.mkdir(parents=True,exist_ok=True)
        pdf=folder/'philosophy_science.pdf'
        document=fitz.open()
        for i in range(3):
            page=document.new_page(width=595,height=842)
            text=('Scientific explanations remain open to alternative interpretations of evidence.\n'*13)
            page.insert_text((45,50),text,fontsize=10)
        document.save(pdf);document.close()
        result=cross.ingest(self.ws,app.native_cfg(self.ws)['cross_domain'])
        self.assertEqual(result['added'],1)
        source=cross.load(self.ws)['sources'][0]
        self.assertEqual(source['status'],'READY')
        self.assertEqual(len(cross.verify_source(self.ws,source)),3)

    def test_source_tampering_blocks_old_citations(self):
        source=self.local_source()
        path=self.ws/'cross_domain_input'/source['file']
        path.write_text(ECON+' forged late paragraph',encoding='utf-8')
        with self.assertRaises(ValueError):
            cross.verify_source(self.ws,source)
        with self.assertRaises(ValueError):
            cross.ingest(self.ws,app.native_cfg(self.ws)['cross_domain'])

    def test_three_checkpoint_waves_are_independent(self):
        # Simulates the deterministic sidecar state at the R3/R5 phase barrier.
        for i,domain in enumerate(['nobel_economics','philosophy','sociology','ecology','mathematics','design_theory']):
            self.local_source(domain, f'source_{i}.md', ECON+str(i)*90)
        self.screen_and_select()
        cfg={**app.native_cfg(self.ws)['cross_domain'],
             'max_papers_per_checkpoint':2,'max_papers_total':6,'max_model_assignments':24}
        state=batch.load_state(self.ws)
        source_state=cross.load(self.ws)
        draw=cross.maybe_next_job(self.ws,cfg,state,None)
        self.assertEqual(draw['checkpoint'],'AFTER_S2')
        self.assertEqual(len(cross.load(self.ws)['checkpoints']['AFTER_S2']['jobs']),2)
        # Complete only the sidecar's selected work; the primary core remains untouched.
        for item in cross.load(self.ws)['checkpoints']['AFTER_S2']['jobs']:
            job={'id':item['id'],'type':'cross','checkpoint':'AFTER_S2','source_id':item['source_id']}
            views={r:self.member(job,r) for r in cross.MEMBERS}
            cross.commit(self.ws,{'job':job},views,self.lead(job,cross._source(self.ws,job['source_id'])),{r:'test_hash' for r in views})
        frozen=batch.load_state(self.ws);frozen['frozen']={'core_workspace':'does_not_need_to_exist_here'}
        batch.save_state(self.ws,frozen)
        after_r2=cross.maybe_next_job(self.ws,cfg,batch.load_state(self.ws),{'type':'leaf','round':3})
        self.assertEqual(after_r2['checkpoint'],'AFTER_R2')
        for item in cross.load(self.ws)['checkpoints']['AFTER_R2']['jobs']:
            job={'id':item['id'],'type':'cross','checkpoint':'AFTER_R2','source_id':item['source_id']}
            views={r:self.member(job,r) for r in cross.MEMBERS}
            cross.commit(self.ws,{'job':job},views,self.lead(job,cross._source(self.ws,job['source_id'])),{r:'test_hash' for r in views})
        after_r4=cross.maybe_next_job(self.ws,cfg,batch.load_state(self.ws),{'type':'leaf','round':5})
        self.assertEqual(after_r4['checkpoint'],'AFTER_R4')
        self.assertEqual(cross.status(self.ws)['drawn'],6)

    def test_global_budget_includes_required_captain(self):
        self.local_source();self.screen_and_select()
        app.apply_patch(self.ws,{'native':{'max_total_subagent_invocations':3}})
        with self.assertRaises(ValueError):
            app.prepare(self.ws)

    def test_crash_recovery_does_not_duplicate_result(self):
        source=self.local_source();self.screen_and_select()
        task=app.prepare(self.ws);jobid=task['job_id'];job=core.jread(app.task_dir(self.ws,jobid)/'manifest.json')['job']
        for idx,role in enumerate(task['roles']):
            file=app.task_dir(self.ws,jobid)/'answers'/(role+'.json')
            core.jwrite(file,self.member(job,role));app.collect(self.ws,jobid,role,file,'unique-thread-'+str(idx))
        capt=app.task_dir(self.ws,jobid)/'captain_answer.json'
        core.jwrite(capt,self.lead(job,source))
        app.commit(self.ws,jobid,capt,'captain-thread-independent')
        root=app.task_dir(self.ws,jobid)
        (root/'commit.json').unlink()  # crash between journal save and final commit record
        repeated=app.commit(self.ws,jobid,capt,'captain-thread-independent')
        self.assertEqual(repeated['route'],'RECOVER_EXISTING_IMMUTABLE_RESULT')
        self.assertEqual(len(cross.load(self.ws)['results']),1)

    def test_v42_native_config_upgrade_without_losing_settings(self):
        path=self.ws/'native_config.json';saved=core.jread(path);saved.pop('cross_domain');core.jwrite(path,saved)
        self.assertEqual(app.main(['init','--workspace',str(self.ws)]),0)
        cfg=app.native_cfg(self.ws)
        self.assertEqual(cfg['cross_domain']['random_seed'],3407)
        self.assertTrue(cfg['allow_native_model_calls'])
        self.assertEqual(len(batch.load_state(self.ws)['papers']),1)

if __name__=='__main__':unittest.main()
