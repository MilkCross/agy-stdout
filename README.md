# agy-stdout

`agy -p`（`--print`）フラグが stdout に何も出力しないバグ（v1.0.4 時点）を回避するラッパースクリプトです。

## 背景・問題

[Antigravity CLI (agy)](https://github.com/google-antigravity/antigravity-cli) の `-p` / `--print` フラグは、非インタラクティブに一問一答する用途で設計されています。  
しかし v1.0.4 時点では、パイプ・リダイレクト・サブプロセス経由で実行すると **stdout に何も出力されない** バグがあります（exit code は 0）。

- 関連 issue: [#76](https://github.com/google-antigravity/antigravity-cli/issues/76) · [#187](https://github.com/google-antigravity/antigravity-cli/issues/187) · [#231](https://github.com/google-antigravity/antigravity-cli/issues/231)
- いずれも未解決・公式対応なし（2026-06-03 時点）

### 根本原因

`printmode_manager.go` が `PlannerResponse` に `ModifiedResponse` が含まれない場合に出力をスキップします。  
ただし **モデルの応答テキストは SQLite の会話 DB に正常に保存されている**ため、そこから読み出すことで回避できます。

```
~/.gemini/antigravity-cli/conversations/{uuid}.db
  └── gen_metadata テーブル
        └── protobuf バイナリ
              └── field .1.2[N].3 = モデルの応答テキスト
```

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
# 単一ディレクトリ
python agy_p.py --add-dir ./src "src ディレクトリの .py ファイルを列挙して"

# 複数ディレクトリ（繰り返し指定可）
python agy_p.py --add-dir ./src --add-dir ./tests "テストカバレッジを確認して"
```

### ツール確認を全スキップする

```bash
python agy_p.py --dangerously-skip-permissions "ファイルを編集して"
```

### サンドボックスモードで実行する

```bash
python agy_p.py --sandbox "コードを実行して結果を教えて"
```

### タイムアウトを調整する

```bash
# agy 内部タイムアウト（デフォルト 5m0s）
python agy_p.py --print-timeout 30s "簡単な質問"
python agy_p.py --print-timeout 10m0s "複雑な処理"

# プロセス強制終了タイムアウト（デフォルト 360 秒）
python agy_p.py --kill-timeout 600 "時間のかかる処理"
```

### ログファイルを指定する

```bash
python agy_p.py --log-file /tmp/agy.log "質問"
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
| `--kill-timeout N` | プロセス強制終了までの秒数（デフォルト: 360） |

## 動作環境

- Windows 10 / 11
- Python 3.x
- [Antigravity CLI](https://github.com/google-antigravity/antigravity-cli) v1.0.4
- `pip install blackboxprotobuf`

## 注意事項

- `agy.exe` のパスは `%LOCALAPPDATA%\agy\bin\agy.exe` を想定しています。異なる場合はスクリプト内の `AGY_EXE` を変更してください。
- このバグが公式に修正された場合、本スクリプトは不要になります。

## ライセンス

MIT
