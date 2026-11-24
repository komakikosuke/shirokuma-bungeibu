import copy
import importlib.util
import json
from pathlib import Path
import unittest
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("atlas", ROOT / "scripts/sync_prefecture_atlas.py")
atlas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(atlas)
PREFECTURES = json.loads((ROOT / "prefectures/map.json").read_text())["prefectures"]
SEED = {"key": "n111", "handle": "writer"}


def payload(tags=None, **overrides):
    data = {
        "key": "n111", "status": "published", "name": "旅の記憶",
        "publish_at": "2026-11-24T20:00:00+09:00",
        "user": {"urlname": "writer", "nickname": "書く人"},
        "hashtag_notes": [{"hashtag": {"name": name}} for name in (tags if tags is not None else [atlas.TAG, "京都府"])],
    }
    data.update(overrides)
    return {"data": data}


class FakeClient:
    def __init__(self, rows, responses):
        self.rows = rows
        self.responses = responses
        self.requested = []

    def discover(self, max_pages=200):
        return self.rows, 1

    def article(self, key):
        self.requested.append(key)
        response = self.responses[key]
        if isinstance(response, Exception):
            raise response
        return response


def previous(*articles):
    return {"version": 1, "tag": atlas.TAG, "articles": list(articles)}


class EligibilityTests(unittest.TestCase):
    def test_requires_campaign_and_registered_prefecture_tag(self):
        self.assertIsNotNone(atlas.parse_article(SEED, payload(), PREFECTURES))
        for tags in [[], [atlas.TAG], ["京都府"], [atlas.TAG, "京都"], [atlas.TAG, "京都旅行"], [atlas.TAG + "2", "京都府"]]:
            with self.subTest(tags=tags):
                self.assertIsNone(atlas.parse_article(SEED, payload(tags), PREFECTURES))

    def test_body_and_title_cannot_substitute_for_registered_tags(self):
        data = payload([], body="#" + atlas.TAG + " #東京都", name="#" + atlas.TAG + " #東京都")
        self.assertIsNone(atlas.parse_article(SEED, data, PREFECTURES))

    def test_multiple_prefectures_and_duplicate_tags(self):
        article = atlas.parse_article(SEED, payload([atlas.TAG, "#東京都", "京都府", "東京都", "北海道"]), PREFECTURES)
        self.assertEqual(["01", "13", "26"], article["prefectures"])

    def test_paid_and_non_text_notes_are_not_excluded(self):
        article = atlas.parse_article(SEED, payload(price=300, type="SoundNote", body=None), PREFECTURES)
        self.assertTrue(article["isPaid"])
        self.assertNotIn("body", article)

    def test_all_47_official_names_work(self):
        self.assertEqual(47, len(PREFECTURES))
        for pref in PREFECTURES:
            article = atlas.parse_article(SEED, payload([atlas.TAG, pref["name"]]), PREFECTURES)
            self.assertEqual([pref["code"]], article["prefectures"])

    def test_unknown_tag_schema_is_an_error_not_an_exclusion(self):
        data = payload()
        del data["data"]["hashtag_notes"]
        with self.assertRaises(ValueError):
            atlas.parse_article(SEED, data, PREFECTURES)

    def test_article_identity_must_match(self):
        with self.assertRaises(ValueError):
            atlas.parse_article(SEED, payload(key="n999"), PREFECTURES)

    def test_drafts_and_reserved_notes_do_not_appear(self):
        for change in [{"status": "draft"}, {"is_draft": True}, {"is_reserved": True}, {"is_published": False}]:
            self.assertIsNone(atlas.parse_article(SEED, payload(**change), PREFECTURES))

    def test_unknown_publication_status_is_an_error(self):
        with self.assertRaises(ValueError):
            atlas.parse_article(SEED, payload(status=None), PREFECTURES)

    def test_naive_dates_are_rejected(self):
        with self.assertRaises(ValueError):
            atlas.parse_article(SEED, payload(publish_at="2026-11-24T20:00:00"), PREFECTURES)

    def test_untrusted_images_are_not_published(self):
        article = atlas.parse_article(SEED, payload(eyecatch="javascript:alert(1)"), PREFECTURES)
        self.assertEqual("", article["imageUrl"])
        self.assertEqual("", atlas.safe_image("https://st-note.com.evil.example/x.jpg"))


