#!/usr/bin/env python3
"""Maintain public note display names for currently featured Shirokuma authors.

Reads approved works from data/works.json. Creator names are stored separately so
Keyboard Maestro can continue replacing works.json without losing nicknames.
"""
import datetime as dt
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKS = ROOT / "data/works.json"
OUTPUT = ROOT / "data/creators.json"
NOW = dt.datetime.now(dt.timezone.utc)
UTC = dt.timezone.utc
TTL = dt.timedelta(days=3)
HANDLE = re.compile(r"^[a-zA-Z0-9_-]{2,100}$")

def get_nickname(handle):
    url = "https://note.com/api/v2/creators/" + urllib.parse.quote(handle, safe="")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ShirokumaBungeibuCreatorSync/1.0)",
            "Accept": "application/json",
            "Referer": "https://note.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as res:
        obj = json.load(res)
    data = obj.get("data", {})
    name = data.get("nickname") if isinstance(data, dict) else None
    if not isinstance(name, str) or not (1 <= len(name.strip()) <= 100):
        raise ValueError("Creator response did not include a valid nickname")
    return name.strip()

def main():
    works = json.loads(WORKS.read_text(encoding="utf-8"))
    handles = sorted({
        entry.get("handle") for entry in works.get("works", [])
        if isinstance(entry, dict) and isinstance(entry.get("handle"), str)
        and HANDLE.fullmatch(entry["handle"])
    })
    try:
        current = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        current = {"version":1, "creators":{}}
    stored = current.get("creators", {})
    if not isinstance(stored, dict):
        stored = {}
    result = {}
    changed = False
    for handle in handles:
        old = stored.get(handle)
        if not isinstance(old, dict):
            old = {}
        name = old.get("name") if isinstance(old.get("name"), str) else None
        checked = old.get("checkedAt", "")
        recently_checked = False
        try:
            when = dt.datetime.fromisoformat(checked.replace("Z", "+00:00"))
            recently_checked = when.tzinfo is not None and NOW-when < TTL
        except (ValueError, AttributeError):
            pass

        if recently_checked and name:
            result[handle] = old
            continue

        try:
            name = get_nickname(handle)
            result[handle] = {
                "name":name,
                "checkedAt":NOW.isoformat(timespec="seconds").replace("+00:00","Z"),
            }
            changed = True
            print(handle, "->", name)
        except Exception as exc:
            print(handle, "could not refresh:", str(exc))
            if name:
                result[handle] = old
        time.sleep(0.3)

    new = {"version":1, "creators":result}
    if not changed and stored == result:
        print("Creator display names unchanged")
        return
    new["updatedAt"] = NOW.isoformat(timespec="seconds").replace("+00:00","Z")
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(new,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__ == "__main__":
    main()
