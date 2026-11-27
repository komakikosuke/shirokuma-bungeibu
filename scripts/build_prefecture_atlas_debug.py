#!/usr/bin/env python3
"""Fetch Komaki's latest public articles into a separate preview-only feed."""
from __future__ import annotations

import argparse
import datetime as dt
from email.utils import parsedate_to_datetime
import html
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from sync_prefecture_atlas import NoteClient, ROOT, UTC, registered_tags, safe_image, write_atomic

CREATOR = "komaki_kousuke"
RSS_URL = "https://note.com/" + CREATOR + "/rss"
PURPOSE = "prefecture-atlas-preview"


def rss_seeds(xml_text):
    root = ET.fromstring(xml_text)
    found = {}
    for item in root.findall(".//item"):
        url = (item.findtext("link") or "").strip()
        parsed = urllib.parse.urlsplit(url)
        match = re.fullmatch(r"/" + CREATOR + r"/n/(n[A-Za-z0-9]+)/?", parsed.path)
        if parsed.scheme != "https" or parsed.netloc != "note.com" or not match:
            continue
        try:
            when = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (ValueError, TypeError):
            continue
        if when.tzinfo is None:
            continue
        found[match[1]] = (when, {"key": match[1], "handle": CREATOR})
    if not found:
        raise ValueError("RSSから公開記事を確認できません")
    return [seed for _, seed in sorted(found.values(), key=lambda row: row[0], reverse=True)]


def preview_article(seed, payload):
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or data.get("key") != seed["key"]:
        raise ValueError("デバッグ記事の記事キーが一致しません")
    user = data.get("user")
    if not isinstance(user, dict) or user.get("urlname") != CREATOR:
        raise ValueError("小牧幸助さん以外の記事はデバッグ表示しません")
    if (data.get("status") != "published" or data.get("is_draft") is True
            or data.get("is_reserved") is True or data.get("is_published") is False):
        raise ValueError("公開中の記事ではありません")
    title, name, published = data.get("name"), user.get("nickname"), data.get("publish_at")
    if not all(isinstance(value, str) and value.strip() for value in (title, name, published)):
        raise ValueError("デバッグ記事の表示情報が不足しています")
    when = dt.datetime.fromisoformat(published.replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise ValueError("記事の公開日時にタイムゾーンがありません")
    tags = registered_tags(data) if isinstance(data.get("hashtag_notes"), list) else []
    try:
        paid = float(data.get("price") or 0) > 0
    except (ValueError, TypeError):
        paid = False
    return {
        "key": seed["key"],
        "url": "https://note.com/" + CREATOR + "/n/" + seed["key"],
        "title": html.unescape(title).strip()[:500],
        "publishedAt": when.astimezone(UTC).isoformat(timespec="seconds"),
        "author": {
            "handle": CREATOR,
            "name": html.unescape(name).strip()[:150],
            "avatarUrl": safe_image(user.get("user_profile_image_path")),
        },
        "imageUrl": safe_image(data.get("eyecatch")),
        "tags": tags,
        "isPaid": data.get("is_paid") is True or paid,
    }


def build_debug_feed(xml_text, client, limit=3):
    articles = [preview_article(seed, client.article(seed["key"])) for seed in rss_seeds(xml_text)[:limit]]
    articles.sort(key=lambda article: dt.datetime.fromisoformat(article["publishedAt"]), reverse=True)
    return {
        "version": 1,
        "purpose": PURPOSE,
        "creator": CREATOR,
        "generatedAt": dt.datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": RSS_URL,
        "articles": articles,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/prefecture-atlas-debug.json")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        parser.error("limit must be between 1 and 10")
    if args.output.resolve() == (ROOT / "data/prefecture-atlas.json").resolve():
        parser.error("通常の掲載データはデバッグ出力先に指定できません")
    request = urllib.request.Request(RSS_URL, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ShirokumaCreatorAtlas/1.0)",
        "Accept": "application/rss+xml, application/xml, text/xml",
    })
    with urllib.request.urlopen(request, timeout=25) as response:
        xml_text = response.read()
    document = build_debug_feed(xml_text, NoteClient(), limit=args.limit)
    write_atomic(args.output, document)
    print(json.dumps({"purpose": PURPOSE, "articles": [{"title": article["title"], "publishedAt": article["publishedAt"]} for article in document["articles"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
