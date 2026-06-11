# agy-stdout

`agy -p`（`--print`）フラグが stdout に何も出力しないバグ（v1.0.4 時点）を回避するラッパースクリプトです。

## スクリプトの選択

| スクリプト | 対象 OS | 特徴 |
|-----------|---------|------|
| `agy_p.py` | **Windows のみ** | シンプル。パスは Windows 向けにハードコード |
| `agy_u.py` | **Windows + Unix/Linux/macOS** | `platform.system()` でパスを自動判別。Unix では疑似 TTY を割り当て |

Unix/Linux/macOS で使用する場合は **`agy_u.py`** を使用してください。

## 背景・問題

[Antigravity CLI (agy)](https://github.com/google-antigravity/antigravity-cli) の `-p` / `--print` フラグは、非インタラクティブに一問一答する用途で設計されています。  
しかし v1.0.4〜v1.0.6 時点では、パイプ・リダイレクト・サブプロセス経由で実行すると **stdout に何も出力されない** バグがあります（exit code は 0）。

- 関連 issue: [#76](https://github.com/google-antigravity/antigravity-cli/issues/76) · [#187](https://github.com/google-antigravity/antigravity-cli/issues/187) · [#231](https://github.com/google-antigravity/antigravity-cli/issues/231)
- いずれも未解決・公式対応なし（2026-06-09 時点）

### 根本原因

`printmode_manager.go` が `PlannerResponse` に `ModifiedResponse` が含まれない場合に出力をスキップします。  
ただし **モデルの応答テキストは SQLite の会話 DB に正常に保存されている**ため、そこから読み出すことで回避できます。

```
~/.gemini/antigravity-cli/conversations/{uuid}.db
  └── gen_metadata テーブル
        └── protobuf バイナリ
              └── field .1.2[N].3 = モデルの応答テキスト
```

### v1.0.6 での CJK ハング修正について

v1.0.4〜v1.0.5 では日本語/CJK テキストのストリーミング後にプロセスがハングする別のバグ（issue [#134](https://github.com/google-antigravity/antigravity-cli/issues/134)）が存在しましたが、**v1.0.6 で修正**されています。

`agy_p.py` は v1.0.6 以降を前提とし、**プロセスの自然終了**を待ってから DB を読み出す方式を採用しています。これによりツール呼び出しを行うモデルでも、ツールチェーン完了後の最終応答を正確に取得できます。

なお v1.0.7 では、メッセージ送信後にスピナーが表示されたまま CLI がハングする別の問題も修正されています。**v1.0.7 以降を使用することを推奨します。**

## agy_p.py と agy_u.py の違い

| 項目 | agy_p.py | agy_u.py |
|------|----------|----------|
| 対象 OS | Windows のみ | Windows + Unix/Linux/macOS |
| パス設定 | Windows 向けにハードコード | `platform.system()` で自動判別 |
| 疑似 TTY | 不要（Windows は不要） | Unix では `pty.openpty()` で割り当て |
| 終了待ち戦略 | 自然終了を待つ | Windows: 自然終了待ち / Unix: DB 書き込み検知で即 kill |

**Unix で疑似 TTY が必要な理由**:  
SSH 非インタラクティブセッションなど TTY を持たない環境では、agy が会話 DB にエントリを書き込まないことがあります。`pty.openpty()` で疑似 TTY を割り当てることでこれを回避しています。

**Unix の終了戦略が異なる理由**:  
Unix の SSH 非インタラクティブセッションでは agy が自然終了しないことがあります。そのため `agy_u.py` では DB に応答が書き込まれた時点でプロセスを強制終了する方式を採用しています。

## インストール

```bash
pip install blackboxprotobuf
```

`agy_p.py`（Windows）または `agy_u.py`（Unix/Linux/macOS）をダウンロードして任意のパスに置いてください。

## 使い方

以下の例では `agy_p.py` を使用していますが、`agy_u.py` でも同じオプションが使えます。

### 基本（新規会話）

```bash
python agy_p.py "あなたの質問"
```

### モデルを指定する（v1.0.5+ で追加）

`--model` には **agy 内部ラベル** をそのまま指定します。

| 指定値 | 説明 |
|--------|------|
| `"Gemini 3.5 Flash (Low)"` | デフォルト。高速・低コスト |
| `"Gemini 3.5 Flash (Medium)"` | バランス型 |
| `"Gemini 3.5 Flash (High)"` | 最大性能 |

> **注意**: `gemini-2.5-pro` や `gemini-2.5-flash` などの Gemini API スタイルの名前は認識されず、インタラクティブモードで設定しているデフォルトモデルにフォールバックします（`agy` の設定画面で変更可能）。

```bash
python agy_p.py --model "Gemini 3.5 Flash (High)" "複雑な質問"
python agy_p.py --model "Gemini 3.5 Flash (Low)"  "簡単な質問（高速）"
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

| オプション | 説明 | 追加バージョン |
|-----------|------|------|
| `-c` / `--continue` | 直前の会話を継続 | v1.0.4 |
| `--conversation ID` | 指定した UUID の会話を継続 | v1.0.4 |
| `--model MODEL` | 使用するモデルを指定。有効値: `"Gemini 3.5 Flash (Low)"` / `"(Medium)"` / `"(High)"` | v1.0.5 |
| `--add-dir PATH` | ワークスペースにディレクトリを追加（複数回指定可） | v1.0.4 |
| `--dangerously-skip-permissions` | ツール確認を全スキップ | v1.0.4 |
| `--log-file PATH` | agy のログ出力先を上書き | v1.0.4 |
| `--print-timeout DURATION` | agy 内部の print モードタイムアウト（例: `30s`, `5m0s`） | v1.0.4 |
| `--sandbox` | サンドボックスモードで実行 | v1.0.4 |

### ラッパー独自フラグ（agy には転送されない）

| オプション | 説明 |
|-----------|------|
| `--id-file PATH` | 新規会話の UUID をファイルに保存 |
| `--poll-interval N` | DB をチェックする間隔（秒、デフォルト: 0.3） |
| `--kill-timeout N` | プロセス強制終了までの秒数（デフォルト: 360） |

## 動作環境

- Python 3.x
- [Antigravity CLI](https://github.com/google-antigravity/antigravity-cli) **v1.0.7 以降を推奨**
- `pip install blackboxprotobuf`
- `agy_u.py` を Unix で使用する場合: Python 標準ライブラリの `pty` モジュール（追加インストール不要）

## 注意事項

- stdout バグが公式に修正された場合、本スクリプトは不要になります。

## ライセンス

MIT
