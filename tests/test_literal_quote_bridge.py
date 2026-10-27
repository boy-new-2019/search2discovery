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
if __name__=='__main__':unittest.main()
