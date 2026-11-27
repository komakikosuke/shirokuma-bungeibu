#!/usr/bin/env python3
"""Collect public note metadata when BOTH required hashtags are registered.

Body text, genre, length, price, and place of birth do not affect eligibility.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TAG = "記事で塗る日本地図"
HANDLE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
KEY = re.compile(r"^n[A-Za-z0-9]+$")
UTC = dt.timezone.utc


def normalize_tag(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().removeprefix("#")


def prefecture_tag_names(name: str) -> set[str]:
    # 北海道 is already the commonly used place name; 北海 is a different tag.
    return {name, name[:-1]} if name.endswith(("都", "府", "県")) else {name}


def seed_from_row(row):
    if not isinstance(row, dict) or not KEY.fullmatch(str(row.get("key", ""))):
        raise ValueError("記事一覧の記事キーを確認できません")
    author = row.get("user") or row.get("author") or {}
    handle = (author.get("urlname") or author.get("handle")) if isinstance(author, dict) else None
    if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
        raise ValueError("記事一覧のクリエイターIDを確認できません")
    return {"key": row["key"], "handle": handle}


def registered_tags(data):
    rows = data.get("hashtag_notes")
    if not isinstance(rows, list):
        raise ValueError("記事の登録ハッシュタグを確認できません")
    tags = set()
    for row in rows:
        raw = row.get("hashtag") if isinstance(row, dict) else None
        name = raw.get("name") if isinstance(raw, dict) else None
        if not isinstance(name, str):
            raise ValueError("登録ハッシュタグの形式が変わっています")
        tags.add(normalize_tag(name))
    return sorted(tags)


def safe_image(value):
    if isinstance(value, dict):
        value = value.get("original_url") or value.get("url")
    if not isinstance(value, str):
        return ""
    parsed = urllib.parse.urlsplit(value)
    host = parsed.hostname or ""
    allowed = ("st-note.com", "note.com", "note.mu", "amazonaws.com")
    if (parsed.scheme == "https" and not parsed.username and not parsed.password
            and any(host == suffix or host.endswith("." + suffix) for suffix in allowed)):
        return value
    return ""


def parse_article(seed, payload, prefectures):
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or data.get("key") != seed["key"]:
        raise ValueError("記事の取得結果を検証できません")
    if not isinstance(data.get("status"), str):
        raise ValueError("記事の公開状態を確認できません")
    if (data["status"] != "published" or data.get("is_draft") is True
            or data.get("is_published") is False or data.get("is_reserved") is True):
        return None
    tags = registered_tags(data)
    codes = [pref["code"] for pref in prefectures if prefecture_tag_names(pref["name"]).intersection(tags)]
    if TAG not in tags or not codes:
        return None
    user = data.get("user")
    if not isinstance(user, dict) or not isinstance(user.get("urlname"), str) or not HANDLE.fullmatch(user["urlname"]):
        raise ValueError("記事のクリエイターIDを確認できません")
    title, name, published = data.get("name"), user.get("nickname"), data.get("publish_at")
    if not all(isinstance(value, str) and value.strip() for value in (title, name, published)):
        raise ValueError("記事の表示情報が不足しています")
    try:
        timestamp = dt.datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("記事の公開日時を確認できません") from exc
    if timestamp.tzinfo is None:
        raise ValueError("記事の公開日時にタイムゾーンがありません")
    price = data.get("price", 0)
    try:
        is_paid = float(price or 0) > 0
    except (ValueError, TypeError):
        is_paid = False
    handle = user["urlname"]
    return {
        "key": seed["key"],
        "url": "https://note.com/" + handle + "/n/" + seed["key"],
        "title": html.unescape(title).strip()[:500],
        "publishedAt": timestamp.isoformat(timespec="seconds"),
        "author": {
            "handle": handle,
            "name": html.unescape(name).strip()[:150],
            "avatarUrl": safe_image(user.get("user_profile_image_path")),
        },
        "imageUrl": safe_image(data.get("eyecatch")),
        "tags": tags,
        "prefectures": codes,
        "isPaid": data.get("is_paid") is True or is_paid,
    }


class NoteClient:
    def __init__(self, delay=0.25):
        self.delay = delay
        self.last_request = 0.0

    def get(self, path):
        request = urllib.request.Request("https://note.com" + path, headers={
            "User-Agent": "Mozilla/5.0 (compatible; ShirokumaCreatorAtlas/1.0)",
            "Accept": "application/json",
            "Referer": "https://note.com/",
        })
        for attempt in range(3):
            pause = self.delay - (time.monotonic() - self.last_request)
            if pause > 0:
                time.sleep(pause)
            self.last_request = time.monotonic()
            try:
                with urllib.request.urlopen(request, timeout=25) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise
                retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
                wait = min(30, int(retry_after)) if retry_after.isdigit() else 2 ** (attempt + 1)
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise
                wait = 2 ** (attempt + 1)
            time.sleep(wait)
        raise RuntimeError("noteへの接続に失敗しました")

    def article(self, key):
        return self.get("/api/v3/notes/" + key)

    def discover(self, max_pages=200):
        seeds, page, scanned = {}, 1, set()
        tag = urllib.parse.quote(TAG, safe="")
        for _ in range(max_pages):
            if page in scanned:
                raise ValueError("記事一覧のページが循環しています")
            scanned.add(page)
            try:
                payload = self.get("/api/v3/hashtags/" + tag + "/notes?order=new&page=" + str(page))
            except urllib.error.HTTPError as exc:
                if exc.code == 404 and page == 1:
                    return [], 1
                raise
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict) or not isinstance(data.get("notes"), list):
                raise ValueError("ハッシュタグの記事一覧形式が変わっています")
            for row in data["notes"]:
                seed = seed_from_row(row)
                seeds[seed["key"]] = seed
            next_page = data.get("next_page")
            if not data["notes"] or data.get("is_last_page") is True or next_page is None:
                return list(seeds.values()), len(scanned)
            if isinstance(next_page, str) and next_page.isdigit():
                next_page = int(next_page)
            if type(next_page) is not int or next_page <= page:
                raise ValueError("記事一覧の次のページを確認できません")
            page = next_page
        raise RuntimeError("記事一覧の走査上限に達しました。前回の掲載データは保持します")


def sync_atlas(client, previous, prefectures, now=None, max_pages=200):
    if previous.get("version") != 1 or previous.get("tag") != TAG or not isinstance(previous.get("articles"), list):
        raise ValueError("前回の図鑑データの形式が違います")
    seeds, page_count = client.discover(max_pages=max_pages)
    queue = {seed["key"]: seed for seed in seeds}
    old = {}
    for article in previous["articles"]:
        seed = seed_from_row(article)
        old[seed["key"]] = article
        queue.setdefault(seed["key"], seed)
    result, failed, checked = {}, [], 0
    for key, seed in queue.items():
        try:
            article = parse_article(seed, client.article(key), prefectures)
            checked += 1
            if article is not None:
                result[key] = article
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410):
                checked += 1
                continue
            failed.append({"key": key, "reason": "HTTP " + str(exc.code)})
            if key in old:
                result[key] = old[key]
        except (ValueError, TypeError, KeyError, urllib.error.URLError, TimeoutError) as exc:
            failed.append({"key": key, "reason": str(exc)})
            if key in old:
                result[key] = old[key]
    if failed and not checked:
        raise RuntimeError("記事の確認にすべて失敗しました。前回の掲載データは保持します")
    timestamp = (now or dt.datetime.now(UTC)).astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    articles = sorted(result.values(), key=lambda article: (article["publishedAt"], article["key"]), reverse=True)
    document = {
        "version": 1,
        "tag": TAG,
        "generatedAt": timestamp,
        "articles": articles,
        "sync": {
            "status": "partial" if failed else "ok",
            "scannedPages": page_count,
            "discoveredArticles": len(seeds),
            "checkedArticles": checked,
            "failedArticles": len(failed),
        },
    }
    return document, failed


HISTORY_START = "2026-11-30T15:00:00Z"  # December 1, 00:00 JST


def record_history(previous, document, prefectures):
    """Keep successful collection snapshots; never infer history from publication dates."""
    history = previous.get("history", [])
    if not isinstance(history, list):
        raise ValueError("地図の履歴データの形式が違います")
    codes = {pref["code"] for pref in prefectures}
    last = None
    for frame in history:
        if not isinstance(frame, dict) or set(frame.get("counts", {})) != codes:
            raise ValueError("地図の履歴データの形式が違います")
        at = frame.get("at", "")
        try:
            moment = dt.datetime.fromisoformat(at.replace("Z", "+00:00"))
        except (TypeError, ValueError, AttributeError):
            raise ValueError("地図の履歴日時が不正です") from None
        if moment.tzinfo is None or (last is not None and moment <= last):
            raise ValueError("地図の履歴日時が不正です")
        if any(type(n) is not int or n < 0 for n in frame["counts"].values()):
            raise ValueError("地図の履歴件数が不正です")
        last = moment
    frames = list(history)
    at = document["generatedAt"]
    if document["sync"]["status"] == "ok" and at >= HISTORY_START:
        counts = {code: set() for code in sorted(codes)}
        for article in document["articles"]:
            for code in article["prefectures"]:
                if code in counts:
                    counts[code].add(article["key"])
        if not frames:
            frames.append({"at": HISTORY_START, "counts": {code: 0 for code in sorted(codes)}})
        if at > frames[-1]["at"]:
            frames.append({"at": at, "counts": {code: len(keys) for code, keys in counts.items()}})
    document["history"] = frames


def write_atomic(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/prefecture-atlas.json")
    parser.add_argument("--map", type=Path, default=ROOT / "prefectures/map.json")
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--delay", type=float, default=0.25)
    args = parser.parse_args()
    if args.max_pages < 1 or args.delay < 0:
        parser.error("max-pages must be positive and delay must not be negative")
    prefectures = json.loads(args.map.read_text(encoding="utf-8"))["prefectures"]
    if len(prefectures) != 47 or len({pref["name"] for pref in prefectures}) != 47:
        raise ValueError("47都道府県の対応表を確認できません")
    previous = json.loads(args.output.read_text(encoding="utf-8")) if args.output.exists() else {"version": 1, "tag": TAG, "articles": []}
    document, failures = sync_atlas(NoteClient(args.delay), previous, prefectures, max_pages=args.max_pages)
    record_history(previous, document, prefectures)
    write_atomic(args.output, document)
    print(json.dumps({"articles": len(document["articles"]), **document["sync"]}, ensure_ascii=False))
    for failure in failures:
        print("確認を再試行する記事: " + failure["key"] + " (" + failure["reason"] + ")")


if __name__ == "__main__":
    main()
