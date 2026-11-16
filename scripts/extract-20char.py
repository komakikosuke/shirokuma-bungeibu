#!/usr/bin/env python3
"""Extract review-only 20-character candidates; never update site publication data."""
import argparse
import json
from pathlib import Path
import sys

try:
    from twenty_char import NoteClient, ROOT, normalize_hashtag, parse_time, run_extraction
except ModuleNotFoundError as exc:
    if exc.name != "regex":
        raise
    raise SystemExit("依存パッケージをインストールしてください: python3 -m pip install -r scripts/requirements-20char.txt")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hashtag", default="20字小説")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--url", action="append", help="検証用の記事URL。複数回指定できます")
    source.add_argument("--input", type=Path, help="既存の works 配列または記事配列を持つJSON")
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--since", help="含む。日付・タイムゾーンなしの時刻は日本時間")
    parser.add_argument("--until", help="含まない。日付・タイムゾーンなしの時刻は日本時間")
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--output", type=Path, default=ROOT / "var/twenty-char/results.json")
    parser.add_argument("--log", type=Path, default=ROOT / "var/twenty-char/events.jsonl")
    args = parser.parse_args()
    try:
        if args.max_pages < 1 or args.limit < 1 or not 0 <= args.delay <= 60:
            raise ValueError("max-pages・limit は1以上、delay は0〜60で指定してください")
        tag = normalize_hashtag(args.hashtag)
        since = parse_time(args.since) if args.since else None
        until = parse_time(args.until) if args.until else None
        if since and until and since >= until:
            raise ValueError("since は until より前にしてください")
        if (args.url or args.input) and (since or until):
            raise ValueError("期間指定はハッシュタグ収集で使用してください")
        seeds = None
        if args.url:
            seeds = [{"url": url} for url in args.url]
        if args.input:
            obj = json.loads(args.input.read_text(encoding="utf-8"))
            rows = obj.get("works") if isinstance(obj, dict) else obj
            if not isinstance(rows, list):
                raise ValueError("input は works 配列または記事配列で指定してください")
            seeds = rows
        output, log_path = args.output.resolve(), args.log.resolve()
        protected = ROOT / "data"
        for path in (output, log_path):
            if path == protected or protected in path.parents:
                raise ValueError("既存サイトの data/ には出力できません。独立した出力先を指定してください")
            if args.input and path == args.input.resolve():
                raise ValueError("入力ファイルと出力先は分けてください")
        if output == log_path:
            raise ValueError("結果JSONとログは別ファイルにしてください")
        result = run_extraction(NoteClient(), tag=tag, output=output, log_path=log_path,
                                max_pages=args.max_pages, limit=args.limit, since=since,
                                until=until, seeds=seeds, delay=args.delay)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"エラー: {exc}\n")
    print(json.dumps({"output": str(output), "log": str(log_path),
                      "summary": result["summary"], "latestRun": result["latestRun"]}, ensure_ascii=False, indent=2))
    return 2 if result["latestRun"]["stopReason"] == "discovery_error" else 0


if __name__ == "__main__":
    sys.exit(main())
