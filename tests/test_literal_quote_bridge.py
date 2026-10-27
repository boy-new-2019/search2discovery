import pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research-cognition-engine/scripts'))
import v44_original_adapter as adapter
class LiteralQuoteBridge(unittest.TestCase):
 def test_pdf_line_wrap_compatibility_and_soft_hyphen_are_exactly_recovered(self):
  page="Header. We deﬁne the measure\nment-update interval with of\u00adfline data. End."
  quote="We define the measurement-update interval with offline data."
  literal=adapter._literal_source_quote(page,quote)
  self.assertIn(literal,page)
  self.assertEqual(adapter.original.norm(literal),adapter.original.norm(quote))
  self.assertNotEqual(literal,quote)
 def test_existing_literal_is_unchanged(self):
  quote="The shared state is recurrent."
  self.assertEqual(adapter._literal_source_quote(quote,quote),quote)
 def test_invented_quotation_or_wrong_page_fails_closed(self):
  with self.assertRaises(adapter.EvidenceBridgeError):
   adapter._literal_source_quote("The shared state is recurrent.","The shared state is feedforward.")
 def test_literal_span_still_obeys_memory_length_bound(self):
  with self.assertRaises(adapter.EvidenceBridgeError):
   adapter._literal_source_quote("a "+" ".join("b"*200)+" end", "a"+"b"*200+"end")
 def test_unrelated_composing_math_marks_do_not_block_line_wrapped_quote(self):
  page="Header a\u0303. This observed signal is unavailable in the native-\ncomparison branch. End x\u0302."
  quote="This observed signal is unavailable in the native-comparison branch."
  literal=adapter._literal_source_quote(page,quote)
  self.assertIn(literal,page)
  self.assertEqual(adapter.original.norm(literal),adapter.original.norm(quote))
 def test_composed_quote_maps_to_decomposed_and_reordered_original_span(self):
  for source,quote in [("Cafe\u0301 evidence\nremains recurrent.","Café evidenceremains recurrent."),
                       ("a\u0315\u0300 evidence\nremains recurrent.","à\u0315 evidenceremains recurrent."),
                       ("\u1100\u1161 evidence\nremains recurrent.","가 evidenceremains recurrent.")]:
   with self.subTest(source=source):
    literal=adapter._literal_source_quote("Header "+source+" End",quote)
    self.assertIn(literal,source)
    self.assertEqual(adapter.original.norm(literal),adapter.original.norm(quote))
 def test_partial_compatibility_decomposition_is_not_promoted(self):
  with self.assertRaises(adapter.EvidenceBridgeError):
   adapter._literal_source_quote("The next café state is recurrent.","The next cafe")
 def test_invalid_partial_match_does_not_hide_later_exact_span(self):
  page="The next café value. Then The next ca\nfe remains."
  quote="The next cafe"
  literal=adapter._literal_source_quote(page,quote)
  self.assertEqual(literal,"The next ca\nfe")
if __name__=='__main__':unittest.main()
