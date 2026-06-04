# agy-stdout

`agy -p`（`--print`）フラグが stdout に何も出力しないバグ（v1.0.4 時点）と、
日本語/CJK テキストのストリーミング後にプロセスがハングするバグを回避するラッパースクリプトです。

## 背景・問題

[Antigravity CLI (agy)](https://github.com/google-antigravity/antigravity-cli) には v1.0.4 時点で 2 つのバグがあります。

### バグ 1: `-p` フラグが stdout に何も出力しない

`-p` / `--print` フラグは非インタラクティブに一問一答する用途で設計されていますが、
パイプ・リダイレクト・サブプロセス経由で実行すると **stdout に何も出力されない**バグがあります（exit code は 0）。

- 関連 issue: [#76](https://github.com/google-antigravity/antigravity-cli/issues/76) · [#187](https://github.com/google-antigravity/antigravity-cli/issues/187) · [#231](https://github.com/google-antigravity/antigravity-cli/issues/231)

**根本原因**: `printmode_manager.go` が `PlannerResponse` に `ModifiedResponse` が含まれない場合に出力をスキップします。ただし **モデルの応答テキストは SQLite の会話 DB に正常に保存されている**ため、そこから読み出すことで回避できます。

```
~/.gemini/antigravity-cli/conversations/{uuid}.db
  └── gen_metadata テーブル
        └── protobuf バイナリ
              └── field .1.2[N].3 = モデルの応答テキスト
```

### バグ 2: 日本語/CJK テキストのストリーミング後にプロセスがハングする

日本語・中国語・韓国語などの CJK テキストを含む応答をストリーミングすると、
`text_drip.go` がアニメーション中にビジーループに入り、**プロセスが永遠に終了しない**ことがあります。

- 関連 issue: [#134](https://github.com/google-antigravity/antigravity-cli/issues/134) · [#168](https://github.com/google-antigravity/antigravity-cli/issues/168) · [#183](https://github.com/google-antigravity/antigravity-cli/issues/183)

**根本原因**: UTF-8 マルチバイト文字がストリームチャンクをまたいで分割されると、
drip バッファが不正バイト列として処理できなくなり `charIdx` が `length` に到達しないまま無限ループに入ります。

**重要な発見**: 実測により、**モデルの応答は `text_drip` のアニメーション開始前に DB へ書き込まれる**ことが確認されています。
つまり `text_drip` がハングしていても、応答テキストは DB に保存済みです。

```
① API からストリーム受信（完了）
   ↓
② DB に応答テキストを書き込む  ← 正常に完了
   ↓
③ text_drip がアニメーション開始  ← ここでハングする可能性あり
   ↓（CJK テキストでビジーループ）
④ プロセスが終了しない（SIGKILL でのみ停止）
```

**対策**: DB に応答が書き込まれた時点でプロセスを強制終了することで、
ハングの有無にかかわらず確実に応答を取得できます。

すべての issue は未解決・公式対応なし（2026-06-04 時点）。

## インストール

```bash
pip install blackboxprotobuf
```

`agy_p.py` をダウンロードして任意のパスに置いてください。

## 使い方

### 基本（新規会話）

```bash
python agy_p.py "あなたの質問"
```

### 会話を継続する

```bash
python agy_p.py "最初のメッセージ"
python agy_p.py -c "続きのメッセージ"                          # 直前の会話を継続
python agy_p.py --conversation "$(cat /tmp/id.txt)" "次の質問"  # 特定の会話を継続
```

### 会話IDを保存して後から再開する

```bash
# 新規会話 — IDをファイルに保存
python agy_p.py "最初のメッセージ" --id-file /tmp/conv.txt
# stderr に "CONV_ID: {uuid}" が出力され、ファイルにも保存されます

# 後から同じ会話を再開
python agy_p.py --conversation "$(cat /tmp/conv.txt)" "続きのメッセージ"
```

### ワークスペースにディレクトリを追加する

```bash
python agy_p.py --add-dir ./src --add-dir ./tests "テストカバレッジを確認して"
```

### ツール確認をスキップ・サンドボックス実行

```bash
python agy_p.py --dangerously-skip-permissions "ファイルを編集して"
python agy_p.py --sandbox "コードを実行して"
```

### タイムアウトを調整する

```bash
# agy 内部タイムアウト（デフォルト 5m0s）
python agy_p.py --print-timeout 30s "簡単な質問"

# プロセス強制終了タイムアウト（デフォルト 360 秒）
python agy_p.py --kill-timeout 600 "時間のかかる処理"
```

## オプション一覧

### agy に転送されるフラグ

| オプション | 説明 |
|-----------|------|
| `-c` / `--continue` | 直前の会話を継続 |
| `--conversation ID` | 指定した UUID の会話を継続 |
| `--add-dir PATH` | ワークスペースにディレクトリを追加（複数回指定可） |
| `--dangerously-skip-permissions` | ツール確認を全スキップ |
| `--log-file PATH` | agy のログ出力先を上書き |
| `--print-timeout DURATION` | agy 内部の print モードタイムアウト（例: `30s`, `5m0s`） |
| `--sandbox` | サンドボックスモードで実行 |

### ラッパー独自フラグ（agy には転送されない）

| オプション | 説明 |
|-----------|------|
| `--id-file PATH` | 新規会話の UUID をファイルに保存 |
| `--poll-interval N` | DB をチェックする間隔（秒、デフォルト: 0.3） |
| `--kill-timeout N` | プロセス強制終了までの秒数（デフォルト: 360） |

## 動作環境

- Windows 10 / 11
- Python 3.x
- [Antigravity CLI](https://github.com/google-antigravity/antigravity-cli) v1.0.4
- `pip install blackboxprotobuf`

## 注意事項

- `agy.exe` のパスは `%LOCALAPPDATA%\agy\bin\agy.exe` を想定しています。異なる場合はスクリプト内の `AGY_EXE` を変更してください。
- これらのバグが公式に修正された場合、本スクリプトは不要になります。

## ライセンス

MIT
