from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_twenty_credits import credit_sort_key, eligible_work, event_window


class TwentyCreditPolicyTests(unittest.TestCase):
    def setUp(self):
        self.since, self.until = event_window("2026-11-17")
        self.record = {
            "key": "n123abc", "handle": "writer", "authorName": "作者",
            "title": "見出しの作品", "url": "https://note.com/writer/n/n123abc",
            "text": "エンドロールが山場だ。僕の名に目を拭う。",
            "publishedAt": "2026-11-17T20:00:00+09:00",
            "status": "pending", "reasonCodes": ["first_line_heading"],
            "charCount": 20, "exactly20": True,
        }

    def test_twenty_character_heading_is_published(self):
        self.assertIsNotNone(eligible_work(self.record, self.since, self.until, set()))

    def test_heading_with_another_hold_reason_or_wrong_length_stays_excluded(self):
        for changes in (
            {"reasonCodes": ["first_line_heading", "explanatory_first_line"]},
            {"charCount": 19, "exactly20": False},
            {"status": "failed"},
            {"publishedAt": "2026-11-17T21:00:00+09:00"},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(eligible_work({**self.record, **changes}, self.since, self.until, set()))

    def test_host_follows_all_subscribers_and_precedes_club_works(self):
        host = deepcopy(self.record)
        host.update(handle="komaki_kousuke", url="https://note.com/komaki_kousuke/n/n123abc")
        host_work = eligible_work(host, self.since, self.until, set())
        subscriber = {**host_work, "key": "nsubscriber", "handle": "subscriber", "publishedAt": "2026-11-17T20:50:00+09:00"}
        club = {**host_work, "key": "nclub", "handle": "club", "creditGroup": "club"}
        ordered = sorted([club, host_work, subscriber], key=credit_sort_key)
        self.assertEqual([work["handle"] for work in ordered], ["subscriber", "komaki_kousuke", "club"])


if __name__ == "__main__":
    unittest.main()
