#!/usr/bin/env python3
"""Build the public 20-character end-roll data from one bounded extraction run."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import json
from pathlib import Path
import re

from twenty_char import COUNT_RULE, MAX_STORY_LINES, count_characters, now_iso, write_json_atomic

JST = timezone(timedelta(hours=9))
HANDLE = re.compile(r"^[a-zA-Z0-9_-]{2,100}$")
KEY = re.compile(r"^n[a-zA-Z0-9]+$")
HOST_NOTE_ID = "komaki_kousuke"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def credit_group(work, members):
    # The host closes this credit section without changing paid membership.
    if work["handle"].lower() == HOST_NOTE_ID:
        return "membership"
    is_member = members.contains(work) if isinstance(members, MembershipSnapshot) else work["handle"] in members
    return "membership" if is_member else "club"


def credit_sort_key(work):
    return (0 if work["creditGroup"] == "membership" else 1,
            1 if work["handle"].lower() == HOST_NOTE_ID else 0,
            work["publishedAt"], work["key"])


def event_window(event_date: str):
    try:
        day = datetime.strptime(event_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("event-date は YYYY-MM-DD で指定してください") from exc
    if day.weekday() != 1:
        raise ValueError("event-date は火曜日を指定してください")
    return (datetime.combine(day, time(19, 0), JST),
            datetime.combine(day, time(21, 0), JST))


def parse_published(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


@dataclass
class MembershipSnapshot:
    event_date: str
    source: dict
    works: dict

    def contains(self, record):
        decision = self.works.get(record["key"])
        if (decision is None or decision["handle"] != record["handle"]
                or parse_published(decision["publishedAt"]) != parse_published(record["publishedAt"])):
            raise ValueError("会員判定と対象作品が一致しません")
        return decision["isMember"]


def load_members(path: Path):
    data = load_json(path)
    if (not isinstance(data, dict) or data.get("version") != 2 or data.get("complete") is not True
            or not isinstance(data.get("source"), dict) or not isinstance(data.get("works"), list)
            or not isinstance(data["source"].get("snapshotId"), str)
            or not isinstance(data["source"].get("capturedAt"), int)):
        raise ValueError("完全なサーバー会員判定が必要です。固定のテスト用リストは使用できません")
    since, until = event_window(data.get("eventDate", ""))
    decisions = {}
    for row in data["works"]:
        if (not isinstance(row, dict) or not isinstance(row.get("key"), str)
                or not KEY.fullmatch(row["key"]) or row["key"] in decisions
                or not isinstance(row.get("handle"), str) or not HANDLE.fullmatch(row["handle"])
                or not isinstance(row.get("isMember"), bool)
                or not (published := parse_published(row.get("publishedAt")))
                or not since <= published < until):
            raise ValueError("会員判定に不正・重複・期間外の作品があります")
        decisions[row["key"]] = row
    return MembershipSnapshot(data["eventDate"], data["source"], decisions)


def eligible_work(record, since, until, members):
    if not isinstance(record, dict):
        return None
    published = parse_published(record.get("publishedAt"))
    if not (published and since <= published < until):
        return None
    reasons = record.get("reasonCodes")
    accepted = record.get("status") == "success" and reasons in ([], None)
    accepted_pending = (record.get("status") == "pending" and isinstance(reasons, list)
                        and bool(reasons) and all(reason in ("first_line_heading", "non_exact_length")
                                                 for reason in reasons))
    char_count = record.get("charCount")
    if (not (accepted or accepted_pending) or type(char_count) is not int
            or not 19 <= char_count <= 21):
        return None
    key, handle = record.get("key"), record.get("handle")
    text, author = record.get("text"), record.get("authorName")
    title, url = record.get("title"), record.get("url")
    if (not isinstance(key, str) or not KEY.fullmatch(key)
            or not isinstance(handle, str) or not HANDLE.fullmatch(handle)
            or not isinstance(text, str) or not text.strip()
            or not isinstance(author, str) or not author.strip()
            or not isinstance(title, str) or not title.strip()
            or not isinstance(url, str) or url != f"https://note.com/{handle}/n/{key}"):
        return None
    if count_characters(text) != char_count:
        return None
    source_lines = record.get("sourceLines")
    if source_lines is not None and (
            not isinstance(source_lines, list) or not 2 <= len(source_lines) <= MAX_STORY_LINES
            or any(not isinstance(line, str) or not line or line != line.strip()
                   or "\n" in line or "\r" in line for line in source_lines)
            or "".join(source_lines) != text or count_characters(source_lines[0]) >= 19):
        return None
    work = {
        "key": key,
        "text": " ".join(source_lines) if source_lines else text,
        "charCount": char_count,
        "authorName": author.strip(),
        "handle": handle,
        "creditGroup": credit_group(record, members),
        "sourceType": "extracted",
        "title": title.strip(),
        "publishedAt": published.isoformat(),
        "url": url,
    }
    if source_lines:
        work["sourceLines"] = source_lines
    return work


def build_documents(extraction, members, event_date, generated_at=None):
    since, until = event_window(event_date)
    if isinstance(members, MembershipSnapshot) and members.event_date != event_date:
        raise ValueError("会員判定の対象日が一致しません")
    if (not isinstance(extraction, dict) or extraction.get("version") != 1
            or extraction.get("hashtag") != "20字小説"
            or extraction.get("countRule") != COUNT_RULE
            or not isinstance(extraction.get("works"), list)):
        raise ValueError("抽出結果の形式・ハッシュタグ・文字数規則が一致しません")
    latest = extraction.get("latestRun")
    if not isinstance(latest, dict):
        raise ValueError("抽出結果に今回の実行情報がありません")
    if latest.get("since") != since.isoformat() or latest.get("until") != until.isoformat():
        raise ValueError("抽出期間が火曜19:00〜21:00の公開対象期間と一致しません")
    if latest.get("stopReason") in {"discovery_error", "running"} or latest.get("truncated") is True:
        raise ValueError("収集が完了していないためエンドロールを更新しません")

    works = []
    seen = set()
    for record in extraction["works"]:
        work = eligible_work(record, since, until, members)
        if work is None:
            continue
        if work["key"] in seen:
            raise ValueError("抽出結果に同一記事が重複しています")
        seen.add(work["key"])
        works.append(work)
    works.sort(key=credit_sort_key)

    checked = latest.get("summary", {}).get("total")
    checked = checked if isinstance(checked, int) and checked >= 0 else len(extraction["works"])
    generated_at = generated_at or now_iso()
    source_window = {"since": since.isoformat(), "until": until.isoformat()}
    document = {
        "version": 1,
        "pageStatus": "ready" if works else "empty",
        "sourceHashtag": "20字小説",
        "eventDate": event_date,
        "sourceWindow": source_window,
        "generatedAt": generated_at,
        "countRule": COUNT_RULE,
        "sourceSummary": {"checked": checked, "extracted": len(works)},
        "works": works,
    }
    if isinstance(members, MembershipSnapshot):
        document["membershipSource"] = members.source
    status = {
        "version": 1,
        "status": document["pageStatus"],
        "eventDate": event_date,
        "workCount": len(works),
        "membershipCount": sum(row["creditGroup"] == "membership" for row in works),
        "clubCount": sum(row["creditGroup"] == "club" for row in works),
        "sourceWindow": source_window,
        "updatedAt": generated_at,
    }
    if isinstance(members, MembershipSnapshot):
        status["membershipSource"] = members.source
    return document, status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--members", type=Path, required=True)
    parser.add_argument("--event-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--archive-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        document, status = build_documents(load_json(args.input), load_members(args.members), args.event_date)
        write_json_atomic(args.output, document)
        write_json_atomic(args.status, status)
        write_json_atomic(args.archive_dir / f"{args.event_date}.json", document)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"エラー: {exc}\n")
    print(json.dumps({"output": str(args.output), "status": status}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
