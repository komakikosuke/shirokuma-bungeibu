"""Independent, review-only extraction of the first text line in public note bodies."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import time
import unicodedata
from urllib.parse import quote, urlsplit

import regex

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))
COUNT_RULE = "extended-grapheme-clusters:regex-2024.11.6:unicode-16.0"
GRAPHEMES = regex.compile(r"\X")


def _existing_collector():
    # Import definitions only: the legacy scan() is protected by its __main__ guard.
    # This reuses its public API requests, timeout/retry policy and URL validation
    # without changing that collector or invoking its file-writing scan().
    spec = importlib.util.spec_from_file_location(
        "shirokuma_note_collector", ROOT / "scripts/sync-candidates.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LEGACY = _existing_collector()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def count_characters(text):
    """Count extended grapheme clusters; preserve the author's original text."""
    return len(GRAPHEMES.findall(text))


def normalize_hashtag(value):
    tag = value.strip().removeprefix("#").removeprefix("＃")
    if not tag or len(tag) > 100 or any(c.isspace() or c in "#＃/" for c in tag):
        raise ValueError("ハッシュタグは空白や / を含めず指定してください")
    return tag


def parse_time(value):
    """CLI dates and naive times use JST; offset-bearing dates retain their instant."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=JST)


@dataclass(frozen=True)
class FirstLine:
    text: str
    kinds: tuple[str, ...]


class BodyParser(HTMLParser):
    """Respect paragraphs and br, without combining separate lines or using alt text.

    Semantic containers are retained as review signals, never skipped in search
    of a later line that happens to have the desired length.
    """

    BLOCKS = set("p div section article h1 h2 h3 h4 h5 h6 ul ol li blockquote pre figure figcaption table tr td th hr".split())
    IGNORE = set("script style noscript template head title rt rp".split())
    VOID = set("area base br col embed hr img input link meta param source track wbr".split())

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = []
        self.kinds = set()
        self.first = None

    def _flush(self):
        text = "".join(self.parts).strip()
        if self.first is None and text:
            self.first = FirstLine(text, tuple(sorted(self.kinds)))
        self.parts.clear()
        self.kinds.clear()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.BLOCKS or tag == "br":
            self._flush()
        style = re.sub(r"\s+", "", attrs.get("style") or "").lower()
        ignore = (tag in self.IGNORE or "hidden" in attrs
                  or attrs.get("aria-hidden") == "true"
                  or "display:none" in style or "visibility:hidden" in style)
        kinds = set()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            kinds.add("heading")
        for kind, tags in {
            "quote": {"blockquote"}, "list": {"li"}, "caption": {"figcaption"},
            "code": {"pre", "code"}, "table": {"table"}, "link": {"a"},
        }.items():
            if tag in tags:
                kinds.add(kind)
        if (tag == "iframe" or "embedded-service" in attrs
                or "embedded-content-key" in attrs):
            kinds.add("embed")
        if tag not in self.VOID:
            self.stack.append((tag, ignore, kinds))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self.BLOCKS:
            self._flush()
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.first is not None or any(frame[1] for frame in self.stack):
            return
        kinds = set().union(*(frame[2] for frame in self.stack)) if self.stack else set()
        # Raw newlines also delimit text lines; note normally represents them as br.
        pieces = data.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for i, piece in enumerate(pieces):
            if i:
                self._flush()
            if self.first is not None:
                break
            self.parts.append(piece)
            if piece.strip():
                self.kinds.update(kinds)

    def result(self):
        self.close()
        self._flush()
        return self.first


def first_body_line(body):
    parser = BodyParser()
    parser.feed(body)
    return parser.result()


def seed_from_url(url):
    if not isinstance(url, str):
        raise ValueError("記事URLが文字列ではありません")
    parsed = urlsplit(url)
    match = re.fullmatch(r"/([a-zA-Z0-9_-]+)/n/(n[a-zA-Z0-9]+)/?", parsed.path)
    if (parsed.scheme != "https" or parsed.netloc != "note.com" or not match
            or not LEGACY.is_handle(match[1]) or not LEGACY.is_key(match[2])):
        raise ValueError("note.com の記事URLを指定してください: " + str(url))
    return {"key": match[2], "handle": match[1],
            "url": LEGACY.canonical_note_url(match[1], match[2])}


def seed_from_row(row):
    if not isinstance(row, dict):
        raise ValueError("記事一覧の要素がオブジェクトではありません")
    if row.get("url"):
        seed = seed_from_url(row["url"])
        if row.get("key") and row["key"] != seed["key"]:
            raise ValueError("記事URLと記事キーが一致しません")
    else:
        user = row.get("user") if isinstance(row.get("user"), dict) else {}
        handle = row.get("handle") or user.get("urlname")
        key = row.get("key")
        if not LEGACY.is_handle(handle) or not LEGACY.is_key(key) or not key.startswith("n"):
            raise ValueError("記事キーまたは投稿者note IDが不正です")
        seed = {"key": key, "handle": handle, "url": LEGACY.canonical_note_url(handle, key)}
    user = row.get("user") if isinstance(row.get("user"), dict) else {}
    for dest, value in {
        "title": row.get("title") or row.get("name"),
        "authorName": row.get("authorName") or user.get("nickname"),
        "publishedAt": row.get("publishedAt") or row.get("publish_at"),
    }.items():
        seed[dest] = value if isinstance(value, str) else ""
    return seed


class NoteClient:
    def get(self, path):
        return LEGACY.get(path)

    def article(self, key):
        return self.get(f"/api/v3/notes/{key}")

    def discover(self, tag, max_pages, since, until, progress, emit):
        page = 1
        for _ in range(max_pages):
            payload = self.get(f"/api/v3/hashtags/{quote(tag, safe='')}/notes?order=new&page={page}")
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict) or not isinstance(data.get("notes"), list):
                raise ValueError("ハッシュタグAPIの記事一覧形式が不正です")
            progress["scannedPages"] += 1
            emit("discovery_page", page=page, count=len(data["notes"]))
            for row in data["notes"]:
                try:
                    seed = seed_from_row(row)
                except (ValueError, TypeError) as exc:
                    progress["invalidRows"] += 1
                    emit("invalid_discovery_row", page=page, reason=str(exc))
                    continue
                try:
                    published = parse_time(seed["publishedAt"])
                except ValueError:
                    published = None
                if (since or until) and published is None:
                    # Unknown dates must not slip into a bounded event's results.
                    progress["invalidRows"] += 1
                    emit("invalid_discovery_row", url=seed["url"], reason="期間指定中に投稿日時を検証できません")
                    continue
                if since and published < since:
                    progress.update(stopReason="since_boundary", truncated=False)
                    return
                if until and published >= until:
                    continue
                yield seed
            next_page = data.get("next_page")
            if data.get("is_last_page") is True or not data["notes"]:
                progress.update(stopReason="last_page", truncated=False)
                return
            if type(next_page) is not int or next_page <= page:
                raise ValueError("ハッシュタグAPIの次ページが不明または循環しています")
            page = next_page
        progress.update(stopReason="max_pages", truncated=True)


REASONS = {
    "fetch_failed": "記事本文の取得に失敗しました",
    "invalid_payload": "記事APIの応答形式が不正です",
    "identity_mismatch": "取得した記事キーが要求と一致しません",
    "body_unavailable": "記事本文を取得できませんでした（一覧の抜粋では代用しません）",
    "empty_body": "本文に空でないテキスト行がありません",
    "unpublished_article": "公開済みの記事であることを確認できません",
    "metadata_incomplete": "記事タイトル・投稿者・投稿日時の一部を検証できません",
    "hashtag_unverified": "指定ハッシュタグを記事のタグ情報で確認できません",
    "restricted_article": "有料・限定公開などの記事のため確認が必要です",
    "outside_range": "一行目が抽出許容範囲の19〜21字に収まりません",
    "non_exact_length": "19字または21字です。正式ルールの20字ではありません",
    "explanatory_first_line": "一行目が説明・案内文の可能性があります",
    "first_line_matches_title": "一行目が記事タイトルと一致しています",
    "invisible_characters": "一行目に不可視文字または制御文字を含みます",
}
for _kind, _label in {
    "heading": "見出し", "quote": "引用", "list": "箇条書き", "caption": "画像の説明",
    "code": "コード", "table": "表", "link": "リンク", "embed": "埋め込み",
}.items():
    REASONS["first_line_" + _kind] = f"一行目が{_label}のため作品か確認が必要です"

INTRO = re.compile(
    r"^(?:[#＃]|https?://|こんにちは|はじめまして|募集要項|参加ルール|投稿ルール|"
    r"(?:今回|この記事)[はので]|(?:解説|説明|あとがき|まえがき|お題|タイトル)[:：]|"
    r"(?:これは|こちらは).{0,8}(?:20字|小説|作品|説明)|"
    r"[【「『]?(?:20|二十)字小説(?:[】」』:：]|について|の説明|に挑戦|を書|です))"
)


def empty_record(seed):
    return {
        "key": seed["key"], "url": seed["url"], "title": seed.get("title", ""),
        "authorName": seed.get("authorName", ""), "handle": seed["handle"],
        "publishedAt": seed.get("publishedAt", ""), "text": None, "charCount": None,
        "status": "failed", "reasonCodes": [], "reason": "", "isCandidate": False,
        "exactly20": False, "reviewRequired": True, "publicationStatus": "unreviewed",
        "firstLineKinds": [], "bodySource": "note API v3 data.body", "checkedAt": now_iso(),
    }


def explain(record, codes, status):
    record.update(status=status, reasonCodes=codes, reason=" / ".join(REASONS[c] for c in codes))
    return record


def extract_article(seed, payload, tag):
    record = empty_record(seed)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return explain(record, ["invalid_payload"], "failed")
    if data.get("key") != seed["key"]:
        return explain(record, ["identity_mismatch"], "failed")
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    codes = []
    if LEGACY.is_handle(user.get("urlname")):
        record["handle"] = user["urlname"]
        record["url"] = LEGACY.canonical_note_url(user["urlname"], seed["key"])
    for dest, value in {
        "title": data.get("name"), "authorName": user.get("nickname"),
        "publishedAt": data.get("publish_at"),
    }.items():
        if isinstance(value, str) and value.strip():
            record[dest] = value
        else:
            codes.append("metadata_incomplete")
    try:
        published = datetime.fromisoformat(record["publishedAt"].replace("Z", "+00:00"))
        if published.tzinfo is None:
            codes.append("metadata_incomplete")
    except (ValueError, TypeError):
        codes.append("metadata_incomplete")
    if not LEGACY.is_handle(user.get("urlname")):
        codes.append("metadata_incomplete")
    if (data.get("status") != "published" or data.get("is_draft") is True
            or data.get("is_published") is False or data.get("is_reserved") is True):
        return explain(record, ["unpublished_article"], "failed")
    tags = data.get("hashtag_notes")
    names = set()
    if isinstance(tags, list):
        for item in tags:
            raw = item.get("hashtag") if isinstance(item, dict) else None
            if isinstance(raw, dict) and isinstance(raw.get("name"), str):
                names.add(raw["name"].removeprefix("#"))
    if tag not in names:
        codes.append("hashtag_unverified")
    # Free articles also return a nonempty paywall *configuration* object.
    # Only an explicit restriction signal should make that a review reason.
    paywall = data.get("paywall") if isinstance(data.get("paywall"), dict) else {}
    context = paywall.get("context") if isinstance(paywall.get("context"), dict) else {}
    if (data.get("type") != "TextNote" or data.get("is_limited") is True
            or data.get("price", 0) != 0 or context.get("is_show_limited_pay_note_paywall") is True):
        codes.append("restricted_article")
    body = data.get("body")
    if not isinstance(body, str):
        return explain(record, ["body_unavailable"], "failed")
    line = first_body_line(body)
    if line is None:
        return explain(record, ["empty_body"], "failed")
    size = count_characters(line.text)
    record.update(text=line.text, charCount=size, isCandidate=19 <= size <= 21,
                  exactly20=size == 20, firstLineKinds=list(line.kinds))
    if not record["isCandidate"]:
        codes.append("outside_range")
    elif size != 20:
        codes.append("non_exact_length")
    codes.extend("first_line_" + kind for kind in line.kinds)
    if INTRO.search(unicodedata.normalize("NFKC", line.text)):
        codes.append("explanatory_first_line")
    if line.text == record["title"]:
        codes.append("first_line_matches_title")
    if any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} and c != "\u200d" for c in line.text):
        codes.append("invisible_characters")
    codes = list(dict.fromkeys(codes))
    if not record["isCandidate"]:
        return explain(record, codes, "failed")
    if codes:
        return explain(record, codes, "pending")
    record.update(status="success", reason="本文の最初の空でない一行から20字を抽出しました（掲載未承認）")
    return record


def summary(records):
    counts = Counter(row["status"] for row in records)
    return {"total": len(records), **{s: counts[s] for s in ("success", "pending", "failed")},
            "candidates": sum(bool(row["isCandidate"]) for row in records)}


def load_records(path, tag):
    if not path.exists():
        return {}
    old = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(old, dict) or old.get("version") != 1 or old.get("hashtag") != tag
            or not isinstance(old.get("works"), list) or old.get("countRule") != COUNT_RULE):
        raise ValueError("既存の出力形式・ハッシュタグ・文字数規則が一致しません。別の出力先を指定してください")
    records = {}
    for record in old["works"]:
        if (not isinstance(record, dict) or not LEGACY.is_key(record.get("key"))
                or record.get("status") not in {"success", "pending", "failed"}
                or "isCandidate" not in record or record["key"] in records):
            raise ValueError("既存の出力データが不正または重複しています。上書きを中止しました")
        seed = seed_from_url(record.get("url", ""))
        if seed["key"] != record["key"]:
            raise ValueError("既存の出力データの記事キーとURLが一致しません")
        records[record["key"]] = record
    return records


def write_json_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temp_path = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def run_extraction(client, *, tag, output, log_path, max_pages=5, limit=100,
                   since=None, until=None, seeds=None, delay=0.2):
    """Checkpoint each article and upsert by immutable note key across invocations."""
    records = load_records(output, tag)  # Fail before writing if an existing file is corrupt.
    progress = {"startedAt": now_iso(), "completedAt": None,
                "source": "hashtag" if seeds is None else "input",
                "since": since.isoformat() if since else None,
                "until": until.isoformat() if until else None,
                "scannedPages": 0, "processed": 0, "duplicatesSkipped": 0,
                "invalidRows": 0, "stopReason": "running", "truncated": None}
    checked = []
    seen = set()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        def emit(event, **values):
            json.dump({"at": now_iso(), "event": event, **values}, log, ensure_ascii=False)
            log.write("\n")
            log.flush()

        def save():
            works = sorted(records.values(), key=lambda row: (row.get("publishedAt", ""), row["key"]), reverse=True)
            document = {"version": 1, "hashtag": tag, "countRule": COUNT_RULE,
                        "generatedAt": now_iso(), "summary": summary(works),
                        "latestRun": {**progress, "summary": summary(checked)}, "works": works}
            write_json_atomic(output, document)
            return document

        emit("run_started", hashtag=tag, source=progress["source"])
        iterable = client.discover(tag, max_pages, since, until, progress, emit) if seeds is None else seeds
        try:
            for raw_seed in iterable:
                try:
                    seed = seed_from_row(raw_seed)
                except (ValueError, TypeError) as exc:
                    progress["invalidRows"] += 1
                    emit("invalid_input_row", reason=str(exc))
                    continue
                if seed["key"] in seen:
                    progress["duplicatesSkipped"] += 1
                    emit("duplicate_skipped", key=seed["key"], url=seed["url"])
                    continue
                if progress["processed"] >= limit:
                    progress.update(stopReason="limit", truncated=True)
                    break
                seen.add(seed["key"])
                try:
                    record = extract_article(seed, client.article(seed["key"]), tag)
                except Exception as exc:
                    record = explain(empty_record(seed), ["fetch_failed"], "failed")
                    record["error"] = f"{type(exc).__name__}: {exc}"[:500]
                record["firstSeenAt"] = records.get(seed["key"], {}).get("firstSeenAt", record["checkedAt"])
                records[seed["key"]] = record
                checked.append(record)
                progress["processed"] += 1
                emit("article_checked", key=record["key"], url=record["url"], status=record["status"],
                     charCount=record["charCount"], reasonCodes=record["reasonCodes"], reason=record["reason"],
                     error=record.get("error"))
                save()
                if delay:
                    time.sleep(delay)
            else:
                if seeds is not None:
                    progress.update(stopReason="input_exhausted", truncated=False)
        except Exception as exc:
            progress.update(stopReason="discovery_error", truncated=True,
                            error=f"{type(exc).__name__}: {exc}"[:500])
            emit("discovery_error", reason=progress["error"])
        progress["completedAt"] = now_iso()
        result = save()
        emit("run_completed", **progress, summary=summary(checked))
    return result
