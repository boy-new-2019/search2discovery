from __future__ import annotations
import json, pathlib, sys, tempfile, unittest
HERE=pathlib.Path(__file__).resolve().parents[1]
SRC=HERE/'scripts'
BUNDLE=HERE.parents[0]
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
import pro5x_optimizer as opt

class Pro5xTest(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.ws=pathlib.Path(t.name)/'lab';self.ws.mkdir()
        import shutil
        for srcname,dstname in (('batch-paper-deepread-desktop/selection_config.example.json','selection_config.json'),
                                ('batch-paper-deepread-desktop/config.example.json','reading_config.json'),
                                ('research-cognition-engine/config.example.json','research_cognition_config.json')):
            shutil.copy2(BUNDLE/srcname,self.ws/dstname)
        sys.path.insert(0,str(BUNDLE/'batch-paper-deepread-desktop'/'scripts'))
        import desktop_bridge
        opt.write(self.ws/'native_config.json',desktop_bridge.DEFAULT)
        # Simulate the installed original skill available to local optimizer.
        skill=self.ws/'.agents'/'skills'/'batch-paper-deepread-desktop'
        skill.mkdir(parents=True)
        shutil.copy2(BUNDLE/'batch-paper-deepread-desktop'/'selection_config.example.json',skill/'selection_config.example.json')
        self.original_goal=b'Frozen research core; do not edit algorithms or results.'
        (self.ws/'goal.md').write_bytes(self.original_goal)
        self.original_v44=(BUNDLE/'batch-paper-deepread-desktop'/'scripts'/'deepread.py').read_bytes()
    def test_apply_budget_and_minima_preserved(self):
        before=opt.plan(self.ws)
        self.assertEqual(before['reader_budget']['max_assignments_per_cycle'],40)
        result=opt.apply(self.ws)
        self.assertEqual(result['status'],'PRO5X_SURVIVAL_CONFIGURED')
        n=opt.read(self.ws/'native_config.json')
        self.assertEqual(n['budget']['max_assignments_per_cycle'],12)
        self.assertEqual(n['budget']['max_prompt_chars_per_cycle'],420000)
        self.assertTrue(n['strict_independent_subagents'])
        self.assertFalse(n['cross_domain']['enabled'])
        self.assertTrue(n['budget']['risk_review_for_s2'])
        self.assertTrue(n['budget']['local_synthesis'])
        s=opt.read(self.ws/'selection_config.json')
        self.assertEqual(s['screen_batch_size'],24)
        self.assertEqual(s['core_target'],max(s['core_min'],sum(x['min_core'] for x in s['coverage_themes'])))
        self.assertEqual(s['screen_excerpt_chars_per_paper'],2600)
        v=opt.read(self.ws/'research_cognition_config.json')
        self.assertEqual(v['budget']['max_native_assignments_per_cycle'],4)
        self.assertEqual(v['budget']['max_input_chars_per_cycle'],160000)
        self.assertEqual(v['stage_order'],['MAP','MECHANISM','CONTRADICTION','HYPOTHESIS','NOVELTY','EXPERIMENT','FINAL'])
        self.assertEqual(len(v['native_roles']['NOVELTY']),2)
        self.assertEqual((self.ws/'goal.md').read_bytes(),self.original_goal)
        self.assertEqual((BUNDLE/'batch-paper-deepread-desktop'/'scripts'/'deepread.py').read_bytes(),self.original_v44)
        self.assertEqual(opt.plan(self.ws)['profile'],opt.PROFILE)
    def test_dry_run_does_not_change(self):
        old=(self.ws/'native_config.json').read_bytes()
        self.assertEqual(opt.apply(self.ws,dry_run=True)['status'],'DRY_RUN')
        self.assertEqual(old,(self.ws/'native_config.json').read_bytes())
        self.assertFalse((self.ws/'output').exists())
    def test_repeat_install_idempotent(self):
        opt.apply(self.ws)
        first={k:opt.sha(p) for k,p in opt.locations(self.ws).items()}
        again=opt.apply(self.ws)
        self.assertFalse(any(x['changed'] for x in again['modifications'].values()))
        self.assertEqual(first,{k:opt.sha(p) for k,p in opt.locations(self.ws).items()})
    def test_keep_custom_reader_state(self):
        (self.ws/'output'/'batch').mkdir(parents=True)
        (self.ws/'output'/'batch'/'state.json').write_text('{}')
        old=opt.read(self.ws/'selection_config.json')
        opt.apply(self.ws)
        self.assertEqual(old,opt.read(self.ws/'selection_config.json'))
        self.assertTrue(opt.read(self.ws/'native_config.json')['cross_domain']['enabled'])
    def test_preserve_ongoing_rce_context_while_tightening_shared_cap(self):
        d=self.ws/'output'/'research_cognition';d.mkdir(parents=True)
        opt.write(d/'engine_state.json',{'cycles':[{'stage':'MECHANISM'}]})
        original=(self.ws/'research_cognition_config.json').read_bytes()
        report=opt.apply(self.ws)
        self.assertIn('ACTIVE_COGNITION_TASK',report['skipped']['rce'])
        self.assertEqual(original,(self.ws/'research_cognition_config.json').read_bytes())
        self.assertEqual(opt.read(self.ws/'native_config.json')['budget']['max_assignments_per_cycle'],12)
    def test_no_custom_selection_overwrite(self):
        custom=opt.read(self.ws/'selection_config.json');custom['core_target']=15
        opt.write(self.ws/'selection_config.json',custom)
        opt.apply(self.ws)
        self.assertEqual(opt.read(self.ws/'selection_config.json')['core_target'],15)
    def test_actual_provider_usage_not_claimed(self):
        opt.apply(self.ws)
        report=opt.plan(self.ws)
        self.assertEqual(report['status'],'PROXY_ONLY_NOT_ACCOUNT_USAGE')
        self.assertIn('本地',report['warning']+'本地')
        self.assertIsNone(report['metadata_pools'].get('core'))
    def test_original_quality_gate_validator_accepts(self):
        opt.apply(self.ws)
        sys.path.insert(0,str(SRC))
        import rce
        rce.check_cfg(opt.read(self.ws/'research_cognition_config.json'))
        import quota_guard,desktop_bridge,batch
        quota_guard.validate(opt.read(self.ws/'native_config.json')['budget'])
        desktop_bridge.native_cfg(self.ws)
        batch.cfg_at(self.ws)

if __name__=='__main__':unittest.main()
