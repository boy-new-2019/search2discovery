"""Offline functional tests for 600+ screening, replacement and five-round core delegation.
All model decisions below are synthetic fixtures, not evidence of actual reading.
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import batch  # noqa: E402
import deepread as core  # noqa: E402

TEXT_REL = ("Streaming occupancy world representations are trained from multiple cameras. "
            "Our method learns temporal evidence memory for autonomous driving. "
            "Implementation and ablation support the proposed architecture. ")
TEXT_IRREL = ("Chemical fertilization affects soil acidity and the root biomass in controlled field plots. "
              "This agricultural experiment measures plant growth with irrigation and different fertilizers. "
              "The analysis reports experimental yields and confounding conditions. ")


def make_ws(ws, n=4, relevant=None, batch_size=2, target=2, minimum=1):
    batch.init(ws)
    # Legacy v2 regression tests synthesize a single screening answer per job.
    # Explicitly disable the new v3 independent team gate for this fixture.
    team_cfg=core.jread(ws/"team_config.json")
    team_cfg["enabled"]=False
    core.jwrite(ws/"team_config.json",team_cfg)
    cfg=batch.cfg_at(ws)
    cfg.update({"screen_batch_size":batch_size,"core_min":minimum,"core_target":target,"core_max":max(target,3),
                "min_supplemental_pdfs":0,"min_supplemental_qualified":0,"max_supplemental_pdfs":8,"max_discovery_waves":2})
    for t in cfg["coverage_themes"]:
        t["min_core"]=0
    core.jwrite(ws/"selection_config.json",cfg)
    for i in range(n):
        yes=(i< (relevant if relevant is not None else n))
        text=(TEXT_REL if yes else TEXT_IRREL)*2
        (ws/"input"/f"paper{i:04d}.md").write_text(text+f"Unique case {i}. ",encoding="utf-8")
    state=batch.ingest(ws)
    return state


def make_model_response(ws,state,job,relevant_files=None,overrides=None):
    excerpts=batch.make_screen_prompt(ws,state,job)[1]
    rows=[]
    for pid in job["group"]["paper_ids"]:
        row=next(x for x in state["papers"] if x["id"]==pid)
        is_rel= (row["file"] in relevant_files) if relevant_files is not None else ('paper0' in row["file"] or 'paper1' in row["file"])
        if overrides and row["file"] in overrides:
            is_rel=overrides[row["file"]]
        first=excerpts[pid][0]
        grade=5 if is_rel else 1
        rows.append({"paper_id":pid,"summary":f"{job['stage']} 分析涉及具体课题和方法 {row['file']}",
                     "verdict":"LIKELY_RELEVANT" if is_rel else "LIKELY_IRRELEVANT",
                     "theme":"Streaming/Temporal Memory" if is_rel else "Other",
                     "scores":{"topic":grade,"method":grade,"trajectory":grade,"evidence_quality":4},
                     "evidence":[{"page":first["page"],"quote":first["text"][:60]}],
                     "uncertainty":"none","reason":f"依据{job['stage']}正文摘录作出独立判断：{row['file']}"})
    return {"stage":job["stage"],"papers":rows}


def fill_screen(ws,state,relevant_files=None):
    calls=0
    while job:=batch.next_screen(ws,state):
        prompt, excerpts=batch.make_screen_prompt(ws,state,job)
        data=make_model_response(ws,state,job,relevant_files)
        cites=batch.verify_screen(ws,state,job,data,excerpts)
        batch.save_screen(ws,state,job,data,prompt,cites,engine="manual",model="TEST_FAKE",attempts=1)
        calls+=1
        if calls>1000:
            raise AssertionError("loop")
    return calls


class LargeBatchTests(unittest.TestCase):
    def test_600_papers_150_screen_batches_and_60_core(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d);state=make_ws(ws,n=600,relevant=120,batch_size=8,target=60,minimum=30)
            # Contract only established after ingest; changing policies mid-run must fail closed.
            cfg=batch.cfg_at(ws)
            cfg["keep_threshold"]=4.4
            core.jwrite(ws/"selection_config.json",cfg)
            with self.assertRaises(RuntimeError):
                batch.load_state(ws)
            cfg["keep_threshold"]=2.85
            core.jwrite(ws/"selection_config.json",cfg)
            # Strict 2 rounds on 600 candidates, only 150 total requests at 8 papers/request.
            files={f"paper{i:04d}.md" for i in range(120)}
            self.assertEqual(fill_screen(ws,state,files),150)
            s=batch.select_core(ws,state)
            self.assertEqual(s["counts"]["REJECT"],480)
            self.assertEqual(s["counts"]["CORE"],60)
            self.assertEqual(s["counts"]["RESERVE"],60)
            self.assertFalse(set(s["last_selected"]) & {x["paper_id"] for x in s["decisions"] if x["decision"]=="REJECT"})
            summary=batch.summary(ws,state)
            self.assertEqual(summary["S1_done"],75)
            self.assertEqual(summary["S2_done"],75)
            self.assertEqual(summary["status"],"SELECTED")

    def test_false_citation_and_wrong_paper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d);state=make_ws(ws)
            job=batch.next_screen(ws,state)
            prompt,excerpts=batch.make_screen_prompt(ws,state,job)
            data=make_model_response(ws,state,job)
            data["papers"][0]["evidence"][0]["quote"]="Paper discusses quantum black hole teleportation"
            with self.assertRaises(ValueError):
                batch.verify_screen(ws,state,job,data,excerpts)
            self.assertFalse(batch.done(ws,job["id"]))
            data=make_model_response(ws,state,job)
            data["papers"].reverse()
            with self.assertRaises(ValueError):
                batch.verify_screen(ws,state,job,data,excerpts)

    def test_new_sources_are_rescreened_without_losing_prior_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d);state=make_ws(ws,n=4)
            files={"paper0000.md","paper0001.md"}
            self.assertEqual(fill_screen(ws,state,files),4)
            initial_receipts=list((batch.root_dir(ws)/"receipts").glob("*.json"))
            self.assertEqual(len(initial_receipts),4)
            batch.select_core(ws,state)
            (ws/"input"/"supplemental").mkdir()
            (ws/"input"/"supplemental"/"new01.md").write_text(TEXT_REL*3,encoding="utf-8")
            state=batch.ingest(ws)
            self.assertEqual(len(state["groups"]),3)
            self.assertEqual(batch.next_screen(ws,state)["id"],"S1_B00003")
            self.assertEqual(fill_screen(ws,state,files|{"supplemental/new01.md"}),2)
            self.assertEqual(len(list((batch.root_dir(ws)/"receipts").glob("*.json"))),6)
            self.assertTrue(all(batch.done(ws,p.stem) for p in initial_receipts))
            revised=batch.select_core(ws,state)
            self.assertEqual(revised["counts"]["REJECT"],2)
            self.assertEqual(revised["counts"]["RESERVE"],1)
            self.assertEqual(revised["counts"]["CORE"],2)

    def test_seal_core_never_includes_screened_out_papers(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d);state=make_ws(ws,n=6,relevant=3)
            files={"paper0000.md","paper0001.md","paper0002.md"}
            fill_screen(ws,state,files)
            s=batch.select_core(ws,state)
            with self.assertRaises(RuntimeError):  # policy change must not reuse prior screening
                cfg=batch.cfg_at(ws);cfg["min_supplemental_pdfs"]=1
                core.jwrite(ws/"selection_config.json",cfg)
                # policy edit requires a new campaign; reload blocks before seal
                batch.load_state(ws)
            cfg["min_supplemental_pdfs"]=0
            core.jwrite(ws/"selection_config.json",cfg)
            sub=batch.seal(ws,state)
            ctx=core.env(sub)
            self.assertEqual(len(ctx["papers"]),2)
            sha={p["sha256"] for p in ctx["papers"]}
            self.assertEqual(sha,{p["sha256"] for p in state["papers"] if p["id"] in s["last_selected"]})
            self.assertEqual(ctx["cfg"]["rounds"],5)
            self.assertEqual(len(batch.summary(ws,state)["frozen"]["paper_ids"]),2)
            with self.assertRaises(RuntimeError):
                (ws/"input"/"new_after_seal.md").write_text(TEXT_REL*2,encoding="utf-8")
                batch.ingest(ws)

    def test_openalex_proposals_dedup_and_no_hidden_download(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d);state=make_ws(ws)
            fill_screen(ws,state,{"paper0000.md","paper0001.md"})
            batch.select_core(ws,state)
            result=[{"id":"https://openalex.org/W123", "display_name":"A New Streaming Gaussian Memory Model",
                     "doi":"https://doi.org/10.1000/abc", "publication_year":2026,
                     "best_oa_location":{"pdf_url":"https://arxiv.org/pdf/9999.99999"}}]
            with patch.object(batch,"search_openalex",return_value=result) as finder:
                new=batch.discover(ws,state,download=False)
            self.assertEqual(len(new["proposals"]),1)
            self.assertEqual(len(new["downloads"]),0)
            self.assertEqual(len(new["papers"]),4)
            self.assertTrue(finder.called)
            self.assertEqual(new["proposals"][0]["status"],"PROPOSED")
            self.assertFalse(batch.safe_pdf_url("http://localhost/private"))
            self.assertFalse(batch.safe_pdf_url("https://127.0.0.1/private"))

    def test_modified_original_paper_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d);state=make_ws(ws)
            (ws/"input"/"paper0000.md").write_text("changed original",encoding="utf-8")
            with self.assertRaises(RuntimeError):
                batch.verify_sources(ws,state)
            with self.assertRaises(RuntimeError):
                batch.ingest(ws)

    def test_manual_screen_rejects_copying_round_one(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d);state=make_ws(ws,n=2,batch_size=2)
            job=batch.next_screen(ws,state)
            prompt,ext=batch.make_screen_prompt(ws,state,job)
            data=make_model_response(ws,state,job)
            batch.save_screen(ws,state,job,data,prompt,batch.verify_screen(ws,state,job,data,ext),engine="manual",model="TEST",attempts=1)
            job=batch.next_screen(ws,state)
            self.assertEqual(job["stage"],"S2")
            second=make_model_response(ws,state,job)
            for i,x in enumerate(second["papers"]):
                x["summary"]=data["papers"][i]["summary"]
                x["reason"]=data["papers"][i]["reason"]
            with self.assertRaises(ValueError):
                batch.verify_screen(ws,state,job,second,batch.make_screen_prompt(ws,state,job)[1])


if __name__=="__main__":
    unittest.main(verbosity=2)


class AutomaticWorkflowTests(unittest.TestCase):
    """Mocked model/source integration exercises the real coordination code."""

    def test_single_auto_invocation_replenishes_and_freezes_core(self):
        import json
        import re
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d)
            state=make_ws(ws,n=4,relevant=2,target=3,minimum=2,batch_size=2)
            cfg=batch.cfg_at(ws)
            cfg.update({"min_supplemental_pdfs":1,"min_supplemental_qualified":1,
                        "max_download_per_wave":2,"max_supplemental_pdfs":2,
                        "max_proposals_per_wave":3,"parallel_screen_workers":2})
            # A changed policy must start a new campaign: reset only fixture's unused state.
            core.jwrite(ws/"selection_config.json",cfg)
            (batch.root_dir(ws)/"state.json").unlink()
            state=batch.ingest(ws)
            invoked=[]
            def fake_codex(ctx,job,prompt):
                stage="S1" if "stage S1" in prompt else "S2"
                raw=prompt.split("<UNTRUSTED_PARTIAL_PAPER_EXCERPTS>\n",1)[1].split("\n</UNTRUSTED_PARTIAL_PAPER_EXCERPTS>",1)[0]
                materials=json.loads(raw)
                records=[]
                for m in materials:
                    excerpt=m["excerpts"][0]
                    whole=" ".join(q["text"] for q in m["excerpts"])
                    good="Streaming occupancy" in whole
                    grade=5 if good else 1
                    records.append({"paper_id":m["paper_id"], "summary":stage+" independent excerpt analysis " + m["paper_id"],
                                    "reason":"Checked original excerpt during "+stage+" for "+m["paper_id"],
                                    "theme":"Streaming/Temporal Memory" if good else "Other",
                                    "verdict":"LIKELY_RELEVANT" if good else "LIKELY_IRRELEVANT",
                                    "scores":{"topic":grade,"method":grade,"trajectory":grade,"evidence_quality":4},
                                    "uncertainty":"none","evidence":[{"page":excerpt["page"],"quote":excerpt["text"][:50]}]})
                invoked.append(stage)
                return json.dumps({"stage":stage,"papers":records},ensure_ascii=False),"FAKE_CODEX"
            def fake_oa(query,c):
                return [{"id":"https://openalex.org/W00001","display_name":"New temporal Gaussian work",
                         "doi":"https://doi.org/10.5555/gnew","best_oa_location":{"pdf_url":"https://arxiv.org/pdf/0000.0000"},
                         "publication_year":2026}]
            def fake_download(url,target,max_mb):
                import fitz
                target.parent.mkdir(parents=True,exist_ok=True)
                doc=fitz.open()
                for _ in range(3):
                    page=doc.new_page()
                    result=page.insert_textbox(fitz.Rect(40,40,540,750),(TEXT_REL*5),fontsize=11)
                    if result<0:
                        raise RuntimeError("Synthetic pdf was too long")
                doc.save(str(target));doc.close()
            touched=[]
            with patch.object(core,"call_codex",side_effect=fake_codex), \
                 patch.object(batch,"search_openalex",side_effect=fake_oa), \
                 patch.object(batch,"pdf_download",side_effect=fake_download), \
                 patch.object(core,"run_auto",side_effect=lambda c,e,m: touched.append((c["paper_ids"],e,m))):
                rc=batch.cli(["auto","--workspace",str(ws),"--engine","codex","--online","--download"])
            self.assertEqual(rc,0)
            state=batch.load_state(ws)
            self.assertEqual(len(state["papers"]),5)
            self.assertEqual(len(state["groups"]),3)
            self.assertTrue(all(batch.done(ws,batch.stage_jid(st,g)) for st in batch.STAGES for g in state["groups"]))
            self.assertEqual(state["selection"]["counts"]["CORE"],3)
            self.assertEqual(state["selection"]["counts"]["REJECT"],2)
            self.assertEqual(batch.supplementary_quality(state)["qualified"],1)
            self.assertIsNotNone(state["frozen"])
            self.assertEqual(len(touched),1)
            self.assertEqual(touched[0][1],"codex")
            self.assertEqual(len(touched[0][0]),3)
            self.assertEqual(len(invoked),6)  # Two screening stages * three groups