class DiscoveryTests(unittest.TestCase):
    def client(self, pages):
        client = atlas.NoteClient(delay=0)
        def get(path):
            page = int(path.rsplit("=", 1)[-1])
            response = pages[page]
            if isinstance(response, Exception):
                raise response
            return response
        client.get = get
        return client

    def test_traverses_every_page_and_deduplicates(self):
        row = {"key": "n111", "user": {"urlname": "writer"}}
        other = {"key": "n222", "user": {"urlname": "other"}}
        client = self.client({1: {"data": {"notes": [row], "next_page": 2}}, 2: {"data": {"notes": [row, other], "next_page": "3"}}, 3: {"data": {"notes": [], "next_page": None}}})
        seeds, pages = client.discover()
        self.assertEqual(["n111", "n222"], [s["key"] for s in seeds])
        self.assertEqual(3, pages)

    def test_capped_scan_fails_instead_of_looking_complete(self):
        client = self.client({1: {"data": {"notes": [{"key": "n111", "user": {"urlname": "writer"}}], "next_page": 2}}})
        with self.assertRaises(RuntimeError):
            client.discover(max_pages=1)

    def test_missing_new_hashtag_is_valid_empty_state(self):
        client = self.client({1: urllib.error.HTTPError("https://note.com", 404, "Not found", {}, None)})
        self.assertEqual(([], 1), client.discover())

    def test_unknown_response_schema_preserves_existing_feed(self):
        with self.assertRaises(ValueError):
            self.client({1: {"data": {"items": []}}}).discover()


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.old = atlas.parse_article(SEED, payload(), PREFECTURES)

    def test_known_article_is_rechecked_even_if_absent_from_discovery(self):
        client = FakeClient([], {"n111": payload([atlas.TAG])})
        document, failures = atlas.sync_atlas(client, previous(self.old), PREFECTURES)
        self.assertEqual(["n111"], client.requested)
        self.assertEqual([], document["articles"])
        self.assertEqual([], failures)

    def test_deleted_article_is_removed(self):
        error = urllib.error.HTTPError("https://note.com", 404, "Not found", {}, None)
        document, _ = atlas.sync_atlas(FakeClient([], {"n111": error}), previous(self.old), PREFECTURES)
        self.assertEqual([], document["articles"])

    def test_transient_failure_keeps_prior_record_while_other_articles_update(self):
        response = payload(key="n222")
        seeds = [SEED, {"key": "n222", "handle": "writer"}]
        client = FakeClient(seeds, {"n111": urllib.error.URLError("timeout"), "n222": response})
        document, failures = atlas.sync_atlas(client, previous(self.old), PREFECTURES)
        self.assertEqual({"n111", "n222"}, {a["key"] for a in document["articles"]})
        self.assertEqual("partial", document["sync"]["status"])
        self.assertEqual(1, len(failures))

    def test_total_failure_cannot_replace_prior_data(self):
        old = previous(self.old)
        before = copy.deepcopy(old)
        client = FakeClient([SEED], {"n111": urllib.error.URLError("offline")})
        with self.assertRaises(RuntimeError):
            atlas.sync_atlas(client, old, PREFECTURES)
        self.assertEqual(before, old)

    def test_edited_prefecture_tags_move_article(self):
        client = FakeClient([SEED], {"n111": payload([atlas.TAG, "北海道", "沖縄県"])})
        document, _ = atlas.sync_atlas(client, previous(self.old), PREFECTURES)
        self.assertEqual(["01", "47"], document["articles"][0]["prefectures"])


if __name__ == "__main__":
    unittest.main()
