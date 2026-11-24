"""Offline behavior tests. No network calls and no changes to live site data."""
from copy import deepcopy
from datetime import timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from twenty_char import (ROOT, NoteClient, count_characters, extract_article,
                         first_body_line, normalize_hashtag, parse_time, run_extraction,
                         seed_from_row, seed_from_url)

STORY = "今日は昨日の私が置いた鍵で明日を開ける。"  # 20 visible characters, including 。
SEED = seed_from_url("https://note.com/test_author/n/na00000000001")


def article(body=None, **fields):
    data = {"key": SEED["key"], "name": "テスト作品", "body": f"<p>{STORY}</p>" if body is None else body,
            "user": {"urlname": "test_author", "nickname": "テスト作者"},
            "publish_at": "2026-11-13T20:00:00+09:00", "status": "published", "type": "TextNote",
            "price": 0, "is_limited": False,
            "hashtag_notes": [{"hashtag": {"name": "#20字小説"}}]}
    data.update(fields)
    return {"data": data}


def extract(body=None, **fields):
    return extract_article(SEED, article(body, **fields), "20字小説")


class ExtractionTests(unittest.TestCase):
    def test_normal_twenty_character_story_and_author_pair(self):
        row = extract()
        self.assertEqual((row["text"], row["charCount"], row["status"]), (STORY, 20, "success"))
        self.assertEqual((row["handle"], row["authorName"]), ("test_author", "テスト作者"))
        self.assertTrue(row["isCandidate"])
        self.assertTrue(row["exactly20"])
        self.assertTrue(row["reviewRequired"])
        self.assertEqual(row["publicationStatus"], "unreviewed")

    def test_nineteen_and_twenty_one_are_candidates_pending_review(self):
        for text, count in [(STORY[:-1], 19), (STORY + "！", 21)]:
            with self.subTest(count=count):
                row = extract(f"<p>{text}</p>")
                self.assertEqual((row["charCount"], row["status"]), (count, "pending"))
                self.assertTrue(row["isCandidate"])
                self.assertFalse(row["exactly20"])
                self.assertIn("non_exact_length", row["reasonCodes"])

    def test_eighteen_and_twenty_two_are_not_candidates(self):
        for text, count in [(STORY[:-2], 18), (STORY + "！！", 22)]:
            with self.subTest(count=count):
                row = extract(f"<p>{text}</p>")
                self.assertEqual((row["charCount"], row["status"]), (count, "failed"))
                self.assertFalse(row["isCandidate"])
                self.assertIn("outside_range", row["reasonCodes"])

    def test_leading_empty_paragraphs_breaks_and_wide_whitespace(self):
        row = extract(f"\n<p><br></p><p>　&nbsp; </p><p><br>　 {STORY}　 </p>")
        self.assertEqual((row["text"], row["status"]), (STORY, "success"))

    def test_explanation_after_story_is_not_appended(self):
        row = extract(f"<p>{STORY}</p><p>ここからは自由な説明です。</p>")
        self.assertEqual(row["text"], STORY)
        self.assertEqual(row["charCount"], 20)

    def test_break_inside_paragraph_is_a_line_boundary(self):
        row = extract(f"<p>{STORY}<br>ここからは説明です。</p>")
        self.assertEqual((row["text"], row["charCount"]), (STORY, 20))

    def test_do_not_skip_a_preface_but_allow_a_complete_split_opening(self):
        row = extract(f"<p>前書き</p><p>{STORY}</p>")
        self.assertEqual((row["text"], row["charCount"], row["status"]), ("前書き", 3, "failed"))
        row = extract(f"<p>{STORY[:9]}</p><p>{STORY[9:]}</p>")
        self.assertEqual((row["text"], row["charCount"], row["status"]), (STORY, 20, "success"))
        self.assertEqual(row["sourceLines"], [STORY[:9], STORY[9:]])

    def test_two_to_four_opening_lines_need_a_complete_boundary(self):
        parts = [STORY[:7], STORY[7:14], STORY[14:]]
        bodies = [
            f"<p>{STORY[:10]}<br>{STORY[10:]}</p>",
            f"<p>{STORY[:10]}</p>\n<p>{STORY[10:]}</p><p><br></p><p>説明です。</p>",
            f"<p>{STORY[:10]}<br>{STORY[10:]}</p><img src='x'><p>説明です。</p>",
            "<p>" + "<br>".join(parts) + "</p><hr><p>説明です。</p>",
            "\n".join(parts) + "\n\n説明です。",
            "<p>" + "<br>".join(STORY[index:index + 5] for index in range(0, 20, 5)) + "</p>",
        ]
        for body in bodies:
            with self.subTest(body=body):
                row = extract(body)
                self.assertEqual((row["text"], row["charCount"], row["status"]), (STORY, 20, "success"))
                self.assertEqual("".join(row["sourceLines"]), STORY)

    def test_multiline_headings_and_allowed_lengths_keep_their_original_text(self):
        for length in (19, 20, 21):
            text = "あ" * length
            row = extract(f"<h3>{text[:8]}</h3><h3>{text[8:]}</h3><p><br></p><p>説明</p>")
            with self.subTest(length=length):
                self.assertEqual((row["text"], row["charCount"]), (text, length))
                self.assertEqual(row["sourceLines"], [text[:8], text[8:]])
                self.assertIn("first_line_heading", row["reasonCodes"])
                self.assertTrue(row["isCandidate"])

    def test_multiline_never_skips_blanks_greetings_or_extra_text(self):
        bodies = [
            f"<p>{STORY[:10]}</p><p><br></p><p>{STORY[10:]}</p>",
            f"<p>{STORY[:10]}<br>{STORY[10:]}<br>さらに続く文章。</p>",
            "<p>あいうえ<br>おかきく<br>けこさし<br>すせそた<br>ちつてと</p>",
            "<p>こんばんは！<br>" + "あ" * 14 + "</p>",
            "<p>#20字小説<br>" + "あ" * 14 + "</p>",
            "<p>前書き</p><p>" + STORY[3:] + "</p>",
            f"<p>{STORY[:10]}<br><a href='https://example.com'>{STORY[10:]}</a></p>",
            f"<p>{STORY[:10]}</p><blockquote><p>{STORY[10:]}</p></blockquote>",
        ]
        for body in bodies:
            with self.subTest(body=body):
                row = extract(body)
                self.assertEqual(row["status"], "failed")
                self.assertNotIn("sourceLines", row)

    def test_heading_is_pending_even_when_twenty_characters(self):
        row = extract(f"<h3>{STORY}</h3><p>説明</p>")
        self.assertEqual(row["status"], "pending")
        self.assertIn("first_line_heading", row["reasonCodes"])

    def test_twenty_character_intro_is_pending(self):
        intro = "こんにちは。今回は二十字小説の紹介です。"
        row = extract(f"<p>{intro}</p><p>{STORY}</p>")
        self.assertEqual(row["charCount"], 20)
        self.assertEqual(row["text"], intro)
        self.assertEqual(row["status"], "pending")
        self.assertIn("explanatory_first_line", row["reasonCodes"])

    def test_leading_hashtag_only_lines_are_skipped_including_links_and_honorifics(self):
        prefixes = [
            "<p>#20字小説</p>",
            "<p>＃20字小説<br>#シロクマ文芸部</p><p><br></p>",
            "<p>#20字小説 #シロクマ文芸部</p>",
            "<p>#20字小説#シロクマ文芸部</p>",
            "<p><a href='https://note.com/hashtag/20字小説'>#20字小説</a></p>",
            "<h3>#小牧幸助　様</h3><p>#20字小説</p>",
        ]
        for prefix in prefixes:
            with self.subTest(prefix=prefix):
                row = extract(prefix + f"<p>{STORY}</p>")
                self.assertEqual((row["text"], row["charCount"], row["status"]), (STORY, 20, "success"))

    def test_hashtags_do_not_count_toward_the_multiline_story_limit(self):
        row = extract("<p>#20字小説<br>#シロクマ文芸部<br>#小説</p>"
                      f"<p>{STORY[:7]}<br>{STORY[7:14]}<br>{STORY[14:]}</p>")
        self.assertEqual(row["text"], STORY)
        self.assertEqual(row["sourceLines"], [STORY[:7], STORY[7:14], STORY[14:]])

    def test_hashtag_footer_ends_a_multiline_story_without_becoming_story_text(self):
        row = extract(f"<p>{STORY[:10]}<br>{STORY[10:]}<br>#20字小説</p>")
        self.assertEqual((row["text"], row["charCount"], row["status"]), (STORY, 20, "success"))
        self.assertEqual(row["sourceLines"], [STORY[:10], STORY[10:]])

    def test_hashtags_do_not_allow_skipping_greetings_or_crossing_story_boundaries(self):
        for body in (
            "<p>#20字小説</p><p>こんばんは！</p>" + f"<p>{STORY}</p>",
            f"<p>{STORY[:10]}<br>#20字小説<br>{STORY[10:]}</p>",
        ):
            with self.subTest(body=body):
                row = extract(body)
                self.assertNotEqual(row["status"], "success")
                self.assertNotIn("sourceLines", row)

    def test_matching_non_twenty_character_opening_notices_are_skipped(self):
        prefixes = [
            "<p>▲今回も参加しました！</p><hr>",
            "<p>（20文字）</p><p><br></p>",
            "<h3>第一部　20字小説（20文字）</h3>",
            "<p>#20字小説 の紹介です。</p>",
            "<blockquote>#20字小説</blockquote>",
            "<p>今回の参加作品です。</p><p>（２０文字）</p><p><br></p>",
        ]
        for prefix in prefixes:
            with self.subTest(prefix=prefix):
                row = extract(prefix + f"<p>{STORY}</p>")
                self.assertEqual((row["text"], row["charCount"], row["status"]), (STORY, 20, "success"))
        for keyword in ("参加", "20文字", "20字"):
            for length in (19, 21):
                preface = keyword + "あ" * (length - len(keyword))
                row = extract(f"<p>{preface}</p><p>{STORY}</p>")
                self.assertEqual((row["text"], row["charCount"]), (STORY, 20))

    def test_exactly_twenty_character_lines_with_notice_keywords_are_kept(self):
        for keyword in ("参加", "20文字", "20字"):
            text = keyword + STORY[len(keyword):]
            row = extract(f"<p>{text}</p><p>ここからは説明です。</p>")
            self.assertEqual((row["text"], row["charCount"], row["status"]), (text, 20, "success"))

    def test_notice_skipping_does_not_skip_titles_or_join_across_blanks(self):
        row = extract(f"<p>参加しました。</p><h2>『付箋』</h2><p>{STORY}</p>")
        self.assertEqual((row["text"], row["charCount"], row["status"]), ("『付箋』", 4, "failed"))
        row = extract(f"<p>（20文字）</p><p>{STORY[:10]}<br><br>{STORY[10:]}</p>")
        self.assertEqual(row["status"], "failed")
        self.assertNotIn("sourceLines", row)
        row = extract(f"<p>参加しました。</p><p>{STORY[:10]}<br>{STORY[10:]}<br>参加しました。</p>")
        self.assertEqual(row["status"], "failed")

    def test_four_line_story_with_text_separator_keeps_its_entire_opening(self):
        lines = ["花が散り戻らぬ", "これ真実", "鳥立つ", "それを見る。"]
        body = "<p>（20文字）</p><p>" + "<br>".join(lines) + "</p><p>＿＿＿＿＿＿<br>◯コンセプト<br>作品についての説明。</p>"
        row = extract(body)
        self.assertEqual((row["text"], row["charCount"], row["status"]), ("".join(lines), 20, "success"))
        self.assertEqual(row["sourceLines"], lines)

    def test_body_hashtags_do_not_replace_verified_article_tags_or_supply_a_story(self):
        row = extract(f"<p>#20字小説</p><p>{STORY}</p>", hashtag_notes=[])
        self.assertIn("hashtag_unverified", row["reasonCodes"])
        self.assertEqual(row["status"], "pending")
        self.assertEqual(extract("<p>#20字小説<br>#小説</p>")["reasonCodes"], ["empty_body"])

    def test_title_repeated_in_body_is_pending(self):
        row = extract(name=STORY)
        self.assertEqual(row["status"], "pending")
        self.assertIn("first_line_matches_title", row["reasonCodes"])

    def test_missing_body_does_not_use_title_description_or_listing_snippet(self):
        seed = {**SEED, "body": STORY, "title": STORY}
        payload = article(description=STORY)
        payload["data"]["body"] = None
        row = extract_article(seed, payload, "20字小説")
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["reasonCodes"], ["body_unavailable"])
        self.assertIsNone(row["text"])
        self.assertIsNone(row["charCount"])

    def test_empty_and_image_only_bodies_fail_without_using_alt(self):
        for body in ["", "<p><br></p>", f'<figure><img alt="{STORY}" src="x"></figure>']:
            with self.subTest(body=body):
                self.assertEqual(extract(body)["reasonCodes"], ["empty_body"])

    def test_grapheme_clusters_for_emoji_combining_marks_and_rare_kanji(self):
        self.assertEqual(count_characters("👨‍👩‍👧‍👦👍🏽🇯🇵か\u3099、。「」"), 8)
        self.assertEqual(count_characters("☕️A\u0301𠮷"), 3)
        self.assertEqual(count_characters("が"), count_characters("か\u3099"))
        text = STORY.replace("今", "👨‍👩‍👧‍👦", 1)
        row = extract(f"<p>{text}</p>")
        self.assertEqual((row["text"], row["charCount"], row["status"]), (text, 20, "success"))

    def test_punctuation_brackets_and_halfwidth_characters_count(self):
        text = "「ただいま」空き家の奥から母の声がした。"
        self.assertEqual(extract(f"<p>{text}</p>")["charCount"], 20)
        self.assertEqual(count_characters("ＡA、。!?「」 "), 9)

    def test_inline_html_and_entities_are_decoded_once(self):
        row = extract("<p>今日は<em>昨日の私が</em>置いた鍵で明日を開ける。</p>")
        self.assertEqual((row["text"], row["charCount"]), (STORY, 20))
        self.assertEqual(first_body_line("<p>A&amp;B&#x3002;</p>").text, "A&B。")
        self.assertEqual(first_body_line("<p>&lt;br&gt;&amp;amp;</p>").text, "<br>&amp;")

    def test_ruby_annotations_do_not_count_twice(self):
        row = extract("<p><ruby>今日<rp>(</rp><rt>きょう</rt><rp>)</rp></ruby>は昨日の私が置いた鍵で明日を開ける。</p>")
        self.assertEqual((row["text"], row["charCount"]), (STORY, 20))

    def test_note_ruby_notation_keeps_only_base_text(self):
        for marker in ("|", "｜"):
            body = STORY.replace("昨日", marker + "昨日《きのう》").replace("鍵", marker + "鍵《かぎ》")
            with self.subTest(marker=marker):
                row = extract(f"<p>{body}</p>")
                self.assertEqual((row["text"], row["charCount"], row["status"]), (STORY, 20, "success"))
        row = extract("<p>今日は昨日の私が置いた|<strong>鍵</strong>《かぎ》で明日を開ける。</p>")
        self.assertEqual((row["text"], row["charCount"], row["status"]), (STORY, 20, "success"))

    def test_note_ruby_notation_in_bounded_two_and_three_line_stories(self):
        cases = [
            (["雨の日の鳥達は賑やかだ。", "晩秋の道を|征《ゆ》く。"],
             ["雨の日の鳥達は賑やかだ。", "晩秋の道を征く。"]),
            (["|硬《カタ》！", "|方々《カタガタ》|硬《カタ》かった？", "|片肩《カタカタ》が、ただガタガタ。"],
             ["硬！", "方々硬かった？", "片肩が、ただガタガタ。"]),
        ]
        for raw, plain in cases:
            with self.subTest(lines=len(raw)):
                body = "<p>" + "<br>".join(raw) + "</p><p><br></p><p>あとがき</p>"
                row = extract(body)
                self.assertEqual((row["text"], row["charCount"], row["status"]), ("".join(plain), 20, "success"))
                self.assertEqual(row["sourceLines"], plain)

    def test_note_ruby_notation_does_not_normalize_base_graphemes(self):
        text = STORY.replace("鍵", "か\u3099")
        row = extract(f"<p>{STORY.replace('鍵', '|か' + chr(0x3099) + '《が》')}</p>")
        self.assertEqual((row["text"], row["charCount"]), (text, 20))

    def test_literal_brackets_incomplete_ruby_and_code_are_preserved(self):
        for text in ("鍵《かぎ》", "|鍵《》", "|鍵《かぎ", r"\|鍵《かぎ》"):
            with self.subTest(text=text):
                self.assertEqual(first_body_line(f"<p>{text}</p>").text, text)
        self.assertEqual(first_body_line("<pre><code>|鍵《かぎ》</code></pre>").text, "|鍵《かぎ》")

    def test_hidden_elements_and_scripts_are_not_body_text(self):
        row = extract(f"<script>説明</script><p hidden>説明</p><p style='display: none'>説明</p><p>{STORY}</p>")
        self.assertEqual((row["text"], row["status"]), (STORY, "success"))

    def test_caption_quote_list_and_embed_are_reviewed_without_skipping(self):
        for wrapper, kind in [("<figure><figcaption>{}</figcaption></figure>", "caption"),
                              ("<blockquote><p>{}</p></blockquote>", "quote"),
                              ("<ul><li>{}</li></ul>", "list"),
                              ('<figure embedded-service="note"><div>{}</div></figure>', "embed")]:
            with self.subTest(kind=kind):
                row = extract(wrapper.format(STORY) + "<p>後続の本文</p>")
                self.assertEqual((row["text"], row["status"]), (STORY, "pending"))
                self.assertIn("first_line_" + kind, row["reasonCodes"])

    def test_invisible_format_character_causes_review(self):
        row = extract(f"<p>{STORY[:-1]}\u200b</p>")
        self.assertEqual(row["status"], "pending")
        self.assertIn("invisible_characters", row["reasonCodes"])

    def test_removed_or_unknown_hashtag_is_pending(self):
        for tags in [None, [], [{"hashtag": {"name": "#20文字小説"}}]]:
            with self.subTest(tags=tags):
                row = extract(hashtag_notes=tags)
                self.assertEqual(row["status"], "pending")
                self.assertIn("hashtag_unverified", row["reasonCodes"])

    def test_paid_article_public_opening_is_allowed(self):
        for fields in [{"price": 100},
                       {"price": 100, "paywall": {"context": {"is_show_limited_pay_note_paywall": True}}}]:
            with self.subTest(fields=fields):
                row = extract(**fields)
                self.assertEqual((row["text"], row["charCount"], row["status"]), (STORY, 20, "success"))
        row = extract(body=123, price=100)
        self.assertEqual(row["reasonCodes"], ["body_unavailable"])

    def test_limited_or_non_text_article_stays_pending(self):
        for fields in [{"is_limited": True}, {"type": "ImageNote"}]:
            with self.subTest(fields=fields):
                row = extract(**fields)
                self.assertEqual(row["status"], "pending")
                self.assertIn("restricted_article", row["reasonCodes"])

    def test_free_article_paywall_configuration_is_not_itself_a_restriction(self):
        row = extract(paywall={"is_simple_paid_note": True,
                               "context": {"is_show_limited_pay_note_paywall": False}})
        self.assertEqual(row["status"], "success")

    def test_missing_metadata_does_not_become_success(self):
        row = extract(user={"urlname": "test_author"})
        self.assertEqual(row["status"], "pending")
        self.assertIn("metadata_incomplete", row["reasonCodes"])

    def test_invalid_payload_wrong_identity_and_draft_are_failures(self):
        for payload, reason in [(None, "invalid_payload"), ({"data": []}, "invalid_payload"),
                                (article(key="ndifferent"), "identity_mismatch"),
                                (article(status="draft"), "unpublished_article")]:
            with self.subTest(reason=reason):
                row = extract_article(SEED, payload, "20字小説")
                self.assertEqual((row["status"], row["reasonCodes"]), ("failed", [reason]))


