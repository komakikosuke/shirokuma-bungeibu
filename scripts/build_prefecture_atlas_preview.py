#!/usr/bin/env python3
"""Build an isolated, explicitly labeled design preview. Never edits live data."""
import datetime as dt
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
COUNTS = [17,3,2,7,0,2,5,4,3,2,7,8,38,15,5,0,8,0,4,12,4,9,14,4,3,18,19,10,6,0,0,3,5,8,2,0,4,3,0,13,0,6,4,3,0,3,9]
JST = dt.timezone(dt.timedelta(hours=9))


def sample_document():
    prefectures = json.loads((ROOT / "prefectures/map.json").read_text())["prefectures"]
    articles, sequence, author_index = [], 0, 0
    for pref, count in zip(prefectures, COUNTS):
        for index in range(count):
            sequence += 1
            person = index % 12 if pref["code"] == "26" else author_index % 154
            if pref["code"] != "26":
                author_index += 1
            handle = "atlas_sample_" + str(person).zfill(3)
            name = ["森のしおり", "あおい", "水野まどか"][person] if person < 3 else "旅の書き手 " + str(person).zfill(3)
            category = ["旅", "食", "暮らし", "趣味"][index % 4]
            title = [
                pref["name"] + "、ふらりと立ち寄った街で。",
                "いつもの味を、" + pref["name"] + "で。",
                pref["name"] + "で暮らして見つけた、小さな楽しみ。",
                "好きなものを探しに、" + pref["name"] + "へ。",
            ][index % 4]
            if pref["code"] == "26" and index < 3:
                title = ["京都の路地で、道に迷うのが好きだ。", "三代続く喫茶店で、いつもの一杯。", "鴨川と、本と、何もしない日曜日。"][index]
            key = "n" + str(sequence).zfill(12)
            published = dt.datetime(2026, 11, 24, 20, tzinfo=JST) - dt.timedelta(days=index, minutes=int(pref["code"]))
            articles.append({
                "key": key, "url": "https://note.com/" + handle + "/n/" + key,
                "title": title, "publishedAt": published.isoformat(),
                "author": {"handle": handle, "name": name, "avatarUrl": ""},
                "imageUrl": "", "tags": ["都道府県クリエイター図鑑", pref["name"], category],
                "prefectures": [pref["code"]], "isPaid": False,
            })
    return {"version": 1, "tag": "都道府県クリエイター図鑑", "sample": True, "generatedAt": "2026-11-24T12:00:00Z", "articles": articles}


def main():
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    for directory in ("prefectures", "assets"):
        shutil.copytree(ROOT / directory, dist / directory, dirs_exist_ok=True)
    (dist / "data").mkdir(exist_ok=True)
    data = sample_document()
    (dist / "data/prefecture-atlas.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    shutil.copyfile(ROOT / "data/prefecture-atlas.json", dist / "data/prefecture-atlas-empty.json")
    (dist / "index.html").write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><meta http-equiv="refresh" content="0;url=./prefectures/#pref=26"><title>都道府県クリエイター図鑑・制作プレビュー</title><a href="./prefectures/#pref=26">制作プレビューを開く</a></html>\n')
    config = ROOT / ".openai"
    config.mkdir(exist_ok=True)
    (config / "hosting.json").write_text(json.dumps({"static": {"directory": "dist"}}) + "\n")
    print("Design preview prepared with " + str(len(data["articles"])) + " sample articles.")


if __name__ == "__main__":
    main()
