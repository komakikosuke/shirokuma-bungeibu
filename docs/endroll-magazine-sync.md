# 20字小説のマガジン自動追加

追加先: https://note.com/komaki_kousuke/m/m47893b257d5a

`scripts/note_magazine_sync.py` は、2026-11-15版の既存のSafari同期コードに
20字小説のチャンネルと水曜夜のスケジュールを加えたもの。
注目記事の初回ベースライン、部室の初回バックフィル、両者の1回5件制限を維持する。

## 対象と公開待ち

- 公式サイトの `twenty-credits/data/works.json` に実掲載された作品だけを対象とする。
  抽出候補・除外作品・試作データ・対象期間外の記事は追加しない。
- 対象火曜の翌日、水曜21:00（日本時間）まで待つ。
- 21:00を過ぎても、小牧幸助の公開案内記事を確認できなければ追加しない。
  当該水曜21:00以降に公開された無料の公開記事で、本文内に
  `https://komakikosuke.github.io/shirokuma-bungeibu/twenty-credits/` のリンクが必要。
  タイトルまたは本文に「エンドロール」を含むことも確認する。
  下書き、予約状態、以前の週の案内記事、別作者の記事では解除しない。
- 案内記事そのものやコメントを自動投稿する機能はない。
  参加作品のマガジン追加通知から、その日の案内に気づいてもらう運用を想定する。
- 公開案内の確認後、全対象を5秒以上の間隔で順番に追加する。
  1回5件で打ち切らず、その回の全作品を処理する。113件なら完了まで十数分以上かかる。
- note画面の「追加済」を確認してから `endroll-state.json` に記録する。
  途中失敗時は当該チャンネルを止め、次回は未確認の作品から再開する。
  状態保存前に止まっても、画面の「追加済」を確認するため二重追加しない。
- 状態は作品URL単位で保持する。週が替わっても前の週の案内で解除しない。
  同じ週に掲載データが修正されれば、後から増えた掲載作品も次回対象になる。
  1週間以上古い掲載データは追加しない。公開後の作品取り消しによる自動削除は行わない。

## Macへの反映

既存の同期を動かしているMacで一度実行する。
Safariは小牧幸助のnoteアカウントにログイン済みで、
「Apple EventsからのJavaScriptを許可」が有効になっている前提。
既存のKeyboard Maestroの時刻設定や状態ファイルは変更しない。

```bash
sync_tmp="$(mktemp -t shirokuma-endroll)" &&
curl -fsSL 'https://komakikosuke.github.io/shirokuma-bungeibu/scripts/note_magazine_sync.py' -o "$sync_tmp" &&
/usr/bin/python3 "$sync_tmp" --install-endroll
```

標準の `~/Library/Application Support/ShirokumaMagazineSync/note_magazine_sync.py` を更新し、
置き換え前のコードがあれば `note_magazine_sync.py.bak` に保存する。
追加のLaunchAgent `jp.shirokuma.endroll-magazine` を登録する。
水曜21:00に開始し、21時台は2分ごと、22時台は15分ごとに再確認する。
実行中の再起動は共通の排他ロックで抑止する。
登録直後にも一度確認するが、公開前の追加はしない。
Macのタイムゾーンは日本時間が必要（異なる設定ではインストールを停止）。
時刻通りに処理するには、Macが起動してスリープせず、ネット接続されている必要がある。
起動・接続が遅れた場合は、次の確認または既存の定期同期で未処理分を再開する。

読み取りだけの確認（Safariや状態ファイルを変更しない）:

```bash
/usr/bin/python3 "$HOME/Library/Application Support/ShirokumaMagazineSync/note_magazine_sync.py" --check-endroll
```

`waiting_for_wednesday_21` は公開時刻待ち、
`waiting_for_public_announcement` は案内記事の公開待ち、`released` は追加可能。
ログは既存の `sync.log`、追加スケジュールの出力は `launchd-endroll.log` に残る。
`--endroll-only` は既存2チャンネルを動かさず、この追加処理だけを実行する。

認証情報やCookieは保存せず、マガジンへの書き込みは従来どおりSafariの画面操作で行う。
LinuxのCIでは時刻・公開確認・掲載対象の検証と、停止後の再開をオフラインでテストする。
