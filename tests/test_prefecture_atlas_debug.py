import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_prefecture_atlas_debug as debug


def rss_item(key, date, creator=debug.CREATOR):
    return "<item><link>https://note.com/" + creator + "/n/" + key + "</link><pubDate>" + date + "</pubDate></item>"


class DebugFeedTests(unittest.TestCase):
    def test_rss_order_does_not_make_an_older_pinned_article_latest(self):
        xml = "<rss><channel>" + rss_item("nold", "Sun, 22 Nov 2026 12:00:00 GMT") + rss_item("nnew", "Tue, 24 Nov 2026 12:00:00 GMT") + "</channel></rss>"
        self.assertEqual(["nnew", "nold"], [row["key"] for row in debug.rss_seeds(xml)])

    def test_other_creators_are_ignored(self):
        xml = "<rss><channel>" + rss_item("nwrong", "Tue, 24 Nov 2026 12:00:00 GMT", "other") + "</channel></rss>"
        with self.assertRaises(ValueError):
            debug.rss_seeds(xml)

    def payload(self, creator=debug.CREATOR):
        return {"data": {"key": "n111", "status": "published", "name": "最新の記事",
                         "publish_at": "2026-11-24T20:00:00+09:00",
                         "user": {"urlname": creator, "nickname": "小牧幸助"},
                         "hashtag_notes": [{"hashtag": {"name": "20字小説"}}]}}

    def test_preview_does_not_add_campaign_or_prefecture_hashtags(self):
        article = debug.preview_article({"key": "n111"}, self.payload())
        self.assertEqual(["20字小説"], article["tags"])
        self.assertNotIn("prefectures", article)
        self.assertNotIn("body", article)

    def test_detail_must_belong_to_the_requested_creator(self):
        with self.assertRaises(ValueError):
            debug.preview_article({"key": "n111"}, self.payload("other"))


if __name__ == "__main__":
    unittest.main()
