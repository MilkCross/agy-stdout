# agy-stdout

`agy -p`（`--print`）フラグが stdout に何も出力しない、または非対話環境でハングするバグを回避するために作られたラッパースクリプト集です。

## 重要: v1.1.2 現在、両スクリプトとも非推奨です

[Antigravity CLI (agy)](https://github.com/google-antigravity/antigravity-cli) 本体側の修正により、**Windows・Linux/Unix いずれも素の `agy -p` を直接使用することを推奨します。**

| 修正内容 | 修正バージョン | 確認日 |
|---------|--------------|--------|
| Windows: 非 TTY 環境（パイプ/サブプロセス）で stdout が破棄される | v1.0.15 | 2026-06-27 |
| Linux/Unix: stdin が開いたままだとハングする | v1.1.1〜v1.1.2 | 2026-07-19 |

**`agy_p.py`（Windows 用）・`agy_u.py`（Windows+Unix 用）はいずれも非推奨とし、以後のメンテナンスは行いません。** agy 本体を v1.1.2 以降に更新した上で、素の `agy -p` を直接使用してください。

過去のバグの詳細・スクリプトの実装意図は記録として以下に残します。

## agy 本体の更新方法

```bash
agy update
```

## スクリプトの状態

| スクリプト | 対象 OS | 状態 |
|-----------|---------|------|
| `agy_p.py` | Windows のみ | **非推奨**（v1.0.15 で agy 本体側が修正済み） |
| `agy_u.py` | Windows + Unix/Linux/macOS | **非推奨**（Linux 側も v1.1.2 で agy 本体側が修正済み） |

---

## 背景・経緯（履歴）

### バグ①: Windows で stdout に何も出力されない（v1.0.4〜v1.0.14、v1.0.15 で修正）

`-p` / `--print` フラグは非インタラクティブに一問一答する用途で設計されていましたが、v1.0.4〜v1.0.14 では、パイプ・リダイレクト・サブプロセス経由で実行すると **stdout に何も出力されない** バグがありました（exit code は 0）。

- 関連 issue: [#76](https://github.com/google-antigravity/antigravity-cli/issues/76) · [#187](https://github.com/google-antigravity/antigravity-cli/issues/187) · [#231](https://github.com/google-antigravity/antigravity-cli/issues/231) · [#408](https://github.com/google-antigravity/antigravity-cli/issues/408) · [#431](https://github.com/google-antigravity/antigravity-cli/issues/431)
- v1.0.15 のリリースノート: "Fixed a bug on Windows where print mode and other non-TUI command outputs were silently discarded when run in non-TTY environments (such as pipes or subprocesses)"
- issue 自体はクローズされていないが、実機検証で解消を確認済み

**根本原因（修正前）**: `printmode_manager.go` が `PlannerResponse` に `ModifiedResponse` が含まれない場合に出力をスキップしていました。モデルの応答テキストは SQLite の会話 DB には正常に保存されていたため、`agy_p.py` / `agy_u.py` はそこから読み出すことで回避していました。

```
~/.gemini/antigravity-cli/conversations/{uuid}.db
  └── gen_metadata テーブル
        └── protobuf バイナリ
              └── field .1.2[N].3 = モデルの応答テキスト
```

### バグ②: CJK テキストのストリーミング後にハングする（v1.0.4〜v1.0.5、v1.0.6 で修正）

日本語/CJK テキストのストリーミング後にプロセスがハングする別のバグ（issue [#134](https://github.com/google-antigravity/antigravity-cli/issues/134)）が存在しましたが、v1.0.6 で修正されています。v1.0.7 では、メッセージ送信後にスピナーが表示されたまま CLI がハングする別の問題も修正されました。

### バグ③: Linux/Unix で stdin が開いたままだとハングする（v1.0.6〜v1.1.0、v1.1.1〜v1.1.2 で修正）

2026-06-27、ubuntu-server（SSH 非対話セッション）で v1.0.15 を検証した結果、Windows とは異なる挙動が確認されました。

| 実行方法 | v1.1.0 まで | v1.1.2 以降 |
|---------|------|------|
| `agy -p "..."` を stdin 未リダイレクトで実行（`ssh host "cmd"` 形式など） | **ハング** | 正常終了 |
| `agy -p "..." < /dev/null` （stdin を明示的に閉じる） | 正常動作 | 正常動作 |

v1.1.1 のリリースノート: "Fixed `agy -p` hanging when invoked inside shell scripts by no longer reading stdin when a prompt is provided via flag"

2026-07-19、ubuntu-server を v1.1.1 → v1.1.2 に更新し、以下を確認しました。

- stdin 未リダイレクトの `agy -p` が正常終了(3 回連続・CJK テキストも含め再現なし)
- 疑似 TTY を割り当てない素の Python `subprocess.Popen` 経由でも正常に DB へ書き込み・stdout 出力される

これにより `agy_u.py` が対策していた「疑似 TTY 割り当て」「DB 書き込み検知による強制終了」のいずれも不要になったと判断し、非推奨としました。

---

## agy_p.py / agy_u.py を今も使う場合（非推奨・参考情報）

新しい agy を使えない事情がある場合のみ、以下を参考にしてください。動作は v1.1.2 時点で確認したものですが、以後の agy アップデートに追従したメンテナンスは行いません。

### インストール

```bash
pip install blackboxprotobuf
```

### 使い方

```bash
python agy_u.py "あなたの質問"
python agy_u.py -c "続きのメッセージ"                          # 直前の会話を継続
python agy_u.py --conversation "$(cat /tmp/id.txt)" "次の質問"  # 特定の会話を継続
python agy_u.py "最初のメッセージ" --id-file /tmp/conv.txt      # 会話IDを保存
python agy_u.py --add-dir ./src --add-dir ./tests "テストカバレッジを確認して"
python agy_u.py --dangerously-skip-permissions "ファイルを編集して"
python agy_u.py --sandbox "コードを実行して"
python agy_u.py --print-timeout 30s "簡単な質問"        # agy 内部タイムアウト（デフォルト 5m0s）
python agy_u.py --kill-timeout 600 "時間のかかる処理"     # プロセス強制終了タイムアウト（デフォルト 360秒）
```

### `--model` について

`--model` には agy 内部のモデル表示名をそのまま指定します。v1.1.2 時点で確認できた値の例:

```
Gemini 3.5 Flash (Low) / (Medium) / (High)
Gemini 3.1 Pro (Low) / (High)
Claude Sonnet 4.6 (Thinking)
Claude Opus 4.6 (Thinking)
GPT-OSS 120B (Medium)
```

> v1.1.2 では、完全に認識不能な名前を指定すると **エラー + 利用可能モデル一覧を表示して非ゼロ exit** するようになりました（例: `totally-bogus-model`）。一方 `gemini-2.5-pro` のような「それらしいが未登録」の名前は、引き続きサイレントフォールバックの対象です。手元の agy で実際に使える名前は `agy models` で確認してください。

```bash
python agy_u.py --model "Gemini 3.1 Pro (High)" "複雑な質問"
```

### オプション一覧

| オプション | 説明 |
|-----------|------|
| `-c` / `--continue` | 直前の会話を継続 |
| `--conversation ID` | 指定した UUID の会話を継続 |
| `--model MODEL` | 使用するモデルを指定 |
| `--add-dir PATH` | ワークスペースにディレクトリを追加（複数回指定可） |
| `--dangerously-skip-permissions` | ツール確認を全スキップ |
| `--log-file PATH` | agy のログ出力先を上書き |
| `--print-timeout DURATION` | agy 内部の print モードタイムアウト（例: `30s`, `5m0s`） |
| `--sandbox` | サンドボックスモードで実行 |
| `--id-file PATH`（ラッパー独自） | 新規会話の UUID をファイルに保存 |
| `--poll-interval N`（ラッパー独自） | DB をチェックする間隔（秒、デフォルト: 0.3） |
| `--kill-timeout N`（ラッパー独自） | プロセス強制終了までの秒数（デフォルト: 360） |

### agy_p.py と agy_u.py の違い

| 項目 | agy_p.py | agy_u.py |
|------|----------|----------|
| 対象 OS | Windows のみ | Windows + Unix/Linux/macOS |
| パス設定 | Windows 向けにハードコード | `platform.system()` で自動判別 |
| 疑似 TTY | 不要 | Unix では `pty.openpty()` で割り当て |
| 終了待ち戦略 | 自然終了を待つ | Windows: 自然終了待ち / Unix: DB 書き込み検知で即 kill |

いずれも DB（`~/.gemini/antigravity-cli/conversations/{uuid}.db` の `gen_metadata` テーブル）を直接読み出す方式で応答を取得します。

## 動作環境（参考情報を使う場合）

- Python 3.x
- `pip install blackboxprotobuf`
- `agy_u.py` を Unix で使用する場合: Python 標準ライブラリの `pty` モジュール（追加インストール不要）

## ライセンス

MIT
