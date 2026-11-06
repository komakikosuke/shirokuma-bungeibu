#!/usr/bin/env python3
"""Synchronize the newest weekly Shirokuma writing prompt from the author's note RSS.

RSS is the supported public article feed. Creator contents API is a fallback.
Only update JSON on a validated newer matching article; never guess an assignment.
"""
import datetime as dt
import email.utils
import json
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

AUTHOR = "komaki_kousuke"
RSS = f"https://note.com/{AUTHOR}/rss"
API = f"https://note.com/api/v2/creators/{AUTHOR}/contents"
FILE = pathlib.Path("data/weekly-topic.json")
MATCH = re.compile(r"^お題で書きはじめるnote企画\s*[｜|]\s*「([^」]+)」")
LINK = re.compile(rf"^https://note\.com/{AUTHOR}/n/n[a-zA-Z0-9]+/?$")
TZ = dt.timezone.utc


def request(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ShirokumaWeeklyTopic/1.0; public feed)",
        "Accept": "application/rss+xml, application/xml, application/json;q=0.9, */*;q=0.5",
        "Referer": f"https://note.com/{AUTHOR}",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as res:
        return res.read()


def date_iso(value):
    if not value:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ).isoformat(timespec="seconds").replace("+00:00", "Z")


def candidate(title, url, published, source):
    title = (title or "").strip()
    match = MATCH.search(title)
    if not match or not LINK.fullmatch(url or "") or not published:
        return None
    topic = match.group(1).strip()
    if not topic or len(topic) > 80:
        return None
    return {
        "topic": topic,
        "title": title,
        "url": url,
        "publishedAt": date_iso(published),
        "source": source,
    }


def rss_candidates():
    root = ET.fromstring(request(RSS))
    results = []
    for item in root.findall(".//channel/item"):
        try:
            row = candidate(
                item.findtext("title"),
                (item.findtext("link") or "").strip(),
                item.findtext("pubDate"),
                "note RSS",
            )
            if row:
                results.append(row)
        except (ValueError, TypeError):
            continue
    return results


def api_candidates():
    results = []
    for page in range(1, 6):
        url = API + "?" + urllib.parse.urlencode({"kind": "note", "page": page})
        payload = json.loads(request(url).decode("utf-8"))
        block = payload.get("data") or {}
        notes = block.get("contents") or []
        if not isinstance(notes, list):
            raise ValueError("unexpected creator API response")
        for note in notes:
            if not isinstance(note, dict):
                continue
            key = note.get("key") or ""
            if not re.fullmatch(r"[a-zA-Z0-9]+", str(key)):
                continue
            try:
                row = candidate(
                    note.get("name") or note.get("title"),
                    f"https://note.com/{AUTHOR}/n/{key}",
                    note.get("publishAt") or note.get("publish_at"),
                    "note creator API",
                )
                if row:
                    results.append(row)
            except (ValueError, TypeError):
                continue
        if block.get("isLastPage") or not notes:
            break
    return results


def main():
    found = []
    failures = []
    try:
        found = rss_candidates()
    except Exception as exc:
        failures.append(f"RSS: {exc}")
    if not found:
        try:
            found = api_candidates()
        except Exception as exc:
            failures.append(f"API: {exc}")
    if not found:
        raise RuntimeError("Could not find a recent weekly prompt. " + "; ".join(failures))

    latest = max(found, key=lambda x: (x["publishedAt"], x["url"]))
    old = None
    if FILE.exists():
        try:
            old = json.loads(FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    if isinstance(old, dict):
        if old.get("publishedAt", "") > latest["publishedAt"]:
            print("Fetched feed is older than existing latest prompt; keeping existing JSON.")
            return
        if old.get("publishedAt") == latest["publishedAt"] and old.get("url") == latest["url"]:
            print(f"Unchanged prompt: {latest['topic']}")
            return

    latest["updatedAt"] = dt.datetime.now(TZ).isoformat(timespec="seconds").replace("+00:00", "Z")
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(latest, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Latest weekly topic: {latest['topic']} / {latest['url']} / {latest['publishedAt']}")


if __name__ == "__main__":
    main()
