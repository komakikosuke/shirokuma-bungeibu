#!/usr/bin/env python3
"""Collect first-comment featured candidates from public note APIs.

Matches the existing Safari collector's rules:
 - hashtag シロクマ文芸部, current Japanese month
 - oldest comment on a participation article
 - first commenter must be someone other than that article's author
 - their latest same-month participation article published before the comment
 - one candidate per commenter per month (earliest first-comment opportunity)
Approval decisions are NEVER modified by this collector.
"""
import datetime as dt
import json
import pathlib
import re
import time
import urllib.parse
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE_FILE = ROOT / "data/candidate-discovery-cache.json"
OUT_FILE = ROOT / "data/candidates.json"
TZ = dt.timezone(dt.timedelta(hours=9))
MONTH = dt.datetime.now(TZ).strftime("%Y-%m")
TAG = "シロクマ文芸部"
MAX_PAGES = 20
URL = "https://note.com"
HANDLE = re.compile(r"^[a-zA-Z0-9_-]{2,100}$")
KEY = re.compile(r"^[a-zA-Z0-9]+$")


def get(path):
    url = URL + path
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/18.1 Safari/605.1.15",
        "Accept": "application/json",
        "Referer": "https://note.com/",
    })
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in (429, 503) or attempt == 2:
                raise
        except Exception as exc:
            last_error = exc
            if attempt == 2:
                raise
        time.sleep((attempt+1)*2)
    raise last_error


def read_json(path, default):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else default
    except (OSError, ValueError):
        return default


def canonical_note_url(handle, key):
    return f"https://note.com/{handle}/n/{key}"


def is_handle(s):
    return isinstance(s, str) and bool(HANDLE.fullmatch(s))


def is_key(s):
    return isinstance(s, str) and bool(KEY.fullmatch(s))


def to_time(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return float("-inf")


def scan():
    old = read_json(CACHE_FILE, {})
    cache = old.get("months", {}) if isinstance(old.get("months"), dict) else {}
    month_cache = cache.get(MONTH, {}) if isinstance(cache.get(MONTH), dict) else {}
    prior_notes = month_cache.get("notes", {}) if isinstance(month_cache.get("notes"), dict) else {}
    prior_comments = month_cache.get("comments", {}) if isinstance(month_cache.get("comments"), dict) else {}
    notes = dict(prior_notes)
    comments = dict(prior_comments)

    seen_boundary = False
    page_count = 0
    for page in range(1, MAX_PAGES+1):
        tag = urllib.parse.quote(TAG, safe="")
        j = get(f"/api/v3/hashtags/{tag}/notes?order=new&page={page}")
        d = j.get("data") or {}
        items = d.get("notes") or []
        if not isinstance(items, list):
            raise RuntimeError("Unexpected hashtag response")
        page_count += 1
        for row in items:
            if not isinstance(row, dict):
                continue
            published = str(row.get("publish_at") or "")
            month = published[:7]
            if month < MONTH:
                seen_boundary = True
                break
            if month != MONTH:
                continue
            key = row.get("key")
            handle = (row.get("user") or {}).get("urlname") if isinstance(row.get("user"), dict) else None
            if not is_handle(handle) or not is_key(key):
                continue
            notes[key] = {
                "key": key,
                "title": str(row.get("name") or "")[:300],
                "handle": handle,
                "publishedAt": published,
                "url": canonical_note_url(handle, key),
            }
        if seen_boundary or not items or d.get("is_last_page") or d.get("next_page") is None:
            seen_boundary = True
            break
        time.sleep(.2)
    if not seen_boundary:
        raise RuntimeError("Reached hashtag API 20-page limit; preserving previous candidate data")
    print(f"Month {MONTH}, pages {page_count}, notes {len(notes)}", flush=True)

    now = dt.datetime.now(dt.timezone.utc)
    count_checked, failed = 0, []
    for key, note in sorted(notes.items(), key=lambda kv: kv[1].get("publishedAt",""), reverse=True):
        prev = comments.get(key, {})
        first = prev.get("firstCommenter")
        when = prev.get("firstCommentAt")
        if first and when:
            continue
        checked = to_time(prev.get("checkedAt"))
        if checked > 0 and now.timestamp()-checked < 6*3600:
            continue
        try:
            j = get(f"/api/v3/notes/{key}/note_comments?order=oldest&per_page=1")
            items = j.get("data") or []
            if not isinstance(items, list):
                raise RuntimeError("Unexpected comment list")
            first_row = items[0] if items else {}
            commenter = first_row.get("user") or {}
            person = commenter.get("urlname") if isinstance(commenter,dict) else None
            at = first_row.get("created_at")
            comments[key] = {
                "firstCommenter":person if is_handle(person) else None,
                "firstCommentAt":str(at) if at else None,
                "checkedAt":now.isoformat(timespec="seconds").replace("+00:00","Z"),
                "commentCount":j.get("total_count", len(items)),
            }
            count_checked += 1
        except Exception as exc:
            failed.append(f"{key}: {exc}")
        time.sleep(.15)
    print(f"Checked {count_checked} comments; failures {len(failed)}", flush=True)

    notes_by_author={}
    for note in notes.values():
        notes_by_author.setdefault(note["handle"],[]).append(note)
    for arr in notes_by_author.values():
        arr.sort(key=lambda x:to_time(x["publishedAt"]),reverse=True)

    discovered = []
    for note in notes.values():
        r = comments.get(note["key"]) or {}
        first = r.get("firstCommenter")
        when = r.get("firstCommentAt")
        if not is_handle(first) or first==note["handle"] or not isinstance(when,str) or when[:7]!=MONTH:
            continue
        prior = [n for n in notes_by_author.get(first,[]) if to_time(n["publishedAt"])<=to_time(when)]
        if not prior:
            continue
        work=prior[0]
        discovered.append({
            "month":MONTH,"handle":first,"title":work["title"],"url":work["url"],
            "firstCommentAt":when,"commentedNoteUrl":note["url"]
        })
    discovered.sort(key=lambda w:to_time(w["firstCommentAt"]))
    first_per_author={}
    for w in discovered:
        first_per_author.setdefault(w["handle"],w)

    # Do not remove any previously discovered candidates if a public API yields partial results.
    prev_out=read_json(OUT_FILE,{})
    old_works=prev_out.get("works",[]) if isinstance(prev_out.get("works"),list) else []
    candidates={}
    for w in old_works:
        if isinstance(w,dict) and isinstance(w.get("month"),str) and is_handle(w.get("handle")):
            candidates[w["month"]+"|"+w["handle"]]=w
    for w in first_per_author.values():
        candidates.setdefault(w["month"]+"|"+w["handle"],w)

    cache[MONTH]={"notes":notes,"comments":comments}
    CACHE_FILE.parent.mkdir(parents=True,exist_ok=True)
    CACHE_FILE.write_text(json.dumps({"version":1,"months":cache},ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    out={
        "version":1,
        "generatedAt":now.isoformat(timespec="seconds").replace("+00:00","Z"),
        "works":sorted(candidates.values(),key=lambda w:(w["month"],w.get("firstCommentAt","")),reverse=True)
    }
    OUT_FILE.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print(f"Currently discovered for {MONTH}: {len(first_per_author)}. Total stored: {len(out['works'])}",flush=True)
    if failed:
        print("Some comment checks failed. Previous data was preserved.",flush=True)
        for x in failed[:5]:
            print(x,flush=True)


if __name__=="__main__":
    scan()
