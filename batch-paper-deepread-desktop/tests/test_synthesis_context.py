"""Offline fixtures check prompt limits/provenance, never scientific correctness."""
from __future__ import annotations
import copy, hashlib, importlib.util, json, tempfile, unittest
from pathlib import Path
from unittest import mock

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/deepread.py'
spec=importlib.util.spec_from_file_location('bounded_reader_fixture',SCRIPT)
core=importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class BoundedOriginalSynthesis(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='bounded-reader-')
  self.root=Path(self.temp.name)
  self.ctx={'run':self.root/'run','ws':self.root,'goal':'Frozen goal; no experiments.','run_id':'fixture','papers':[]}
 def tearDown(self):self.temp.cleanup()
 def rows(self,n=3):
  return [{'round':4,'paper_id':f'P{i}','overview':f'Source {i} fixture, not a research review.',
           'key_points':[{'claim':f'P{i} observation {j}: '+('fixture evidence '*15),
                          'evidence':[{'page':1,'quote':f'Exact complete source fixture {i}-{j}'}],
                          'status':'reported'} for j in range(20)],
           'weaknesses':[f'P{i} complete counter-evidence '+('qualification '*14) for _ in range(4)],
           'visual_flags':[{'page':1,'reason':'Unviewed fixture, never visually verified.'}]} for i in range(n)]
 def prompt(self,rows,tag='VERIFIED_PAPER_OR_GROUP_NOTES',tail='Only JSON.'):
  return 'Frozen source and safety instructions.\n<'+tag+'>\n'+core.dump(rows)+'\n</'+tag+'>\n'+tail
 def pack(self,rows,cap=8000,typ='group',tag='VERIFIED_PAPER_OR_GROUP_NOTES',tail='Only JSON.'):
  return core._bounded_synthesis_prompt(self.ctx,{'id':'FIXTURE','type':typ},self.prompt(rows,tag,tail),cap)
 def unpack(self,text,tag='VERIFIED_PAPER_OR_GROUP_NOTES'):
  return json.loads(text.split('<'+tag+'>\n',1)[1].split('\n</'+tag+'>',1)[0])
 def test_short_prompts_are_byte_identical_and_create_no_archive(self):
  raw='Unchanged original prompt\r\nwith no context parsing.'
  for typ in ('leaf','merge','group','master','final','audit'):
   self.assertEqual(core._bounded_synthesis_prompt(self.ctx,{'type':typ},raw,100),raw)
  self.assertFalse(self.ctx['run'].exists())
 def test_all_evidence_is_indexed_and_inline_records_are_whole_and_balanced(self):
  rows=self.rows();before=copy.deepcopy(rows);text=self.pack(rows);packed=self.unpack(text)
  self.assertLessEqual(len(text),8000)
  selection=packed['evidence_selection'];index=selection['complete_index'];raw=core.filesystem_path(Path(index['path'])).read_bytes()
  self.assertEqual(hashlib.sha256(raw).hexdigest(),index['sha256'])
  self.assertEqual(json.loads(raw)['records'],rows)
  self.assertEqual(rows,before)
  self.assertGreater(selection['indexed_only_list_items'],0)
  self.assertEqual(selection['included_list_items']+selection['indexed_only_list_items'],selection['available_list_items'])
  for i,row in enumerate(packed['records']):
   self.assertEqual(row['paper_id'],rows[i]['paper_id'])
   self.assertEqual(row['key_points'][0],rows[i]['key_points'][0])
   self.assertTrue(row['weaknesses'])
   self.assertTrue(row['visual_flags'])
   for key,positions in selection['source_field_indices'][i].items():
    self.assertEqual(row[key],[rows[i][key][j] for j in positions])
 def test_repeat_is_identical_and_tampered_index_fails_closed(self):
  rows=self.rows();first=self.pack(rows);self.assertEqual(first,self.pack(rows))
  index=Path(self.unpack(first)['evidence_selection']['complete_index']['path'])
  core.filesystem_path(index).write_bytes(b'changed original context')
  with self.assertRaisesRegex(ValueError,'Changed immutable'):self.pack(rows)
  self.assertEqual(core.filesystem_path(index).read_bytes(),b'changed original context')
 def test_original_instructions_are_not_truncated_to_make_room(self):
  with self.assertRaisesRegex(ValueError,'instructions exceed'):
   core._bounded_synthesis_prompt(self.ctx,{'id':'FIXTURE','type':'group'},self.prompt(self.rows()),100)
 def test_required_primary_evidence_must_fit_without_raising_cap(self):
  rows=self.rows(1);rows[0]['key_points'][0]['claim']='A required source record '+('z'*9000)
  with self.assertRaisesRegex(ValueError,'Required source-row evidence'):
   self.pack(rows,cap=5000)
 def test_final_keeps_each_round_and_prior_independent_veto_verbatim(self):
  rows=[{'round':i,'group_id':'ALL','paper_ids':['P0','P1'],'overview':f'Round {i}',
         'comparisons':[{'claim':f'Round{i} claim{j} '+('fixture '*40),
                         'support':[{'paper_id':'P0','page':1,'quote':'Complete source quotation'}],
                         'counter':[],'confidence':'low'} for j in range(20)],
         'gaps':['Unresolved source qualification'],'priorities':['Verify original sources']} for i in range(1,6)]
  tail='PRIOR DRAFT FOR CORRECTION: whole draft.\nINDEPENDENT VETO: critical source issue retained verbatim.\nOnly JSON.'
  text=self.pack(rows,cap=10000,typ='final',tag='ALL_ROUND_MASTERS',tail=tail)
  self.assertTrue(text.endswith(tail));self.assertLessEqual(len(text),10000)
  for i,row in enumerate(self.unpack(text,'ALL_ROUND_MASTERS')['records']):
   self.assertEqual(row['round'],i+1);self.assertEqual(row['paper_ids'],['P0','P1'])
   self.assertEqual(row['comparisons'][0],rows[i]['comparisons'][0])
 def test_oversized_leaf_and_audit_gates_are_not_weakened(self):
  raw='x'*(core.MAX_PROMPT_CHARS+1)
  for typ in ('leaf','audit'):
   with mock.patch.object(core,'_unpacked_prompt',return_value=raw):
    with self.assertRaises(RuntimeError):core.generate_job(self.ctx,{'id':'FIXTURE','type':typ})
  self.assertFalse(self.ctx['run'].exists())

if __name__=='__main__':unittest.main()
