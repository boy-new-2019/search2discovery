"""Offline end-to-end state machine tests. Synthetic paper fixtures are not real readings."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MOD = Path(__file__).resolve().parents[1] / "scripts" / "deepread.py"
spec = importlib.util.spec_from_file_location("deepread", MOD)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixture(ws: Path) -> dict:
    mod.init(ws)
    text1 = ("Our paper addresses streaming 3D occupancy under incomplete camera observations. "
             "The method uses a fixed memory bank and temporal updates with explicit consistency checks. "
             "Training follows a clearly stated protocol and uses validation sequences separated from training. "
             "The experiments report numerical metrics, ablation settings, and several recognized limitations. "
             "The appendix describes implementation assumptions and difficult cases. ")
    text2 = ("This paper studies sparse Gaussian occupancy perception across several temporal observations. "
             "The authors employ sparse state and dynamic refinement of a limited Gaussian set. "
             "The method section explains supervision, loss functions, and computation cost. "
             "Experiments compare models using a shared evaluation metric and show a stress test. "
             "Limitations include occlusion handling and evaluation protocol ambiguity. ")
    (ws / "input" / "A_paper.md").write_text(text1, encoding="utf-8")
    (ws / "input" / "B_paper.md").write_text(text2, encoding="utf-8")
    mod.ingest(ws)
    return mod.env(ws)


def evidence(ctx, pid, offset=5):
    page = mod.paper_pages(ctx, pid)[0]
    return {"page": 1, "quote": page[offset:offset+55]}


def obs(ctx, pid, r=1, offset=5):
    return {"claim": f"第{r}轮抽取的原文论点及约束 {offset}", "category": "method", "status": "reported",
            "confidence": "high", "evidence": [evidence(ctx, pid, offset)]}


def response(ctx, job, *, veto=False):
    typ, r, pid = job["type"], job.get("round"), job.get("paper_id")
    if typ == "leaf":
        return {"round": r, "paper_id": pid, "chunk_id": job["chunk_id"],
                "brief": f"R{r} extract original page", "observations": [obs(ctx,pid,r,5+r)],
                "open_questions": [], "visual_flags": [], "empty_reason": ""}
    if typ == "merge":
        return {"round": r, "paper_id": pid, "overview": f"R{r} thematic overview",
                "key_points": [obs(ctx,pid,r,5+r), obs(ctx,pid,r,45+r)], "method_details": ["Method structure"],
                "weaknesses": ["Unproven generalization"], "open_questions": ["Check visual plots"], "visual_flags": []}
    if typ in ("group", "master"):
        refs = [{"paper_id": p, **evidence(ctx,p,11+r)} for p in job["paper_ids"]]
        return {"round": r, "group_id": job["group_id"], "paper_ids":job["paper_ids"],
                "overview": f"R{r} corpus group comparison", "comparisons": [
                    {"claim":"The two papers offer different methods", "support":refs, "counter":[], "confidence":"high"}],
                "gaps":["Results may not be directly comparable"], "priorities":["Review formulas"]}
    if typ == "final":
        return {"overview":f"Synthetic aggregate rev {job['revision']}",
                "research_map":[{"theme":"Temporal memory", "papers":ctx["paper_ids"],"summary":"Paper themes"}],
                "ranked_reading":[{"paper_id":p,"reason":"Matches goal","priority":"A"} for p in ctx["paper_ids"]],
                "actionable_lessons":[{"claim":"Methods need reproducible comparisons", "support":[
                    {"paper_id":p, **evidence(ctx,p,20)} for p in ctx["paper_ids"]],
                    "caveat":"A plausible research direction, not a proven contribution"}],
                "unresolved":["How robust are results?"],"limitations":["Figures were not visually verified"]}
    if typ == "audit":
        return {"verdict":"VETO" if veto else "PASS", "checked_papers":ctx["paper_ids"],
                "coverage_confidence":"high", "issues": ([{"severity":"major", "claim":"unverified comparison",
                   "reason":"manual synthetic audit requests another pass", "support":[],
                   "repair":"Reconsider the original experiment protocol"}] if veto else [])}
    raise AssertionError(typ)


def fill(ctx, veto_revisions=()):
    count = 0
    while job := mod.next_job(ctx):
        content = response(ctx, job, veto=job["type"]=="audit" and job["revision"] in veto_revisions)
        checked = mod.validate(ctx, job, content)
        mod.create_prompt(ctx, job)
        mod.save_answer(ctx, job, content, checked, engine="manual", model="TEST_FIXTURE", attempts=1)
        count += 1
        if count > 100:
            raise AssertionError("Unexpected infinite loop")
    return count


class PaperFlowTests(unittest.TestCase):
    def test_minimum_five_and_32_jobs(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            ctx = fixture(ws)
            self.assertEqual(ctx["cfg"]["rounds"],5)
            total = fill(ctx)
            self.assertEqual(total, 32)
            state = mod.run_status(ctx)
            self.assertEqual(state["status"], "COMPLETE")
            self.assertTrue(all(x["all_papers_read"] and x["master_completed"] for x in state["per_round"]))
            self.assertGreater(state["verified_source_anchors"], 0)
            mod.produce_report(ctx)
            self.assertTrue((ctx["run"] / "reading_report.md").exists())
            self.assertTrue((ctx["run"] / "cross_paper_matrix.csv").exists())
            self.assertTrue((ctx["run"] / "audit_trail.json").exists())
            self.assertEqual(len(list((ctx["run"] / "paper_notes").glob("*.md"))), 2)

    def test_hallucinated_citation_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = fixture(Path(d))
            job = mod.next_job(ctx)
            response1 = response(ctx, job)
            response1["observations"][0]["evidence"][0]["quote"] = "A made-up unsupported numerical claim."
            with self.assertRaises(ValueError):
                mod.validate(ctx, job, response1)
            self.assertFalse(mod.completed(ctx, job["id"]))
            self.assertEqual(mod.next_job(ctx)["id"], job["id"])

    def test_audit_veto_not_false_pass(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            mod.init(ws)
            cfg = mod.config_for(ws)
            cfg["max_audit_repairs"] = 1
            mod.jwrite(ws / "reading_config.json", cfg)
            ctx = fixture(ws)
            self.assertEqual(fill(ctx, veto_revisions=(0,1)), 34)
            state = mod.run_status(ctx)
            self.assertEqual(state["status"], "AUDIT_VETO")
            mod.produce_report(ctx)
            self.assertFalse((ctx["run"] / "reading_report.md").exists())
            self.assertTrue((ctx["run"] / "INCOMPLETE_OR_VETO.md").exists())

    def test_bad_audit_pass_with_major_issue_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = fixture(Path(d))
            while (job := mod.next_job(ctx)) and job["type"] != "audit":
                raw = response(ctx,job)
                mod.save_answer(ctx,job,raw,mod.validate(ctx,job,raw),engine="manual",model="TEST",attempts=1)
            test_response = response(ctx, job, veto=True)
            test_response["verdict"] = "PASS"
            with self.assertRaises(ValueError):
                mod.validate(ctx, job, test_response)

    def test_ingest_detects_duplicate_and_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            mod.init(ws)
            (ws / "input" / "A.md").write_text("This is an original real paragraph. "*8, encoding="utf-8")
            (ws / "input" / "B.md").write_text("This is an original real paragraph. "*8, encoding="utf-8")
            (ws / "input" / "C.txt").write_text("short", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                mod.ingest(ws)
            mf = mod.jread(ws / "output" / "manifest.json")
            self.assertEqual(mf["duplicates"],1)
            self.assertEqual(mf["blocked"],1)

    def test_edited_source_requires_reingest(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            ctx = fixture(ws)
            (ws / "input" / "A_paper.md").write_text("Altered paper content "*30,encoding="utf-8")
            with self.assertRaises(RuntimeError):
                mod.env(ws)

    def test_reused_answer_does_not_count_as_new_reading(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = fixture(Path(d))
            # Complete R1 and reach R2 first leaf.
            while (job := mod.next_job(ctx))["round"] == 1:
                data = response(ctx,job)
                mod.save_answer(ctx,job,data,mod.validate(ctx,job,data),engine="manual",model="TEST",attempts=1)
            self.assertEqual(job["round"],2)
            prev = mod.answer(ctx,f"R01_{job['paper_id']}_{job['chunk_id']}")
            repeated = dict(prev)
            repeated["round"] = 2
            with self.assertRaises(ValueError):
                mod.validate(ctx,job,repeated)

    def test_codex_subprocess_routes_explicit_model_in_isolated_cwd(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            ctx = fixture(ws)
            fake_cli = ws / "fake-codex"
            fake_cli.write_text('''#!/usr/bin/env python3
import os,sys,json
args=sys.argv[1:]
where=args[args.index('--output-last-message')+1]
with open(where,'w') as f: f.write(json.dumps({'ok':1, 'cwd':os.getcwd(), 'args':args}))
''', encoding="utf-8")
            fake_cli.chmod(0o755)
            cfg = ctx["cfg"]
            cfg["codex"]["binary"] = str(fake_cli)
            mod.jwrite(ws / "reading_config.json",cfg)
            # Existing in-memory context has config snapshot, update it for mock invocation.
            ctx["cfg"] = cfg
            job = mod.next_job(ctx)
            raw, model = mod.call_codex(ctx,job,job["prompt"])
            record = json.loads(raw)
            self.assertEqual(model, "gpt-6-luna")
            self.assertIn("--model", record["args"])
            self.assertIn("--sandbox", record["args"])
            self.assertIn("read-only", record["args"])
            self.assertNotEqual(Path(record["cwd"]).resolve(), ws.resolve())
            self.assertEqual(record["args"][record["args"].index("--model")+1], "gpt-6-luna")

    def test_pdf_ingest_and_render(self):
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF not installed")
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            mod.init(ws)
            doc = fitz.open()
            page = doc.new_page()
            content = "Figure 1 shows the occupancy baseline. "*27
            page.insert_textbox(fitz.Rect(35,35,565,750), content, fontsize=12)
            doc.save(str(ws / "input" / "figure_paper.pdf"))
            doc.close()
            mod.ingest(ws)
            ctx = mod.env(ws)
            pid = ctx["paper_ids"][0]
            candidates = mod.visual_candidates(ctx,pid)
            self.assertIn(1,candidates)
            mod.render_pdf(ctx,pid,[1],100)
            self.assertTrue((ctx["run"] / "visual_pages" / pid / "p0001.png").exists())
            self.assertEqual(mod.visual_summary(ctx)[0]["status"],"VISUAL_PENDING")
            mod.record_visual(ctx,pid,[1], "I inspected the real visual plot and checked axes manually.", "unit tester")
            self.assertEqual(mod.visual_summary(ctx)[0]["status"],"VISUAL_REVIEW_RECORDED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
