#!/usr/bin/env python3
"""Build a public, read-only list of featured articles eligible for note magazine sync.

No note login or write operation happens here. Magazine sync must separately
check actual membership before adding an article.
"""
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
JST = ZoneInfo("Asia/Tokyo")
MAGAZINE_URL = "https://note.com/komaki_kousuke/m/mc02c43cae693"


def load(name, default):
    try:
        value = json.loads((DATA / name).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except (OSError, ValueError):
        return default


def week_start(item):
    explicit = item.get("weekStart")
    if isinstance(explicit, str) and len(explicit) == 10:
        try:
            return dt.date.fromisoformat(explicit).isoformat()
        except ValueError:
            pass
    timestamp = item.get("firstCommentAt", "")
    try:
        value = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(JST)
    except (ValueError, TypeError, AttributeError):
        return None
    start = (value - dt.timedelta(days=(value.weekday() - 3) % 7)).replace(
        hour=20, minute=0, second=0, microsecond=0
    )
    if value < start:
        start -= dt.timedelta(days=7)
    return start.date().isoformat()


def eligible(item):
    if not isinstance(item, dict):
        return False
    url = item.get("url")
    handle = item.get("handle")
    return (
        isinstance(url, str)
        and url.startswith("https://note.com/")
        and "/n/" in url
        and isinstance(handle, str)
        and bool(handle)
        and bool(week_start(item))
    )


def main():
    published = load("works.json", {}).get("works", [])
    candidates = load("candidates.json", {}).get("works", [])
    decisions = load("admin-decisions.json", {}).get("decisions", {})
    if not isinstance(decisions, dict):
        decisions = {}

    # Match the homepage rule: earliest first-comment opportunity per author/week.
    by_week = {}
    for item in [*published, *candidates]:
        if not eligible(item):
            continue
        period = week_start(item)
        key = period + "|" + item["handle"]
        previous = by_week.get(key)
        if previous is None or item.get("firstCommentAt", "") < previous.get("firstCommentAt", ""):
            by_week[key] = item

    featured = []
    for key, item in by_week.items():
        old_key = str(item.get("month", "")) + "|" + item["handle"]
        choice = decisions.get(key, {})
        if not isinstance(choice, dict) or not choice.get("status"):
            choice = decisions.get(old_key, {})
        if isinstance(choice, dict) and choice.get("status") in ("draft", "excluded"):
            continue
        featured.append(item)

    # A note article can be featured in different weeks; magazine should add it ONCE.
    by_url = {}
    for item in featured:
        url = item["url"].split("?")[0].rstrip("/")
        prior = by_url.get(url)
        if prior is None or item.get("firstCommentAt", "") < prior.get("firstCommentAt", ""):
            by_url[url] = {
                "url": url,
                "handle": item["handle"],
                "title": item.get("title", ""),
                "firstCommentAt": item.get("firstCommentAt", ""),
                "weekStart": week_start(item),
            }

    works = sorted(by_url.values(), key=lambda x: (x["firstCommentAt"], x["url"]))
    output = {
        "version": 1,
        "magazineUrl": MAGAZINE_URL,
        "description": "Featured-site articles eligible for magazine membership. This is NOT a record of completed magazine additions.",
        "works": works,
    }
    path = DATA / "magazine-eligible.json"
    path.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Magazine eligibility list: {len(works)} unique articles (not yet added to note)")


if __name__ == "__main__":
    main()
