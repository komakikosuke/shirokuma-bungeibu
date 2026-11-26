# 20字小説のマガジン自動追加

追加先: https://note.com/komaki_kousuke/m/m47893b257d5a

`scripts/note_magazine_sync.py` は、2026-11-15版の既存のSafari同期コードに
20字小説のチャンネルと水曜夜のスケジュールを加えたもの。
注目記事の初回ベースライン、部室の初回バックフィル、両者の1回5件制限を維持する。

## 対象と公開待ち

- 公式サイトの `twenty-credits/data/works.json` に実掲載された作品だけを対象とする。
  抽出候補・除外作品・試作データ・対象期間外の記事は追加しない。
- 現在の投稿期間は火曜19:00以上・翌水曜00:00未満（日本時間）。過去の21:00締切の掲載データも元の期間で検証する。2026-11-25より前にMacへ導入したコードは、下記のインストールコマンドで更新する。
- 対象火曜の翌日、水曜21:00（日本時間）まで待つ。
- 21:00を過ぎても、小牧幸助の公開案内記事を確認できなければ追加しない。
  当該水曜21:00以降に公開された無料の公開記事で、本文内に
  `https://komakikosuke.github.io/shirokuma-bungeibu/twenty-credits/` のリンクが必要。
  タイトルまたは本文に「エンドロール」を含むことも確認する。
  下書き、予約状態、以前の週の案内記事、別作者の記事では解除しない。
- 案内記事そのものやコメントを自動投稿する機能はない。
  参加作品のマガジン追加通知から、その日の案内に気づいてもらう運用を想定する。
- 公開案内の確認後、5秒以上の間隔で順番に追加する。1回の上限は50記事。
  直近60分間の追加試行も最大50回とし、既存の部室・注目記事の同期とも枠を共有する。
  `addition-rate.json` にクリック前の試行時刻を保存するため、手動再実行・Macの再起動・
  Safari停止後の再開・スクリプトの更新でも枠はリセットされない。
  確認前に失敗したクリックも数え、画面ですでに「追加済」の記事は枠を消費しない。
  上限に達した場合はSafariを開かずに終了し、時間経過後の定期確認で続ける。
- 各回の開始前に、公開マガジンの全ページと掲載作品を照合する。
  ローカルで追加済みと記録されていても、実際に未掲載なら再び対象にする。
  すでにマガジンに掲載されている作品は再追加しない。過去の週の記録は保持する。
- note画面の「追加済」を確認してから `endroll-state.json` に記録する。
  Safari操作で失敗したら `safari-guard.json` に操作段階とエラーを保存して停止する。
  次の自動実行はSafariを開かずに終了する。操作中にプロセスが中断された場合も同様。
  ログを確認し、明示的に再開したときだけ未確認の作品から続ける。
  状態保存前に止まっても、画面の「追加済」を確認するため二重追加しない。
  作業用ウィンドウには専用のURLフラグメントを付け、残っていれば再利用する。
  初期作成時は空白ページを使い、作成前後のウィンドウIDから対象を特定する。
  正常時も、専用フラグメント付き・タブ1枚の作業ウィンドウだけを閉じる。
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
curl -fsSL 'https://komakikosuke.github.io/shirokuma-bungeibu/scripts/note_magazine_sync.py?v=20261126-hourly50' -o "$sync_tmp" &&
/usr/bin/python3 "$sync_tmp" --install-endroll
```

標準の `~/Library/Application Support/ShirokumaMagazineSync/note_magazine_sync.py` を更新し、
置き換え前のコードがあれば `note_magazine_sync.py.bak` に保存する。
追加のLaunchAgent `jp.shirokuma.endroll-magazine` を登録する。
5分ごとに公開条件・残件・時間枠を確認する。水曜21:00と公開案内の両条件を満たすまで追加しない。
水曜深夜や翌日以降も再確認するため、50記事ずつ残件を引き継ぐ。
5分ごとの確認によって直近60分50記事の上限を超えることはない。
再確認は公開待ち・時間枠待ち・ネットワーク失敗にも使う。Safari操作失敗後は自動再試行しない。
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

2026-11-24回の未追加分を更新直後に再開する場合は、上記インストール後に次を実行する。
現在の公開マガジンと照合し、残りだけを50記事/時の枠内で処理する。
停止フラグがあればこの明示操作で解除するが、時間枠と追加済みの記録は維持する。

```bash
/usr/bin/python3 "$HOME/Library/Application Support/ShirokumaMagazineSync/note_magazine_sync.py" --endroll-only --resume-safari
```

認証情報やCookieは保存せず、マガジンへの書き込みは従来どおりSafariの画面操作で行う。
LinuxのCIでは時刻・公開確認・掲載対象・公開一覧のページ送り・停止後の再開・
複数回実行や日付をまたいだ60分50記事制限をオフラインでテストする。

## ウィンドウが増える・追加されない場合

自動追加を停止する:

```bash
launchctl bootout "gui/$(id -u)/jp.shirokuma.endroll-magazine"
```

修正版に更新し、Safari操作を停止した状態でログを表示する:

```bash
sync_tmp="$(mktemp -t shirokuma-endroll)" &&
curl -fsSL 'https://komakikosuke.github.io/shirokuma-bungeibu/scripts/note_magazine_sync.py?v=20261119-safari-guard' -o "$sync_tmp" &&
/usr/bin/python3 "$sync_tmp" --repair-endroll
```

この操作で既存の追加済み記録は維持する。既存のSafariウィンドウは開閉しない。
旧コードのエラーは `sync.log` と `launchd-endroll.log` の末尾に表示する。
更新後は既存のKeyboard Maestroから実行された場合も、Safari操作停止フラグで終了する。
`--diagnose-endroll` 単体でも、ログ・直近の失敗・公開判定を読み取りだけで確認できる。
修正したAppleScriptのMac上での実動作は別途確認する必要がある。

ログから原因を解消したあと、まず1件を確認する:

```bash
/usr/bin/python3 "$HOME/Library/Application Support/ShirokumaMagazineSync/note_magazine_sync.py" --endroll-only --resume-safari --max-works 1
```

成功すれば通常の `--endroll-only` 実行で残りを処理する。
失敗したら停止フラグが再び保存されるため、そのまま自動再試行を続けない。
