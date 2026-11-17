import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sync_twenty_members import sync_members


class MembershipSyncTests(unittest.TestCase):
    def setUp(self):
        self.work = {"key": "n123", "handle": "actual_author", "publishedAt": "2026-11-17T20:00:00+09:00"}
        self.document = {"version": 1, "sourceHashtag": "20字小説", "eventDate": "2026-11-17", "works": [self.work]}
        self.response = {"version": 2, "complete": True, "eventDate": "2026-11-17",
                         "source": {"snapshotId": "snapshot", "capturedAt": 1},
                         "works": [{**self.work, "isMember": True}]}
        self.environment = {"ACTIONS_ID_TOKEN_REQUEST_URL": "https://actions.test/token?job=1",
                            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "ephemeral-test-token"}

    def test_workflow_uses_its_audience_bound_token_and_submits_only_participants(self):
        with patch.dict(os.environ, self.environment), patch("sync_twenty_members.request_json", side_effect=[{"value": "signed"}, self.response]) as request:
            result = sync_members(self.document, "2026-11-17")
        self.assertTrue(result["works"][0]["isMember"])
        self.assertIn("audience=https%3A%2F%2Fshirokuma-writing-room", request.call_args_list[0].args[0].full_url)
        self.assertNotIn(b"text", request.call_args_list[1].args[0].data)

    def test_missing_duplicate_or_changed_decisions_stop_publication(self):
        invalid = [[], [self.response["works"][0]] * 2, [{**self.response["works"][0], "handle": "different"}],
                   [{**self.response["works"][0], "isMember": "yes"}]]
        for works in invalid:
            with self.subTest(works=works), patch.dict(os.environ, self.environment), patch(
                    "sync_twenty_members.request_json", side_effect=[{"value": "signed"}, {**self.response, "works": works}]):
                with self.assertRaises(ValueError):
                    sync_members(self.document, "2026-11-17")


if __name__ == "__main__":
    unittest.main()
