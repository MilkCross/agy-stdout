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

### 会話を継続する（`--continue`）

```bash
python agy_p.py "最初のメッセージ"
python agy_p.py -c "続きのメッセージ"   # 直前の会話を継続
```

### 会話IDを使って特定の会話を継続する

```bash
# 新規会話 — IDをファイルに保存
python agy_p.py "最初のメッセージ" --id-file /tmp/conv.txt
# stderr に "CONV_ID: {uuid}" が出力され、ファイルにも保存されます

# 後から同じ会話を再開
python agy_p.py --conversation "$(cat /tmp/conv.txt)" "続きのメッセージ"
```

### 複数の会話を並行して管理する

```bash
# 会話A
python agy_p.py "好きな色は青です" --id-file /tmp/conv_a.txt

# 会話B（独立したコンテキスト）
python agy_p.py "好きな数字は42です" --id-file /tmp/conv_b.txt

# 会話Aに戻る
python agy_p.py --conversation "$(cat /tmp/conv_a.txt)" "好きな色は何でしたか？"
# → "青" と返答（会話Bの内容は含まれない）

# 会話Bに戻る
python agy_p.py --conversation "$(cat /tmp/conv_b.txt)" "好きな色と数字は？"
# → 色は知らないが数字は42と返答
```

### オプション一覧

| オプション | 説明 |
|-----------|------|
| `-c` / `--continue` | 直前の会話を継続 |
| `--conversation ID` | 指定したUUIDの会話を継続 |
| `--id-file PATH` | 新規会話のIDをファイルに保存 |
| `--timeout N` | タイムアウト秒数（デフォルト: 120） |

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
