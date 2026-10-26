from __future__ import annotations
import pathlib,sys,tempfile,unittest,concurrent.futures
SKILL=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL/'scripts'))
import store,rce

class BudgetLinks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.ws=pathlib.Path(self.tmp.name)
        (self.ws/'goal.md').write_text('流式三维占用预测与世界模型的状态修订，原论文核心固定不变并保持数据和协议真实。','utf8')
        rce.init(self.ws)
    def tearDown(self):self.tmp.cleanup()
    def test_parallel_reservations_do_not_exceed_cycle_budget(self):
        cfg=rce.config(self.ws)
        cfg['budget']['max_native_assignments_per_cycle']=3
        store.write(self.ws/rce.CONF,cfg)
        def call(i):
            try:rce._reserve(self.ws,cfg,{f'RCE:mock-assignment-{i}':250});return 'OK'
            except rce.BudgetPause:return 'PAUSED'
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            result=list(pool.map(call,range(12)))
        self.assertEqual(result.count('OK'),3)
        self.assertEqual(rce.budget(self.ws,cfg)['reserved_assignments'],3)
        self.assertEqual(result.count('PAUSED'),9)
    def test_linked_budget_uses_v44_guard_when_available(self):
        scripts=self.ws/'.agents/skills/batch-paper-deepread-desktop/scripts'
        scripts.mkdir(parents=True)
        (scripts/'quota_guard.py').write_text('''from pathlib import Path\nfrom contextlib import contextmanager\nimport json\ndef validate(c):\n if "max_assignments_per_cycle" not in c: raise ValueError("bad native budget")\ndef reserve(ws,c,requests):\n p=ws/"linked_native_used.json"\n current=json.loads(p.read_text()) if p.exists() else []\n if len(current)+len(requests)>c["max_assignments_per_cycle"]:raise ValueError("NATIVE_QUOTA_STOP")\n current.extend(requests)\n p.write_text(json.dumps(current))\n return {"new":len(requests)}\ndef renew(ws,c,label,user_authorized=False):\n pass\ndef status(ws,c):\n return {"native_link":"VERIFIED_TEST", "used":len(json.loads((ws/"linked_native_used.json").read_text())) if (ws/"linked_native_used.json").exists() else 0}\n''','utf8')
        store.write(self.ws/'native_config.json',{'budget':{'max_assignments_per_cycle':1}})
        cfg=rce.config(self.ws)
        result=rce._reserve(self.ws,cfg,{'RC0001_MAP:cartographer':100})
        self.assertTrue(result['linked_v44_budget'])
        self.assertEqual(rce.status(self.ws)['shared_v44_budget']['used'],1)
        with self.assertRaisesRegex(ValueError,'NATIVE_QUOTA_STOP'):
            rce._reserve(self.ws,cfg,{'RC0001_MECHANISM:method':100})
        self.assertEqual(rce.budget(self.ws,cfg)['reserved_assignments'],1)
        self.assertEqual(rce._reserve(self.ws,cfg,{'RC0001_MAP:cartographer':100})['new_reservations'],0)
    def test_budget_period_requires_real_user_approval(self):
        cfg=rce.config(self.ws)
        rce._reserve(self.ws,cfg,{'test-001':500})
        with self.assertRaisesRegex(ValueError,'Explicit user approval'):
            rce.renew(self.ws,'budget-period-nov',False)
        got=rce.renew(self.ws,'budget-period-nov',True)
        self.assertEqual(got['reserved_assignments'],0)
        with self.assertRaisesRegex(ValueError,'reuse'):
            rce.renew(self.ws,'budget-period-nov',True)
        s=store.read(self.ws/'output/research_cognition/local_model_budget.json')
        self.assertEqual(len(s['renewals']),1)

if __name__=='__main__':unittest.main()
