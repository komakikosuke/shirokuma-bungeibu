import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TwentyCreditsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "twenty-credits/index.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "twenty-credits/style.css").read_text(encoding="utf-8")
        cls.js = (ROOT / "twenty-credits/app.js").read_text(encoding="utf-8")
        cls.data = json.loads((ROOT / "twenty-credits/data/works.json").read_text(encoding="utf-8"))

    def test_initial_public_data_contains_no_preview_or_fictional_works(self):
        self.assertEqual(self.data["pageStatus"], "scheduled")
        self.assertEqual(self.data["sourceHashtag"], "20字小説")
        self.assertEqual(self.data["sourceSummary"], {"checked": 0, "extracted": 0})
        self.assertEqual(self.data["works"], [])

    def test_page_is_unindexed_and_home_entrance_starts_disabled(self):
        self.assertIn('name="robots" content="noindex,nofollow,noarchive"', self.index)
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="endrollEntry" aria-disabled="true" tabindex="-1"', homepage)
        self.assertIn('entry.href="./twenty-credits/"', homepage)

    def test_page_has_controls_empty_state_and_reduced_motion_support(self):
        self.assertIn('id="toggleButton"', self.index)
        self.assertIn('id="restartButton"', self.index)
        self.assertIn("TUESDAY / 21:00", self.index)
        self.assertIn("emptyScene", self.js)
        self.assertIn("prefers-reduced-motion", self.css)
        self.assertIn('matchMedia("(prefers-reduced-motion: reduce)")', self.js)

    def test_dynamic_content_is_created_as_text(self):
        self.assertIn("node.textContent = text", self.js)
        self.assertNotIn("innerHTML", self.js)

    def test_credit_roll_does_not_link_out_to_note_or_number_stories(self):
        self.assertNotIn("source-link", self.index)
        self.assertNotIn("source-link", self.js)
        self.assertNotIn('element("a"', self.js)
        self.assertNotIn("SHORT STORY", self.js)
        self.assertNotIn("credit-number", self.js)
        self.assertNotIn("credit-number", self.css)

    def test_membership_and_club_credits_have_distinct_hierarchy(self):
        self.assertIn("MEMBERSHIP MEMBERS", self.js)
        self.assertIn("CLUB MEMBERS", self.js)
        self.assertIn("credit-work--${groupKey}", self.js)
        self.assertIn('if (groupKey === "membership")', self.js)
        self.assertIn(".credit-work--club .story-text", self.css)
        self.assertIn(".credits-group-heading", self.css)
        self.assertIn("すぐ書ける。すぐ読める。", self.js)
        self.assertIn("min-height: 12.8vh", self.css)
        self.assertIn("padding-block: clamp(10px, 1.6vh, 16px)", self.css)
        self.assertIn("margin-top: clamp(14px, 2vh, 18px)", self.css)
        self.assertIn("margin-top: clamp(10px, 1.4vh, 13px)", self.css)


if __name__ == "__main__":
    unittest.main()