class FakeClient(NoteClient):
    def __init__(self, articles=None, pages=None):
        self.articles = articles or {}
        self.pages = pages or {}
        self.calls = []

    def article(self, key):
        self.calls.append(key)
        value = self.articles.get(key, article())
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)

    def get(self, path):
        page = int(path.rsplit("=", 1)[-1])
        value = self.pages[page]
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)


def page(rows, next_page=None, last=True):
    return {"data": {"notes": rows, "next_page": next_page, "is_last_page": last}}


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / "results.json"
        self.log = Path(self.tmp.name) / "events.jsonl"

    def run_extract(self, client, **kwargs):
        return run_extraction(client, tag="20字小説", output=self.output,
                              log_path=self.log, delay=0, **kwargs)

    def events(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_duplicate_query_urls_and_repeated_runs_upsert_by_article_key(self):
        one = seed_from_url(SEED["url"] + "?from=share#top")
        client = FakeClient()
        result = self.run_extract(client, seeds=[SEED, one])
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["latestRun"]["duplicatesSkipped"], 1)
        self.assertEqual(client.calls, [SEED["key"]])
        first_seen = result["works"][0]["firstSeenAt"]
        client.articles[SEED["key"]] = article(f"<p>{STORY}！</p>")
        result = self.run_extract(client, seeds=[one])
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["works"][0]["status"], "pending")
        self.assertEqual(result["works"][0]["firstSeenAt"], first_seen)

    def test_article_request_failure_does_not_stop_later_articles(self):
        broken = seed_from_url("https://note.com/test_author/n/nb00000000002")
        client = FakeClient({broken["key"]: OSError("HTTP 404")})
        result = self.run_extract(client, seeds=[broken, SEED])
        self.assertEqual(result["summary"], {"total": 2, "success": 1, "pending": 0, "failed": 1, "candidates": 1})
        failed = next(row for row in result["works"] if row["key"] == broken["key"])
        self.assertEqual(failed["reasonCodes"], ["fetch_failed"])
        self.assertIn("404", failed["error"])
        self.assertEqual(len([event for event in self.events() if event["event"] == "article_checked"]), 2)

    def test_missing_body_does_not_stop_next_article(self):
        broken = seed_from_url("https://note.com/test_author/n/nb00000000002")
        broken_payload = article(key=broken["key"])
        broken_payload["data"]["body"] = None
        result = self.run_extract(FakeClient({broken["key"]: broken_payload}), seeds=[broken, SEED])
        self.assertEqual((result["summary"]["failed"], result["summary"]["success"]), (1, 1))

    def test_discovery_pagination_and_cross_page_duplicates(self):
        result = self.run_extract(FakeClient(pages={1: page([SEED], 2, False), 2: page([SEED])}))
        self.assertEqual(result["latestRun"]["scannedPages"], 2)
        self.assertEqual(result["latestRun"]["duplicatesSkipped"], 1)
        self.assertFalse(result["latestRun"]["truncated"])

    def test_page_limit_is_visible_as_partial_scan(self):
        result = self.run_extract(FakeClient(pages={1: page([SEED], 2, False)}), max_pages=1)
        self.assertEqual(result["latestRun"]["stopReason"], "max_pages")
        self.assertTrue(result["latestRun"]["truncated"])

    def test_article_limit_is_visible_as_partial_scan(self):
        another = seed_from_url("https://note.com/test_author/n/nb00000000002")
        result = self.run_extract(FakeClient(), seeds=[SEED, another], limit=1)
        self.assertEqual(result["latestRun"]["processed"], 1)
        self.assertEqual(result["latestRun"]["stopReason"], "limit")
        self.assertTrue(result["latestRun"]["truncated"])

    def test_discovery_error_preserves_previous_records_and_logs_reason(self):
        self.run_extract(FakeClient(), seeds=[SEED])
        result = self.run_extract(FakeClient(pages={1: OSError("HTTP 503")}))
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["latestRun"]["stopReason"], "discovery_error")
        self.assertIn("503", result["latestRun"]["error"])
        self.assertTrue(any(event["event"] == "discovery_error" for event in self.events()))

    def test_corrupt_existing_output_is_not_silently_replaced(self):
        self.output.write_text("corrupt", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_extract(FakeClient(), seeds=[SEED])
        self.assertEqual(self.output.read_text(), "corrupt")
        self.assertFalse(self.log.exists())

    def test_different_hashtag_or_count_rule_cannot_mix_with_existing_output(self):
        result = self.run_extract(FakeClient(), seeds=[SEED])
        for key, value in [("hashtag", "別企画"), ("countRule", "different")]:
            with self.subTest(key=key):
                changed = {**result, key: value}
                self.output.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    self.run_extract(FakeClient(), seeds=[SEED])

    def test_bad_discovery_row_does_not_stop_valid_row(self):
        result = self.run_extract(FakeClient(pages={1: page([None, {"url": 123}, SEED])}))
        self.assertEqual(result["summary"]["success"], 1)
        self.assertEqual(result["latestRun"]["invalidRows"], 2)

    def test_bad_input_row_is_written_to_log_and_valid_row_continues(self):
        result = self.run_extract(FakeClient(), seeds=[None, {"url": "https://invalid.example/"}, SEED])
        self.assertEqual(result["summary"]["success"], 1)
        self.assertEqual(result["latestRun"]["invalidRows"], 2)
        self.assertTrue(any(event["event"] == "invalid_input_row" for event in self.events()))

    def test_jst_window_is_inclusive_since_exclusive_until(self):
        rows = [{**SEED, "publishedAt": "2026-11-14T00:00:00+09:00"},
                {**SEED, "publishedAt": "2026-11-13T00:00:00+09:00"},
                {**SEED, "publishedAt": "2026-11-12T23:59:59+09:00"}]
        result = self.run_extract(FakeClient(pages={1: page(rows)}), since=parse_time("2026-11-13"), until=parse_time("2026-11-14"))
        self.assertEqual(result["latestRun"]["processed"], 1)
        self.assertEqual(result["latestRun"]["stopReason"], "since_boundary")

    def test_unknown_date_is_not_allowed_into_bounded_event(self):
        result = self.run_extract(FakeClient(pages={1: page([SEED])}), since=parse_time("2026-11-13"))
        self.assertEqual(result["summary"]["total"], 0)
        self.assertEqual(result["latestRun"]["invalidRows"], 1)

    def test_invalid_pagination_is_reported_without_losing_partial_results(self):
        result = self.run_extract(FakeClient(pages={1: page([SEED], 1, False)}))
        self.assertEqual(result["summary"]["success"], 1)
        self.assertEqual(result["latestRun"]["stopReason"], "discovery_error")

    def test_cli_uses_existing_work_list_shape_and_protects_site_data(self):
        input_path = Path(self.tmp.name) / "empty-works.json"
        input_path.write_text('{"version":1,"works":[]}')
        command = [sys.executable, str(ROOT / "scripts/extract-20char.py"), "--input", str(input_path),
                   "--output", str(self.output), "--log", str(self.log)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.output.read_text())["summary"]["total"], 0)
        result = subprocess.run(command + ["--output", str(ROOT / "data/works.json")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("data/", result.stderr)


class InputTests(unittest.TestCase):
    def test_url_canonicalization_and_untrusted_urls(self):
        self.assertEqual(seed_from_url(SEED["url"] + "/?x=1#fragment"), SEED)
        for url in ["https://evil.example/test_author/n/na00000000001", "http://note.com/test_author/n/na00000000001",
                    "https://note.com@evil.example/test_author/n/na00000000001", 123]:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    seed_from_url(url)

    def test_existing_site_work_entry_without_key_is_accepted(self):
        seed = seed_from_row({"url": SEED["url"], "handle": "test_author", "title": "記事"})
        self.assertEqual(seed["key"], SEED["key"])

    def test_hashtag_normalization_and_date_timezone(self):
        self.assertEqual(normalize_hashtag(" #20字小説 "), "20字小説")
        self.assertEqual(parse_time("2026-11-13").utcoffset().total_seconds(), 9 * 3600)
        self.assertEqual(parse_time("2026-11-13T11:00:00Z").tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
