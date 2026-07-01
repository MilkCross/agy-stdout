# agy-stdout

`agy -p`（`--print`）フラグが stdout に何も出力しない、または非対話環境でハングするバグを回避するラッパースクリプト集です。

## 重要: v1.0.15 で Windows 側のバグは修正されました

[Antigravity CLI (agy)](https://github.com/google-antigravity/antigravity-cli) **v1.0.15** のリリースノートに以下の記載があり、実機検証でも確認しました。

> "Fixed a bug on Windows where print mode and other non-TUI command outputs were silently discarded when run in non-TTY environments (such as pipes or subprocesses)"

**Windows では v1.0.15 以降、素の `agy -p` がパイプ・サブプロセス経由でも正常に stdout へ出力します。** `agy_p.py` は不要になったため **非推奨** とし、以後のメンテナンスは行いません（Windows で `agy -p` がまだ動かない場合は agy 本体を最新版に更新してください）。

一方 **Linux/Unix では別のハング挙動が残っており、`agy_u.py` は引き続き必要です**（詳細は後述）。

## スクリプトの選択

| スクリプト | 対象 OS | 状態 |
|-----------|---------|------|
| `agy_p.py` | Windows のみ | **非推奨**（v1.0.15 で agy 本体側が修正済みのため不要） |
| `agy_u.py` | Windows + Unix/Linux/macOS | **Linux/Unix では引き続き推奨** |

Linux/Unix で使用する場合は **`agy_u.py`** を使用してください。Windows では素の `agy -p`（v1.0.15 以降）を直接使うことを推奨します。

## 背景・問題（v1.0.4〜v1.0.14 時点）

`-p` / `--print` フラグは非インタラクティブに一問一答する用途で設計されていますが、v1.0.4〜v1.0.14 では、パイプ・リダイレクト・サブプロセス経由で実行すると **stdout に何も出力されない** バグがありました（exit code は 0）。

- 関連 issue: [#76](https://github.com/google-antigravity/antigravity-cli/issues/76) · [#187](https://github.com/google-antigravity/antigravity-cli/issues/187) · [#231](https://github.com/google-antigravity/antigravity-cli/issues/231) · [#408](https://github.com/google-antigravity/antigravity-cli/issues/408) · [#431](https://github.com/google-antigravity/antigravity-cli/issues/431)
- v1.0.15（2026-06 リリース）で Windows 側は修正。issue 自体はクローズされていないが、実機では解消を確認済み

### 根本原因（修正前）

`printmode_manager.go` が `PlannerResponse` に `ModifiedResponse` が含まれない場合に出力をスキップしていました。  
モデルの応答テキストは SQLite の会話 DB には正常に保存されていたため、そこから読み出すことで回避していました。

```
~/.gemini/antigravity-cli/conversations/{uuid}.db
  └── gen_metadata テーブル
        └── protobuf バイナリ
              └── field .1.2[N].3 = モデルの応答テキスト
```

`agy_p.py` / `agy_u.py` はこの DB 読み出し方式を今も使用しています。

### CJK ハングと自然終了待ち戦略について（v1.0.6 で修正）

v1.0.4〜v1.0.5 では日本語/CJK テキストのストリーミング後にプロセスがハングする別のバグ（issue [#134](https://github.com/google-antigravity/antigravity-cli/issues/134)）が存在しましたが、v1.0.6 で修正されています。

これを受けて `agy_p.py` / `agy_u.py`（Windows パス）は**プロセスの自然終了**を待ってから DB を読み出す方式を採用しています。これによりツール呼び出しを行うモデルでも、ツールチェーン完了後の最終応答を正確に取得できます。

v1.0.7 では、メッセージ送信後にスピナーが表示されたまま CLI がハングする別の問題も修正されています。

## Linux/Unix 特有のハング問題（v1.0.15 でも未解決・要検証環境）

**2026-06-27、ubuntu-server（SSH 非対話セッション）で v1.0.15 を検証した結果、Windows とは異なる挙動が確認されました。**

| 実行方法 | 結果 |
|---------|------|
| `agy -p "..."` を stdin 未リダイレクトで実行（SSH の `ssh host "cmd"` 形式など） | **ハング**（応答が返らずタイムアウトするまで終了しない） |
| `agy -p "..." < /dev/null` （stdin を明示的に閉じる） | 正常動作。stdout に直接出力される |
| `agy -p "..."` にパイプで何か流し込む | 正常動作 |

つまり **Linux では stdin が「開いたまま」だと agy がハングします。** これは Windows 側で修正された「stdout が破棄される」バグとは別の現象で、v1.0.15 でも解消されていません。

`agy_u.py` の Unix 向けロジック（疑似 TTY 割り当て＋ DB 書き込み検知による強制終了）は、このハングに対する回避策として引き続き有効です。**Linux/Unix で agy を自動化に組み込む場合は、素の `agy -p` ではなく `agy_u.py` を使用してください**（あるいは呼び出し側で必ず `< /dev/null` を明示する運用でも回避可能です）。

## agy_p.py と agy_u.py の違い

| 項目 | agy_p.py（非推奨） | agy_u.py |
|------|----------|----------|
| 対象 OS | Windows のみ | Windows + Unix/Linux/macOS |
| パス設定 | Windows 向けにハードコード | `platform.system()` で自動判別 |
| 疑似 TTY | 不要 | Unix では `pty.openpty()` で割り当て |
| 終了待ち戦略 | 自然終了を待つ | Windows: 自然終了待ち / Unix: DB 書き込み検知で即 kill |

**Unix で疑似 TTY が必要な理由**:  
SSH 非インタラクティブセッションなど TTY を持たない環境では、agy が会話 DB にエントリを書き込まないことがあります。`pty.openpty()` で疑似 TTY を割り当てることでこれを回避しています。

**Unix の終了戦略が異なる理由**:  
上記の通り、Linux では stdin が開いたままだと agy がハングし自然終了しないことがあります。そのため `agy_u.py` では DB に応答が書き込まれた時点でプロセスを強制終了する方式を採用しています。

## インストール

```bash
pip install blackboxprotobuf
```

Linux/Unix の場合は `agy_u.py` をダウンロードして任意のパスに置いてください（Windows では agy 本体を v1.0.15 以降に更新すれば `-p` をそのまま使用でき、本スクリプトは不要です）。

## 使い方

以下は `agy_u.py` の例です（`agy_p.py` と同じオプション体系ですが非推奨です）。

### 基本（新規会話）

```bash
python agy_u.py "あなたの質問"
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
python agy_u.py --model "Gemini 3.5 Flash (High)" "複雑な質問"
python agy_u.py --model "Gemini 3.5 Flash (Low)"  "簡単な質問（高速）"
```

### 会話を継続する

```bash
python agy_u.py "最初のメッセージ"
python agy_u.py -c "続きのメッセージ"                          # 直前の会話を継続
python agy_u.py --conversation "$(cat /tmp/id.txt)" "次の質問"  # 特定の会話を継続
```

### 会話IDを保存して後から再開する

```bash
# 新規会話 — IDをファイルに保存
python agy_u.py "最初のメッセージ" --id-file /tmp/conv.txt
# stderr に "CONV_ID: {uuid}" が出力され、ファイルにも保存されます

# 後から同じ会話を再開
python agy_u.py --conversation "$(cat /tmp/conv.txt)" "続きのメッセージ"
```

### ワークスペースにディレクトリを追加する

```bash
python agy_u.py --add-dir ./src --add-dir ./tests "テストカバレッジを確認して"
```

### ツール確認をスキップ・サンドボックス実行

```bash
python agy_u.py --dangerously-skip-permissions "ファイルを編集して"
python agy_u.py --sandbox "コードを実行して"
```

### タイムアウトを調整する

```bash
# agy 内部タイムアウト（デフォルト 5m0s）
python agy_u.py --print-timeout 30s "簡単な質問"

# プロセス強制終了タイムアウト（デフォルト 360 秒）
python agy_u.py --kill-timeout 600 "時間のかかる処理"
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
- [Antigravity CLI](https://github.com/google-antigravity/antigravity-cli) **v1.0.15 以降**
  - Windows: 素の `agy -p` で問題なし（本スクリプトは不要）
  - Linux/Unix: `agy_u.py` の使用を推奨（stdin 未リダイレクト時のハングが未解決のため）
- `pip install blackboxprotobuf`
- `agy_u.py` を Unix で使用する場合: Python 標準ライブラリの `pty` モジュール（追加インストール不要）

## 注意事項

- Windows での stdout 無出力バグは v1.0.15 で修正済みです。`agy_p.py` は非推奨とし、以後の更新は行いません。
- Linux/Unix では stdin 未リダイレクト時のハングが v1.0.15 時点でも解消されていません。`agy_u.py` の使用を継続してください。
- agy のバージョンアップに伴い本 README の内容が古くなる場合があります。挙動が変わった場合は Issues や PR で報告いただけると助かります。

## ライセンス

MIT
