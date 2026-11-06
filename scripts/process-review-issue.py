#!/usr/bin/env python3
"""Apply a review decision submitted as an issue by the repository owner.

The public approval page creates a prefilled GitHub issue. This workflow checks
the issue's actual GitHub author and validates the candidate against stored
candidate records before modifying a single independent decisions file.
"""
import datetime as dt
import json
import os
import pathlib
import re

ROOT=pathlib.Path(__file__).resolve().parents[1]
MARKER=re.compile(r"<!-- shirokuma-review-request\s*(\{[^\n]*\})\s*-->",re.DOTALL)
HANDLE=re.compile(r"^[a-zA-Z0-9_-]{2,100}$")
MONTH=re.compile(r"^\d{4}-\d{2}$")
OWNER="komakikosuke"
ALLOWED={"approved","draft","excluded"}

def load(file):
    return json.loads((ROOT/file).read_text(encoding="utf-8"))

def main():
    event=json.loads(pathlib.Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    issue=event.get("issue",{})
    author=(issue.get("user") or {}).get("login")
    if author!=OWNER:
        raise SystemExit("Only repository owner may make an approval decision")
    title=issue.get("title") or ""
    if not title.startswith("[シロクマ掲載管理] "):
        raise SystemExit("Not an approval issue")
    match=MARKER.search(issue.get("body") or "")
    if not match:
        raise SystemExit("Missing review-request payload")
    request=json.loads(match.group(1))
    if request.get("version")!=1:
        raise SystemExit("Unknown request version")
    month,handle,status=request.get("month"),request.get("handle"),request.get("status")
    if not isinstance(month,str) or not MONTH.fullmatch(month):
        raise SystemExit("Invalid month")
    if not isinstance(handle,str) or not HANDLE.fullmatch(handle):
        raise SystemExit("Invalid creator")
    if status not in ALLOWED:
        raise SystemExit("Invalid decision")
    key=month+"|"+handle
    if not title.endswith(key+" "+status):
        raise SystemExit("Issue title and payload disagree")
    candidates=load("data/candidates.json")
    works=load("data/works.json")
    known=[x for x in list(candidates.get("works",[]))+list(works.get("works",[]))
           if isinstance(x,dict) and x.get("month")==month and x.get("handle")==handle]
    if not known:
        raise SystemExit("This creator/month has not been discovered as an eligible candidate")

    path=ROOT/"data/admin-decisions.json"
    record=json.loads(path.read_text(encoding="utf-8"))
    if record.get("version")!=1 or not isinstance(record.get("decisions"),dict):
        raise SystemExit("Review data is missing or invalid")
    record["decisions"][key]={
        "status":status,
        "updatedAt":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
    }
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(key,"->",status)

if __name__=="__main__":
    main()
