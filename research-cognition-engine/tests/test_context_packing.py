import copy,json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
import context_packing,engine,store


def renderer():
    def render(context,role):return role+store.dump(context)
    render.roles=["short","longer_role"]
    return render


def claim(number,source="A",kind="METHOD",length=180):
    return {"claim_id":str(number),"source_id":source,"work_id":source,"claim_kind":kind,
            "text":"Evidence "+"x"*length,"quote":"Exact quote.\nSecond line.","page":2}


class PackingTests(unittest.TestCase):
    def test_index_lookup_allowed_without_scientific_execution(self):
        prompt=engine._instructions("MECHANISM","rce_method_sol")
        self.assertIn("filtered index lookup",prompt)
        self.assertIn("Do not execute scientific models",prompt)
        self.assertNotIn("Do not run code,",prompt)

    def test_balances_sources_and_kinds_preserving_records(self):
        rows=[claim(i) for i in range(20)]+[claim(20,"A","LIMITATION"),claim(21,"B")]
        original=copy.deepcopy(rows)
        ordered=list(context_packing.balanced(rows))
        self.assertEqual([x["source_id"] for x in ordered[:2]],["A","B"])
        self.assertEqual({x["claim_kind"] for x in ordered[:3]},{"METHOD","LIMITATION"})
        self.assertEqual(rows,original)
        self.assertEqual({r["claim_id"] for r in ordered},{r["claim_id"] for r in rows})

    def test_actual_render_cap_whole_quotes_and_pinned_evidence(self):
        rows=[claim(i) for i in range(80)]+[claim(80,"B")]
        context={"claims":rows,"hypotheses":[{"linked_claims":"[\"79\"]"}],
                 "contradictions":[{"left_id":"78","right_id":"80"}],
                 "available_fulltext_index":{"sha256":"verified-index"}}
        original=copy.deepcopy(context);render=renderer()
        packed=context_packing.fit(context,5000,render)
        self.assertLessEqual(max(len(render(packed,r)) for r in render.roles),5000)
        self.assertTrue({"78","79","80"}<={r["claim_id"] for r in packed["claims"]})
        self.assertEqual(context,original)
        for row in packed["claims"]:self.assertEqual(row,next(r for r in rows if r["claim_id"]==row["claim_id"]))
        selection=packed["evidence_selection"]
        self.assertEqual(selection["available_claims"],selection["included_claims"]+selection["omitted_claims"])
        self.assertGreater(selection["omitted_claims"],0)

    def test_required_oversize_and_missing_fail_closed(self):
        context={"claims":[claim(1,length=9000)],"hypotheses":[{"linked_claims":["1"]}]}
        with self.assertRaisesRegex(ValueError,"Required stage evidence"):
            context_packing.fit(context,3000,renderer())
        context["hypotheses"][0]["linked_claims"]=["absent"]
        with self.assertRaisesRegex(ValueError,"missing"):
            context_packing.fit(context,3000,renderer())

    def test_index_is_complete_content_addressed_and_tamper_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=pathlib.Path(tmp);rows=[claim(i) for i in range(200)]
            sources=[{"source_id":"S","file_sha":"sourcehash","file_path":"source.pdf"}]
            result=context_packing.archive(ws,sources,rows);path=pathlib.Path(result["path"])
            self.assertEqual(store.hashbytes(path.read_bytes()),result["sha256"])
            self.assertEqual(store.read(path)["claims"],rows)
            self.assertEqual(context_packing.archive(ws,sources,rows),result)
            path.write_text("tampered",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"immutable"):
                context_packing.archive(ws,sources,rows)

    def test_final_retains_actual_reviews_and_plans_not_blinded_novelty(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=pathlib.Path(tmp)
            with store.connect(ws) as c:
                c.execute("INSERT INTO works(work_id,title,category,record_sha) VALUES('W','Paper','CORE','hash')")
                c.execute("INSERT INTO sources VALUES('S','W','paper.pdf','hash',3,'pages.json','now')")
                c.execute("INSERT INTO claims VALUES('C','S','W','Evidence','METHOD',1,'Quote','reader','ANCHOR_CHECKED','now')")
                c.execute("INSERT INTO questions VALUES('Q','Question',1,1,'field','OPEN','now')")
                c.execute("INSERT INTO hypotheses VALUES('H','Q','Statement','Mechanism','Prediction','Falsifier','Assumptions','[\"C\"]','[]','Test','OPEN','OPEN','now')")
                for role in ('independent1','independent2'):
                    c.execute("INSERT INTO assessments VALUES('H',?,'REJECT','[]','Substantive objection',?,'now')",(role,role))
                c.execute("INSERT INTO experiments VALUES('P','H','Concrete plan','Controls','Metrics','Stop','Budget','PLANNED_NOT_EXECUTED','now')")
            cfg={"budget":{"max_papers_in_task_context":8}}
            with patch.object(engine,"get_state",return_value={"cycles":[{}]}):
                final=engine._context(ws,"FINAL",cfg)
                novelty=engine._context(ws,"NOVELTY",cfg)
            self.assertEqual(len(final["independent_novelty_assessments"]),2)
            self.assertEqual(final["committed_experiment_plans"][0]["plan"],"Concrete plan")
            self.assertNotIn("independent_novelty_assessments",novelty)
            self.assertNotIn("committed_experiment_plans",novelty)

if __name__=="__main__":unittest.main()
