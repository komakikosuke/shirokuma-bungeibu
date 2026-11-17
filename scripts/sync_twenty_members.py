#!/usr/bin/env python3
"""Classify end-roll participants against the existing private room roster."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from build_twenty_credits import eligible_work, event_window, load_json, load_members
from twenty_char import write_json_atomic

ENDPOINT = "https://shirokuma-writing-room.claska.chatgpt.site/api/endroll/membership"


def request_json(request):
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def public_works(document, event_date):
    since, until = event_window(event_date)
    if document.get("version") != 1 or not isinstance(document.get("works"), list):
        raise ValueError("作品データの形式が不正です")
    if "hashtag" in document:
        if document["hashtag"] != "20字小説":
            raise ValueError("対象タグが一致しません")
        return [work for record in document["works"]
                if (work := eligible_work(record, since, until, set())) is not None]
    if document.get("sourceHashtag") != "20字小説" or document.get("eventDate") != event_date:
        raise ValueError("公開作品の対象日・タグが一致しません")
    return document["works"]


def sync_members(document, event_date):
    works = public_works(document, event_date)
    url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    authorization = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not url or not authorization:
        raise ValueError("GitHub Actionsの会員判定用認証が必要です")
    token = request_json(Request(url + ("&" if "?" in url else "?") + urlencode({"audience": ENDPOINT}),
                                 headers={"Authorization": "Bearer " + authorization}))["value"]
    payload = {"eventDate": event_date, "works": [
        {key: work[key] for key in ("key", "handle", "publishedAt")} for work in works
    ]}
    result = request_json(Request(ENDPOINT, data=json.dumps(payload).encode(), method="POST",
                                  headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}))
    if (result.get("version") != 2 or result.get("complete") is not True
            or result.get("eventDate") != event_date or not isinstance(result.get("works"), list)
            or len(result["works"]) != len(works)):
        raise ValueError("会員判定が完了していません")
    expected = {work["key"]: (work["handle"], work["publishedAt"]) for work in works}
    seen = set()
    for row in result["works"]:
        key = row.get("key")
        if (key in seen or key not in expected or (row.get("handle"), row.get("publishedAt")) != expected[key]
                or not isinstance(row.get("isMember"), bool)):
            raise ValueError("会員判定と対象作品が一致しません")
        seen.add(key)
    return result


def refresh_published(path, status_path, archive_dir, members):
    document = load_json(path)
    if document.get("eventDate") != members.event_date:
        raise ValueError("会員判定の対象日が一致しません")
    for work in document["works"]:
        work["creditGroup"] = "membership" if members.contains(work) else "club"
    document["works"].sort(key=lambda row: (0 if row["creditGroup"] == "membership" else 1,
                                           row["publishedAt"], row["key"]))
    document["membershipSource"] = members.source
    status = load_json(status_path)
    if status.get("eventDate") != members.event_date:
        raise ValueError("公開状態の対象日が一致しません")
    status.update(membershipCount=sum(work["creditGroup"] == "membership" for work in document["works"]),
                  clubCount=sum(work["creditGroup"] == "club" for work in document["works"]),
                  membershipSource=members.source)
    write_json_atomic(path, document)
    write_json_atomic(status_path, status)
    write_json_atomic(archive_dir / f"{members.event_date}.json", document)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--event-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--refresh-published", action="store_true")
    parser.add_argument("--status", type=Path, default=Path("data/twenty-char-status.json"))
    parser.add_argument("--archive-dir", type=Path, default=Path("twenty-credits/data/archive"))
    args = parser.parse_args()
    try:
        result = sync_members(load_json(args.input), args.event_date)
        write_json_atomic(args.output, result)
        members = load_members(args.output)
        if args.refresh_published:
            refresh_published(args.input, args.status, args.archive_dir, members)
    except Exception:
        # Authentication tokens and the private server response never enter logs.
        parser.exit(2, "会員判定を更新できませんでした。公開データは更新せず停止します。\n")
    print(json.dumps({"eventDate": args.event_date, "classifiedWorks": len(result["works"]),
                      "membershipWorks": sum(work["isMember"] for work in result["works"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
