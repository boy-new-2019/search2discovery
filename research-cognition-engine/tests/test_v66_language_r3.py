"""v6.6 English-internal and paper-only R3 safety regression tests.

The synthetic source quotations in multilingual-language fixtures are research DATA,
not executable Skill instructions. No model call or experiment is performed here.
"""
from __future__ import annotations
import inspect
import pathlib
import re
import sys
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'batch-paper-deepread-desktop/scripts'))
sys.path.insert(0,str(ROOT/'research-cognition-engine/scripts'))
import deepread
import engine
import round_intelligence
import topic_to_plan

CJK = re.compile(r'[\u3400-\u9fff]')

class EnglishInternalPolicyTests(unittest.TestCase):
    def test_all_three_skill_instructions_are_english(self):
        for name in ('paper-discovery-preflight','batch-paper-deepread-desktop','research-cognition-engine'):
            instruction=(ROOT/name/'SKILL.md').read_text(encoding='utf8')
            self.assertFalse(CJK.search(instruction),name)
            self.assertIn('English',instruction)

    def test_all_27_native_agent_instructions_english_and_nonexecuting(self):
        files=list((ROOT/'.codex/agents').glob('*.toml'))
        self.assertEqual(len(files),27)
        for file in files:
            record=tomllib.loads(file.read_text('utf8'))
            policy=record['developer_instructions']
            self.assertFalse(CJK.search(policy),file.name)
            self.assertIn('English',policy)
            self.assertIn('experiments',policy)
            self.assertIn('untrusted data',policy)

    def test_all_shipped_executable_prompts_and_docs_are_english(self):
        # Research data inside the tests intentionally include original-language quotes.
        # Executable Skill prompts, scripts, templates, configs and instructions must not.
        allow_suffixes={'.py','.md','.toml','.json','.yaml','.yml','.txt'}
        for root_name in ('batch-paper-deepread-desktop','paper-discovery-preflight',
                          'research-cognition-engine','.codex'):
            for path in (ROOT/root_name).rglob('*'):
                if not path.is_file() or path.suffix not in allow_suffixes or 'tests' in path.parts:
                    continue
                self.assertFalse(CJK.search(path.read_text('utf8')),str(path.relative_to(ROOT)))

    def test_visual_review_flags_keep_source_page_and_reason(self):
        source=inspect.getsource(round_intelligence._round_items)
        self.assertIn("flag.get('page'",source)
        self.assertIn("flag.get('reason'",source)
        self.assertIn('visual review pending',source)
        self.assertNotIn("issues.append('Source state and independent reviewer provenance",source)

    def test_r3_desk_scenario_must_be_inferred(self):
        ok={'claim':'Under stale observations the historical representation could lag behind the scene.',
            'category':'desk_scenario','status':'inferred'}
        deepread.validate_r3_paper_only([ok])
        with self.assertRaisesRegex(ValueError,'inferred'):
            deepread.validate_r3_paper_only([{**ok,'status':'reported'}])

    def test_r3_desk_scenario_must_not_contain_numerical_claims(self):
        example={'claim':'The simulated memory update improved mIoU by 7.6%.',
                 'category':'hypothetical','status':'inferred'}
        with self.assertRaisesRegex(ValueError,'numerical'):
            deepread.validate_r3_paper_only([example])

    def test_paper_reported_metrics_are_not_prohibited(self):
        actual={'claim':'The paper reports mIoU of 27.4% on a stated benchmark.',
                'category':'experiment','status':'reported'}
        deepread.validate_r3_paper_only([actual])

    def test_original_fulltext_prompt_and_cognition_instruction_are_english(self):
        self.assertNotIn('review detail',inspect.getsource(deepread.make_prompt))
        self.assertNotIn('review detail',inspect.getsource(engine._instructions))
        self.assertIn('PLANNED_NOT_EXECUTED',engine._instructions('EXPERIMENT','rce_experiment_sol'))

    def test_internal_report_renders_english_preserving_source_quote(self):
        report={
            'kind':'SCREEN','label':'S1','key':'SCREEN_sample_S1',
            'summary':'Three real candidate papers screened.','stats':{'papers':3},
            'items':[{'paper_id':'P001','decision':'BORDERLINE','reason':'Relevant memory update','uncertainty':'none'}],
            'citations':[{'paper_id':'P001','page':1,'quote':'中文原文摘录应保持不变'}],
            'citation_total':1,'issues':[],'source_files':[],'scientific_limit':'Screening is not fulltext evidence.'
        }
        text=round_intelligence._render(report)
        self.assertIn('Round summary',text)
        self.assertIn('中文原文摘录应保持不变',text)
        self.assertNotIn('review detail',text)

    def test_final_topic_report_template_clean(self):
        code=inspect.getsource(topic_to_plan.finalize)
        self.assertIn('PLANNED_NOT_EXECUTED',code)
        self.assertIn('DESIGN ONLY',code)
        self.assertIn('Bibliographic records',code)
        self.assertIn('Nearest identified prior art',code)

if __name__=='__main__':
    unittest.main()
