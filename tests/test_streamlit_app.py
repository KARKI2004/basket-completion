"""Streamlit interaction checks against frozen local artifacts."""
from __future__ import annotations
import unittest
import json
from pathlib import Path
from basket_completion.demo import DemoService, load_saved_results
try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None
APP_PATH = Path(__file__).resolve().parents[1] / "app/main.py"

@unittest.skipIf(AppTest is None, "Install the demo extra")
class StreamlitAppTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(APP_PATH), default_timeout=60).run()
        self.assertFalse(self.app.exception)
        self.assertFalse(self.app.error)
    def demo(self):
        self.app.get("segmented_control")[0].set_value("Demo").run()
        self.assertFalse(self.app.exception)
        return self.app
    def button(self, key):
        return next(item for item in self.app.button if item.key == key)
    def browse_keys(self):
        return [x.key for x in self.app.button if x.key and x.key.startswith("browse_add:")]
    def test_navigation_and_saved_reports(self):
        self.assertEqual(self.app.get("segmented_control")[0].value, "Reports and outcomes")
        self.assertEqual(self.app.query_params["view"], "Reports and outcomes")
        saved=load_saved_results()["primary"]
        displayed={m.label:m.value for m in self.app.metric}
        self.assertEqual(displayed["Co-purchase method · top 5"],f"{saved['combined_hit_rate_at_5']:.2%}")
        self.assertEqual(len(self.app.get("image")),3)
        self.assertEqual([x.value for x in self.app.get("subheader")],
                         ["Project background", "Data and methodology", "Outcomes", "Assumptions and limitations"])
        self.assertEqual(sum(m.label=="Co-purchase method · top 5" for m in self.app.metric),1)
        self.assertEqual(sum(m.label=="Popular products · top 5" for m in self.app.metric),1)
        summary=json.loads((APP_PATH.parents[1] / "reports/preparation_summary.json").read_text())
        split_caption=" ".join(x.value for x in self.app.get("caption"))
        for label in ("train","validation","test"):
            self.assertIn(f"{label.title()} {summary['splits'][label]['baskets']:,}", split_caption)
        self.assertEqual(displayed["Difference · percentage points"],
                         f"+{100*saved['difference_from_popularity']:.2f}")
        self.assertTrue(any("I evaluated five suggestions" in x.value for x in self.app.get("caption")))
        report_text=" ".join(x.value for x in self.app.get("markdown"))
        self.assertIn("I kept positive purchase lines",report_text)
        self.assertIn("I used product presence rather than quantity",report_text)
        self.assertNotIn("/n Public",report_text)
        self.assertNotIn("File change.",report_text)
        self.assertIn("useful cart context",report_text)
        self.assertIn("UCI Online Retail dataset",report_text)
        self.assertIn("ranked products by that count with stock code breaking ties",report_text)
        self.assertIn("skipped products already in the cart",report_text)
        self.assertIn("CC BY 4.0",report_text)
        self.assertTrue(any(x.label=="How I estimated uncertainty" for x in self.app.get("expander")))
        self.assertTrue((APP_PATH.parents[1] / "reports/figures/method_comparison.png").is_file())
        next(x for x in self.app.button if x.label=="Try the demo →").click().run()
        self.assertEqual(self.app.get("segmented_control")[0].value,"Demo")
        self.assertEqual(self.app.query_params["view"],"Demo")
        self.app.get("segmented_control")[0].set_value("Reports and outcomes").run()
        self.demo()
        self.assertEqual(self.app.query_params["view"],"Demo")
        self.assertTrue(any("Add a product below, then see what goes with your cart." in x.value for x in self.app.get("markdown")))
        self.assertFalse(any(x.key == "example_cart" or (x.key or "").startswith("history:") for x in self.app.button))
    def test_two_row_paging_search_and_details(self):
        self.demo()
        first=self.browse_keys()
        self.assertEqual(len(first),8)
        self.assertEqual(len([x for x in self.app.get("expander") if x.label=="Details"]),8)
        next(x for x in self.app.button if x.label=="Next →").click().run()
        self.assertEqual(len(self.browse_keys()),8)
        self.assertNotEqual(first,self.browse_keys())
        next(x for x in self.app.button if x.label=="← Previous").click().run()
        self.assertEqual(first,self.browse_keys())
        self.app.text_input[0].set_value("85123A").run()
        self.assertEqual(set(self.browse_keys()),{"browse_add:85123A","browse_add:85123a"})
        self.assertTrue(any("Stock code: 85123A" in x.value for x in self.app.get("caption")))
        self.app.text_input[0].set_value("no such product").run()
        self.assertTrue(any("No matching products" in x.value for x in self.app.info))
        self.app.text_input[0].set_value("").run()
        self.assertEqual(self.browse_keys(),first)
        model=DemoService.from_frozen()
        self.assertEqual(len(model.products),3500)
        last,total,last_page=model.browse("",9999,page_size=8)
        self.assertEqual((total,last_page,len(last)),(3500,437,4))
        self.app.session_state["browse_page"]=last_page
        self.app.run()
        self.assertEqual(self.browse_keys(),[f"browse_add:{product.code}" for product in last])
        self.assertTrue(next(x for x in self.app.button if x.label=="Next →").disabled)
        self.assertEqual(len(self.browse_keys()),4)
    def test_cart_suggestions_and_restoration(self):
        self.demo()
        self.button("browse_add:85123A").click().run()
        self.assertEqual(dict(self.app.session_state["basket"]),{"85123A":1})
        self.assertFalse(any(x.key=="suggest:85123A" for x in self.app.button))
        evidence=DemoService.from_frozen().recommend(("85123A",)).combined[0].evidence
        captions=" ".join(x.value for x in self.app.get("caption"))
        self.assertIn(f"Bought in {evidence.pair_count} training orders",captions)
        self.button("browse_add:85123A").click().run()
        self.assertTrue(any("Already in your cart" in x.value for x in self.app.info))
        next(x for x in self.app.number_input if x.key=="qty:85123A").set_value(3).run()
        self.assertIn('"85123A":3',self.app.query_params["basket"])
        first_three=[x.key for x in self.app.button if x.key and x.key.startswith("suggest:")]
        self.assertEqual(len(first_three),3)
        next(x for x in self.app.button if x.label=="Show more (2)").click().run()
        all_five=[x.key for x in self.app.button if x.key and x.key.startswith("suggest:")]
        self.assertEqual(len(all_five),5)
        self.assertEqual(all_five[:3],first_three)
        next(x for x in self.app.button if x.label=="Show fewer").click().run()
        self.assertEqual([x.key for x in self.app.button if x.key and x.key.startswith("suggest:")],first_three)
        key=first_three[0]
        self.button(key).click().run()
        self.assertIn(key.split(":",1)[1],self.app.session_state["basket"])
        self.button("remove:85123A").click().run()
        self.assertNotIn("85123A",self.app.session_state["basket"])
        next(x for x in self.app.button if x.label=="Clear cart").click().run()
        self.assertEqual(dict(self.app.session_state["basket"]),{})
        self.assertNotIn("basket",self.app.query_params)
        fresh=AppTest.from_file(str(APP_PATH),default_timeout=60)
        fresh.query_params["view"]="Demo"; fresh.query_params["basket"]='{"85123A":3}'
        fresh.run()
        self.assertEqual(fresh.get("segmented_control")[0].value,"Demo")
        self.assertEqual(dict(fresh.session_state["basket"]),{"85123A":3})
    def test_fallback_label(self):
        self.demo()
        rare=next(x.code for x in DemoService.from_frozen().products if x.training_baskets==1)
        self.app.text_input[0].set_value(rare).run()
        self.button(f"browse_add:{rare}").click().run()
        self.assertEqual(sum("popularity fallback" in x.value for x in self.app.get("caption")),3)
        next(x for x in self.app.button if x.label=="Show more (2)").click().run()
        self.assertEqual(sum("popularity fallback" in x.value for x in self.app.get("caption")),5)
if __name__ == "__main__": unittest.main()
