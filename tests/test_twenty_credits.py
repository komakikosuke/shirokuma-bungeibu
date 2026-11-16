import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from twenty_char import count_characters


class TwentyCreditsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "twenty-credits/index.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "twenty-credits/style.css").read_text(encoding="utf-8")
        cls.js = (ROOT / "twenty-credits/app.js").read_text(encoding="utf-8")
        cls.data = json.loads((ROOT / "twenty-credits/data/works.json").read_text(encoding="utf-8"))

    def test_six_real_extracted_works_keep_author_pairing(self):
        works = self.data["works"]
        extracted = [work for work in works if work["sourceType"] == "extracted"]
        samples = [work for work in works if work["sourceType"] == "sample"]

        self.assertEqual(self.data["sourceSummary"], {"checked": 20, "extracted": 6})
        self.assertEqual(len(works), 9)
        self.assertEqual(len(extracted), 6)
        self.assertEqual(len(samples), 3)
        self.assertEqual(len({work["key"] for work in works}), 9)

        for work in works:
            with self.subTest(key=work["key"]):
                self.assertEqual(count_characters(work["text"]), 20)
                self.assertEqual(work["charCount"], 20)
                self.assertTrue(work["authorName"].strip())

        for work in extracted:
            with self.subTest(key=work["key"]):
                self.assertRegex(work["url"], rf"^https://note\.com/{re.escape(work['handle'])}/n/{work['key']}$")

        for work in samples:
            with self.subTest(key=work["key"]):
                self.assertIsNone(work["url"])
                self.assertIsNone(work["handle"])

    def test_page_is_unindexed_and_homepage_has_no_route_to_it(self):
        self.assertIn('name="robots" content="noindex,nofollow,noarchive"', self.index)
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("twenty-credits", homepage)

    def test_page_has_controls_and_reduced_motion_support(self):
        self.assertIn('id="toggleButton"', self.index)
        self.assertIn('id="restartButton"', self.index)
        self.assertIn("prefers-reduced-motion", self.css)
        self.assertIn('matchMedia("(prefers-reduced-motion: reduce)")', self.js)

    def test_dynamic_content_is_created_as_text(self):
        self.assertIn("node.textContent = text", self.js)
        self.assertNotIn("innerHTML", self.js)

    def test_credit_roll_does_not_link_out_to_note(self):
        self.assertNotIn("source-link", self.index)
        self.assertNotIn("source-link", self.js)
        self.assertNotIn('element("a"', self.js)

    def test_credit_roll_omits_story_numbering(self):
        self.assertNotIn("SHORT STORY", self.js)
        self.assertNotIn("credit-number", self.js)
        self.assertNotIn("credit-number", self.css)

    def test_membership_and_club_credits_have_distinct_hierarchy(self):
        works = self.data["works"]
        self.assertEqual(sum(work["creditGroup"] == "membership" for work in works), 5)
        self.assertEqual(sum(work["creditGroup"] == "club" for work in works), 4)
        self.assertIn("MEMBERSHIP MEMBERS", self.js)
        self.assertIn("CLUB MEMBERS", self.js)
        self.assertIn("credit-work--club", self.js)
        self.assertIn(".credit-work--club .story-text", self.css)
        self.assertIn(".credits-group-heading", self.css)


if __name__ == "__main__":
    unittest.main()
