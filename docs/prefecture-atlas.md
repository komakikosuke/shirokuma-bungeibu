# 都道府県クリエイター図鑑

制作ブランチ `feature/prefecture-atlas` で開発し、本番の `main` とホームページにはまだ変更を加えない。制作中のため `noindex,nofollow` を付与。公開時にこれを外し、入口は別の変更として追加する。

## 掲載条件

公開されているnote記事の**登録ハッシュタグ**に、次の両方がある記事を収集する。

- `#都道府県クリエイター図鑑`
- 47都道府県の正式名称のうち、いずれか（例：`#東京都`、`#京都府`、`#北海道`）

本文に書かれた文字列だけでは判定しない。`#東京`、`#京都旅行` などの省略・派生タグも現在は対象外。出身地の確認、文字数、投稿期間、ジャンルによる制限はない。有料記事も公開メタデータから掲載し、本文は取得・保存しない。複数の都道府県タグがあれば各県に掲載する。

全体の記事数・クリエイター数は重複を除く。県別には、その県に登録された記事と書き手をそれぞれ集計する。同じ記事に複数の都道府県があるため、県別の合計は全体の記事数と一致しないことがある。

## 構成

- `prefectures/index.html`、`style.css`、`app.js`：静的ページ。地図／県一覧、県選択、記事とクリエイター名の一覧、追加表示、企画タグのコピーを備える。
- `prefectures/map.json`：47都道府県の名称・コード・地図。地球地図日本を変換した [dataofjapan/land](https://github.com/dataofjapan/land) の境界を簡略化・配置。出典元を画面上にも表示。離島は地図を見やすくするため一部省略し、沖縄本島は別枠に配置。
- `scripts/sync_prefecture_atlas.py`：noteの公開ハッシュタグ一覧を最後まで走査し、記事詳細の登録タグを確認する。
- `data/prefecture-atlas.json`：公開情報のみを含む掲載データ。初期値は0件。
- `.github/workflows/sync-prefecture-atlas.yml`：検証と収集。制作中のpushは制作ブランチだけを更新する。`main`への公開後は原則毎時17分に起動（GitHub側の遅延があり得る）。

一覧の走査が失敗・打ち切りになった場合はデータを上書きしない。記事単位の一時的な取得失敗では前回確認済みの記事を保持し、次回再試行する。登録タグの削除・公開終了・記事の削除を確認できたものは掲載から外す。既知の記事も毎回確認するため、一覧から消えた記事も再判定される。

色分けは0／1–4／5–9／10–19／20記事以上の5段階。県へのリンクは `#pref=26`（京都府）など。県一覧は `&view=list`。記事とクリエイター名は一つの一覧で表示する。ジャンル表示・ジャンル絞り込み・記事／書き手タブは設けない。

## 検証

    python3 -m unittest discover -s tests -p 'test_prefecture_atlas.py' -v
    node --test tests/test_prefecture_atlas.mjs
    node --check prefectures/app.js
    python3 scripts/sync_prefecture_atlas.py

サンプルは `python3 scripts/build_prefecture_atlas_preview.py` で制作プレビュー用の `dist/` 内にだけ生成する。サンプル表示の案内と確認用リンクは画面に出さず、`sample: true` の場合は更新日時欄も非表示にする。本番データにサンプル記事は混ぜない。

## 小牧幸助の最新記事を使うデバッグ

通常の掲載データとは別に、scripts/build_prefecture_atlas_debug.py が本人の公開RSSから最新3記事を選び、記事詳細の公開メタデータを取得する。出力は data/prefecture-atlas-debug.json。本文は保存せず、記事の実際のハッシュタグをそのまま保持する。

デバッグデータには purpose: prefecture-atlas-preview を付け、通常の収集データとしては読み込めない。通常の2種類のハッシュタグによる掲載条件は変えない。

プレビュー生成時にだけ atlas-debug-feed メタタグを設定する。メタタグのある確認用ページで ?debug=komaki を指定すると、本人の最新記事だけを東京に仮表示する。メタタグのない本番用HTMLではこのURL指定はデバッグを有効にしない。専用の案内と「通常表示に戻る」リンクを出す。

    python3 scripts/build_prefecture_atlas_debug.py
    python3 scripts/build_prefecture_atlas_preview.py --debug-komaki

既存の定期収集ワークフローは、通常の掲載データと別ファイルのデバッグデータを更新する。デバッグ取得が一時的に失敗しても通常の収集は継続する。

非公開の確認用ページはGitHub上の最新のデバッグJSONを読み込み、取得できないときはプレビュー作成時のコピーを使用する。デバッグJSONは通常の収集JSONと分け、通常表示への切り替えでは読み込まない。
