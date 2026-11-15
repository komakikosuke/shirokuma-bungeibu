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
        self.assertEqual(self.data["sourceSummary"], {"checked": 20, "extracted": 6})
        self.assertEqual(len(works), 6)
        self.assertEqual(len({work["key"] for work in works}), 6)
        for work in works:
            with self.subTest(key=work["key"]):
                self.assertEqual(count_characters(work["text"]), 20)
                self.assertEqual(work["charCount"], 20)
                self.assertRegex(work["url"], rf"^https://note\.com/{re.escape(work['handle'])}/n/{work['key']}$")
                self.assertTrue(work["authorName"].strip())

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


if __name__ == "__main__":
    unittest.main()
