#!/usr/bin/env python3
"""Build the atlas preview from real collected data, without debug or sample UI."""
import argparse
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = 'https://raw.githubusercontent.com/komakikosuke/shirokuma-bungeibu/feature/prefecture-atlas/data/prefecture-atlas.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feed-url', default=DEFAULT_FEED)
    args = parser.parse_args()
    if args.feed_url != DEFAULT_FEED:
        parser.error('Use the configured atlas feed URL')
    data = json.loads((ROOT / 'data/prefecture-atlas.json').read_text())
    if data.get('sample') is True or data.get('purpose'):
        raise ValueError('実際の掲載データだけをビルドしてください')
    dist = ROOT / 'dist'
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir()
    for directory in ('prefectures', 'assets'):
        shutil.copytree(ROOT / directory, dist / directory, dirs_exist_ok=True)
    (dist / 'data').mkdir(exist_ok=True)
    shutil.copyfile(ROOT / 'data/prefecture-atlas.json', dist / 'data/prefecture-atlas.json')
    for old in dist.rglob('prefecture-atlas-debug.json'):
        old.unlink()
    page = dist / 'prefectures/index.html'
    text = page.read_text()
    meta = '<meta name="atlas-feed" content="' + args.feed_url + '" data-fallback="../data/prefecture-atlas.json">\n'
    page.write_text(text.replace('</head>', meta + '</head>'))
    (dist / 'index.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><meta http-equiv="refresh" content="0;url=./prefectures/"><title>記事で塗る日本地図・制作プレビュー</title><a href="./prefectures/">制作プレビューを開く</a></html>\n')
    config = ROOT / '.openai/hosting.json'
    config.parent.mkdir(exist_ok=True)
    manifest = json.loads(config.read_text()) if config.exists() else {}
    manifest['static'] = {'directory': 'dist'}
    config.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('Real atlas feed packaged without debug UI.')


if __name__ == '__main__':
    main()
