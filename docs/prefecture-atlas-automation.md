# 記事で塗る日本地図の定期収集

対象Site: appgprj_6b060907928081918668c39b5a473203
GitHub: komakikosuke/shirokuma-bungeibu
更新対象ブランチ: feature/prefecture-atlas

収集本体は scripts/sync_prefecture_atlas.py。GitHub Actionsの Validate and sync prefecture creator atlas が実行する。クラウドタスクは3時間ごとに起動要求だけを保存し、記事取得とJSON更新はActionsが行う。タスクの認証は接続済みGitHubを使用し、トークンをファイルやプロンプトに保存しない。

## 1回の実行

1. GitHubからこの手順と、対象ブランチの data/prefecture-atlas-request.json の最新内容・blob SHAを読む。同じブランチで収集中なら重ねて起動せず、進行中の実行を確認する。
2. GitHubのupdate_fileで同じブランチの要求JSONを更新する。versionは1、requestedAtは実行時の現在UTC日時（ISO 8601、秒付き、末尾Z）。新規の現在時刻を使い、直前に読んだblob SHAをshaとして渡す。コミットメッセージは Request prefecture atlas collection。競合した場合は最新内容を読み直して1回だけ再試行する。
3. このpushで .github/workflows/sync-prefecture-atlas.yml が起動する。GitHub Actionsの実行一覧から要求コミットに対応するpush実行を確認する。実行中のときは完了を待つ。承認要求や接続要求が出た場合は回避せず、処理できていないことを報告する。
4. 成功後、同じブランチの data/prefecture-atlas.json を読み戻す。version=1、sampleフラグなし、tag=都道府県クリエイター図鑑、generatedAtが今回の要求時刻以降、sync.status=okであることを確認する。0記事でも成功。記事ごとの省略名は都道府県コードへ正規化される。
5. Siteはこの最新JSONを直接読むため、通常の収集時に再公開はしない。既存ホームへの入口、main、共有設定、収集ロジックは変更しない。正常終了の通知は不要。収集失敗・一部失敗・読み戻し失敗だけを具体的な原因とともに報告する。

## 掲載条件

公開記事の登録ハッシュタグに #都道府県クリエイター図鑑 と、47都道府県のいずれかのタグが両方必要。都・府・県は省略可（東京・大阪・京都・神奈川など）。北海道は北海道。派生タグや本文だけの記載は対象外。複数の県のタグはそれぞれに掲載する。出身地・ジャンル・文字数・有料かどうかは問わない。

## 障害時

収集の全体失敗では前回データを保持する。記事単位の一時エラーでも前回確認済みレコードを保持する。削除・非公開化・参加タグの削除を確認した記事は掲載から外す。通常データと小牧幸助の記事を使うデバッグデータは別ファイルで維持する。
