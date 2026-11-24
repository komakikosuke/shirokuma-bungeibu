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

    def test_multiline_publication_inserts_one_space_per_original_break(self):
        lines = [self.record["text"][:7], self.record["text"][7:14], self.record["text"][14:]]
        published = eligible_work({**self.record, "sourceLines": lines}, self.since, self.until, set())
        self.assertEqual(published["text"], " ".join(lines))
        self.assertEqual(published["sourceLines"], lines)
        self.assertEqual(published["charCount"], 20)

    def test_four_line_publication_inserts_one_space_per_original_break(self):
        lines = [self.record["text"][index:index + 5] for index in range(0, 20, 5)]
        published = eligible_work({**self.record, "sourceLines": lines}, self.since, self.until, set())
        self.assertEqual(published["text"], " ".join(lines))
        self.assertEqual(published["sourceLines"], lines)
        self.assertEqual(published["charCount"], 20)

    def test_multiline_source_lines_must_match_the_validated_story(self):
        for lines in ([self.record["text"]], ["あ" * 10, "あ" * 10],
                      [self.record["text"][index:index + 4] for index in range(0, 20, 4)]):
            with self.subTest(lines=lines):
                self.assertIsNone(eligible_work({**self.record, "sourceLines": lines}, self.since, self.until, set()))

    def test_nineteen_to_twenty_one_characters_are_published_with_or_without_headings(self):
        for length in (19, 20, 21):
            for heading in (False, True):
                reasons = (["non_exact_length"] if length != 20 else []) + (["first_line_heading"] if heading else [])
                record = {**self.record, "text": "あ" * length, "charCount": length,
                          "exactly20": length == 20, "reasonCodes": reasons,
                          "status": "pending" if reasons else "success"}
                with self.subTest(length=length, heading=heading):
                    published = eligible_work(record, self.since, self.until, set())
                    self.assertIsNotNone(published)
                    self.assertEqual(published["charCount"], length)
                    self.assertEqual(published["text"], record["text"])

    def test_heading_with_another_hold_reason_or_wrong_length_stays_excluded(self):
        for changes in (
            {"reasonCodes": ["first_line_heading", "explanatory_first_line"]},
            {"text": "あ" * 18, "charCount": 18, "exactly20": False},
            {"text": "あ" * 22, "charCount": 22, "exactly20": False},
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
