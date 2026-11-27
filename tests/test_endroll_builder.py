"""Offline tests for the weekly public end-roll builder."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_twenty_credits import MembershipSnapshot, build_documents, event_window, load_members
from twenty_char import COUNT_RULE

JST = timezone(timedelta(hours=9))
STORY = "今日は昨日の私が置いた鍵で明日を開ける。"


def work(key, handle, published_at, *, status="success", exactly20=True,
         char_count=20, reasons=None):
    return {
        "key": key,
        "url": f"https://note.com/{handle}/n/{key}",
        "title": "20字小説",
        "authorName": handle,
        "handle": handle,
        "publishedAt": published_at,
        "text": (STORY + "。" * max(0, char_count - 20))[:char_count],
        "charCount": char_count,
        "status": status,
        "reasonCodes": [] if reasons is None else reasons,
        "exactly20": exactly20,
    }


def extraction(works, **latest_overrides):
    latest = {
        "since": "2026-11-17T19:00:00+09:00",
        "until": "2026-11-18T00:00:00+09:00",
        "stopReason": "since_boundary",
        "truncated": False,
        "summary": {"total": len(works)},
    }
    latest.update(latest_overrides)
    return {
        "version": 1,
        "hashtag": "20字小説",
        "countRule": COUNT_RULE,
        "latestRun": latest,
        "works": works,
    }


class EndrollBuilderTests(unittest.TestCase):
    def test_allowed_lengths_inside_tuesday_window_are_published(self):
        rows = [
            work("na1", "member_one", "2026-11-17T19:00:00+09:00"),
            work("na2", "club_one", "2026-11-17T23:59:59+09:00"),
            work("na3", "club_two", "2026-11-18T00:00:00+09:00"),
            work("na4", "club_three", "2026-11-17T20:00:00+09:00",
                 status="pending", exactly20=False, char_count=19,
                 reasons=["non_exact_length"]),
        ]
        document, status = build_documents(
            extraction(rows), {"member_one"}, "2026-11-17", "2026-11-17T12:02:00Z"
        )
        self.assertEqual([row["key"] for row in document["works"]], ["na1", "na4", "na2"])
        self.assertEqual([row["creditGroup"] for row in document["works"]], ["membership", "club", "club"])
        self.assertEqual(document["sourceWindow"], {
            "since": "2026-11-17T19:00:00+09:00",
            "until": "2026-11-18T00:00:00+09:00",
        })
        self.assertEqual(document["sourceSummary"], {"checked": 4, "extracted": 3})
        self.assertEqual(status["status"], "ready")
        self.assertEqual((status["membershipCount"], status["clubCount"]), (1, 2))

    def test_empty_result_keeps_entrance_closed(self):
        document, status = build_documents(extraction([]), set(), "2026-11-17")
        self.assertEqual(document["pageStatus"], "empty")
        self.assertEqual(document["works"], [])
        self.assertEqual((status["status"], status["workCount"]), ("empty", 0))

    def test_incomplete_or_wrong_window_never_replaces_public_data(self):
        with self.assertRaisesRegex(ValueError, "完了していない"):
            build_documents(extraction([], truncated=True), set(), "2026-11-17")
        with self.assertRaisesRegex(ValueError, "抽出期間"):
            build_documents(extraction([], since="2026-11-17T18:00:00+09:00"), set(), "2026-11-17")

    def test_event_date_must_be_tuesday(self):
        self.assertEqual(event_window("2026-11-17")[0], datetime(2026, 11, 17, 19, tzinfo=JST))
        self.assertEqual(event_window("2026-11-17")[1], datetime(2026, 11, 18, 0, tzinfo=JST))
        with self.assertRaisesRegex(ValueError, "火曜日"):
            event_window("2026-11-16")

    def test_expanded_window_includes_21_to_24_but_excludes_midnight(self):
        rows = [work("na1", "writer_one", "2026-11-17T21:00:00+09:00"),
                work("na2", "writer_two", "2026-11-17T23:59:59.999+09:00"),
                work("na3", "writer_three", "2026-11-18T00:00:00+09:00"),
                work("na4", "writer_four", "2026-11-17T18:59:59.999+09:00")]
        document, status = build_documents(extraction(rows), set(), "2026-11-17")
        self.assertEqual([row["key"] for row in document["works"]], ["na1", "na2"])
        self.assertEqual(status["workCount"], 2)

    def test_home_entrance_starts_disabled_until_real_data_exists(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="endrollEntry" aria-disabled="true" tabindex="-1"', homepage)
        self.assertIn('entry.href = "./twenty-credits/"', (ROOT / "home/app.js").read_text(encoding="utf-8"))
        status = json.loads((ROOT / "data/twenty-char-status.json").read_text(encoding="utf-8"))
        published = json.loads((ROOT / "twenty-credits/data/works.json").read_text(encoding="utf-8"))
        self.assertEqual(status["workCount"], len(published["works"]))
        self.assertEqual(status["membershipCount"], sum(w["creditGroup"] == "membership" for w in published["works"]))

    def test_server_decisions_are_bound_to_the_exact_publication_and_event(self):
        record = work("na1", "member_one", "2026-11-17T20:00:00+09:00")
        decisions = MembershipSnapshot("2026-11-17", {"snapshotId": "real"}, {
            "na1": {"key": "na1", "handle": "member_one", "publishedAt": record["publishedAt"], "isMember": True},
        })
        document, status = build_documents(extraction([record]), decisions, "2026-11-17")
        self.assertEqual(document["works"][0]["creditGroup"], "membership")
        self.assertEqual(status["membershipSource"], {"snapshotId": "real"})
        with self.assertRaisesRegex(ValueError, "一致しません"):
            build_documents(extraction([{**record, "handle": "other", "url": "https://note.com/other/n/na1"}]), decisions, "2026-11-17")

    def test_fixed_test_member_lists_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "members.json"
            path.write_text(json.dumps({"version": 1, "members": ["test_member"]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "固定のテスト"):
                load_members(path)


if __name__ == "__main__":
    unittest.main()
