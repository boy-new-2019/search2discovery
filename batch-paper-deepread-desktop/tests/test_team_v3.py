"""Offline simulations of independent specialist orchestration; no real AI claims."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import batch
import deepread as core
import team
import configure
import test_batch
import test_deepread


def enable_ws(ws, n=3):
    batch.init(ws)
    c=batch.cfg_at(ws)
    c.update({"screen_batch_size":2,"core_min":1,"core_target":2,"core_max":3,
              "min_supplemental_pdfs":0,"min_supplemental_qualified":0,"max_discovery_waves":0})
    for t in c["coverage_themes"]:
        t["min_core"]=0
    core.jwrite(ws/"selection_config.json",c)
    for i in range(n):
        (ws/"input"/f"paper{i:04d}.md").write_text((test_batch.TEXT_REL if i<2 else test_batch.TEXT_IRREL)*2+str(i),encoding="utf-8")
    return batch.ingest(ws)


class V3TeamTests(unittest.TestCase):
    def test_two_screening_rounds_distinct_agents_and_persistent_veto(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d);state=enable_ws(ws,3)
            def fake_call(_ws,_conf,role,engine,prompt,jid,attempt):
                stage=jid.split("_")[0]
                g=next(g for g in state["groups"] if batch.stage_jid(stage,g)==jid)
                job={"id":jid,"stage":stage,"group":g}
                if role=="skeptic" and any(p["file"]=="paper0000.md" for p in state["papers"]):
                    rel_files={"paper0001.md"}
                else:
                    rel_files={"paper0000.md","paper0001.md"}
                ans=test_batch.make_model_response(ws,state,job,relevant_files=rel_files)
                return core.dump(ans),"SYNTHETIC_MODEL_"+role
            with patch.object(team,"call_single",side_effect=fake_call) as spy:
                n=batch.screen_auto(ws,state,"codex",None)
            self.assertEqual(n,4)
            self.assertGreaterEqual(spy.call_count,12)  # 3 independent experts on each of 4 batches
            self.assertLessEqual(spy.call_count,18)  # adaptive captain can save unanimous batches
            self.assertTrue((team.task_dir(ws,'S1_B00002')/'consensus.json').exists())
            self.assertTrue(batch.done(ws,"S1_B00001"))
            flag=team.dissent_for_screen(ws,"S1_B00001")
            self.assertTrue(flag)
            decision=batch.select_core(ws,state)
            self.assertEqual(next(x["decision"] for x in decision["decisions"] if x["file"]=="paper0000.md"),"HOLD")
            self.assertEqual(next(x["decision"] for x in decision["decisions"] if x["file"]=="paper0002.md"),"REJECT")
            jid="S1_B00001"
            cert=team.task_dir(ws,jid)/"team_certificate.json"
            cert.unlink()
            self.assertFalse(batch.done(ws,jid))

    def test_core_leaf_3_readers_leader_and_audit_single_veto(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d)
            core.init(ws)
            shutil_team=ROOT/"team_config.example.json"
            (ws/"team_config.json").write_bytes(shutil_team.read_bytes())
            c=core.config_for(ws);c["max_audit_repairs"]=0
            core.jwrite(ws/"reading_config.json",c)
            (ws/"input"/"A.md").write_text((test_batch.TEXT_REL)*3,encoding="utf-8")
            core.ingest(ws);ctx=core.env(ws)
            seen=[]
            def fake_call(_ws,_conf,role,engine,prompt,jid,attempt):
                job=core.next_job(ctx)
                self.assertEqual(jid,job["id"])
                ans=test_deepread.response(ctx,job,veto=job["type"]=="audit" and role=="audit_methods")
                if job["type"]=="leaf":
                    ans["observations"][0]["claim"]+=f" [{role}]"
                seen.append((jid,role))
                return core.dump(ans),"SYNTH_"+role
            with patch.object(team,"call_single",side_effect=fake_call):
                core.run_auto(ctx,"codex",None)
            self.assertEqual(core.run_status(ctx)["status"],"AUDIT_VETO")
            leaf=next(x for x in seen if x[0].startswith("R01_") and "_C" in x[0])
            self.assertTrue(leaf)
            self.assertTrue(core.completed(ctx,leaf[0]))
            data=core.answer(ctx,leaf[0])
            self.assertGreaterEqual(len(data["observations"]),3)
            self.assertTrue((team.task_dir(ws,leaf[0])/"leaf_fusion.json").exists())
            audit=core.answer(ctx,"AUDIT_v0")
            self.assertEqual(audit["jury"],{"audit_evidence":"PASS","audit_methods":"VETO"})
            self.assertEqual(audit["verdict"],"VETO")
            self.assertFalse((ctx["run"]/"reading_report.md").exists())

    def test_prompt_hyperparameters_atomic_and_runtime_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d);batch.init(ws)
            patch1={"reading":{"rounds":7,"codex":{"models":{"r6":"custom-model-r6"}}},
                    "selection":{"screen_batch_size":10,"core_min":10,"core_target":25,"core_max":40,
                                 "coverage_themes":[{"name":"World Model","min_core":2}]},
                    "team":{"rosters":{"R6":["method","skeptic"],"R7":["transfer","skeptic"]},
                            "agents":{"skeptic":{"codex_model":"new-auditor-x","effort":"medium"}},
                            "execution":{"max_global_parallel_calls":7,"max_total_model_calls_per_workspace":8000}},
                    "run":{"engine":"codex","max_jobs_per_launch":35,"allow_model_calls":True},
                    "goal_text":"研究世界模型与自动驾驶时序记忆的交叉领域。"}
            result=configure.apply_patch(ws,patch1,user_instruction="7轮、总经理带队、多代理学术审查")
            self.assertEqual(configure.validate_all(ws)["rounds"],7)
            self.assertTrue(result["source_instruction_sha256"])
            self.assertEqual(core.jread(ws/"team_config.json")["agents"]["skeptic"]["codex_model"],"new-auditor-x")
            with self.assertRaises(ValueError):
                configure.apply_patch(ws,{"team":{"execution":{"invented_knob":34}}})
            self.assertEqual(configure.validate_all(ws)["rounds"],7)
            with self.assertRaises(RuntimeError):
                configure.apply_patch(ws,{"reading":{"rounds":3}})
            self.assertEqual(configure.validate_all(ws)["rounds"],7)
            with self.assertRaises(RuntimeError):
                configure.apply_patch(ws,{"team":{"arbitration":{"veto_on_any_audit_failure":False}}})
            self.assertEqual(core.jread(ws/"team_config.json")["arbitration"]["veto_on_any_audit_failure"],True)

    def test_semantic_lock_allows_models_retries_budgets_but_not_roles_and_goal(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d);state=enable_ws(ws,2)
            configure.apply_patch(ws,{"team":{"agents":{"skeptic":{"codex_model":"different-model","effort":"medium"}},
                                                    "execution":{"max_parallel_agent_workers":2}},
                                       "reading":{"codex":{"timeout_seconds":550}}})
            self.assertEqual(batch.load_state(ws)["campaign"],state["campaign"])
            with self.assertRaises(RuntimeError):
                configure.apply_patch(ws,{"team":{"agents":{"skeptic":{"brief":"改变角色审核职责"}}}})
            with self.assertRaises(RuntimeError):
                configure.apply_patch(ws,{"goal_text":"改变整个研究路线"})
            self.assertEqual(team.load(ws)["agents"]["skeptic"]["brief"],"Review literature, methods and authentic source evidence independently; prepare research or experiment designs only, never execute any tests or simulations.")

    def test_team_model_route_explicit_and_budget_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d);batch.init(ws)
            conf=team.load(ws)
            cfg=core.config_for(ws)
            with patch.object(core,"call_codex",return_value=('{}','gpt-6-astra')) as mock:
                answer,model=team.call_single(ws,conf,"method","codex","test","TASK1",1)
                self.assertEqual(mock.call_args.args[1]["type"],"method")
                subcfg=mock.call_args.args[0]["cfg"]["codex"]
                self.assertEqual(subcfg["models"]["method"],"gpt-6.1-sol")  # automatic TASK1 default is balanced
                self.assertEqual(subcfg["reasoning_effort"]["method"],"high")
            conf2=copy.deepcopy(conf);conf2["execution"]["max_total_model_calls_per_workspace"]=1
            with self.assertRaises(RuntimeError):
                team.call_single(ws,conf2,"method","codex","test","TASK2",1)
            self.assertEqual(team.calls_used(ws),1)

    def test_natural_language_prompt_compiler_is_explicitly_model_routed(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d);batch.init(ws)
            request="把候选每批改为10篇，核心60篇，主任务最多20个，启动前禁止模型调用。"
            compiled={"selection":{"screen_batch_size":10,"core_target":60},
                      "run":{"max_jobs_per_launch":20,"allow_model_calls":False}}
            with patch.object(core,"call_codex",return_value=(core.dump(compiled),"fake-model")) as mocked:
                patch1=configure.compile_prompt(ws,request,"codex","explicit-config-model")
                self.assertEqual(mocked.call_args.args[1]["type"],"__config_compiler")
                c=mocked.call_args.args[0]["cfg"]["codex"]
                self.assertEqual(c["models"]["__config_compiler"],"explicit-config-model")
            configure.apply_patch(ws,patch1,user_instruction=request)
            self.assertEqual(core.jread(ws/"selection_config.json")["screen_batch_size"],10)
            self.assertFalse(core.jread(ws/"run_config.json")["allow_model_calls"])

    def test_600_paper_resource_estimate_counts_real_specialist_jobs(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d);state=enable_ws(ws,3)
            estimate=batch.estimate(ws,state)
            self.assertEqual(estimate["screening_model_calls_estimate"],16)
            self.assertEqual(estimate["team_readers_per_S1"],3)
            self.assertEqual(estimate["team_readers_per_S2"],3)

if __name__=="__main__":
    unittest.main(verbosity=2)
