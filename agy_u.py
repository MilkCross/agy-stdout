#!/usr/bin/env python
"""
agy_p.py — agy -p wrapper that actually prints the response to stdout.

Usage:
    python agy_p.py "your prompt"
    python agy_p.py -c "follow-up"
    python agy_p.py --conversation ID "follow-up"
    python agy_p.py --add-dir ./src --add-dir ./tests "your prompt"
    python agy_p.py --dangerously-skip-permissions "your prompt"
    python agy_p.py --print-timeout 30s "your prompt"
    python agy_p.py --sandbox "your prompt"
    python agy_p.py --log-file /tmp/agy.log "your prompt"
    python agy_p.py "first message" --id-file /tmp/id.txt

Root cause of the bug (agy v1.0.4):
    printmode_manager.go silently drops responses when PlannerResponse has no
    ModifiedResponse. The actual text is saved to the SQLite conversation DB
    (gen_metadata table) even when stdout gets nothing. This script reads it back.

Hang workaround (issue #134):
    text_drip.go enters a busy-loop after streaming CJK (Japanese/Chinese/Korean)
    text, causing agy to never exit. The response is already written to the DB
    before text_drip starts animating, so this script polls the DB and kills the
    process as soon as the response is found — without waiting for natural exit.

Flags forwarded to agy:
    -c / --continue              Continue most recent conversation
    --conversation ID            Continue specific conversation by UUID
    --model MODEL                Model to use. Valid internal labels:
                                   "Gemini 3.5 Flash (Low)"    — default (fast)
                                   "Gemini 3.5 Flash (Medium)" — balanced
                                   "Gemini 3.5 Flash (High)"   — max capability
                                 Any other value silently falls back to Medium.
    --add-dir PATH               Add directory to workspace (repeatable)
    --dangerously-skip-permissions  Auto-approve all tool requests
    --log-file PATH              Override agy log file path
    --print-timeout DURATION     agy-internal print timeout (e.g. 30s, 5m0s)
    --sandbox                    Run in sandbox mode

Our own flags (not forwarded):
    --id-file PATH               Save new conversation UUID to file
    --poll-interval N            DB poll interval in seconds (default: 0.3)
    --kill-timeout N             Seconds before force-killing agy process (default: 360)
"""

import argparse
import glob
import os
import subprocess
import sys
import time

import platform as _platform
if _platform.system() == 'Windows':
    CONVERSATIONS_DIR = os.path.expandvars(
        r"%USERPROFILE%\.geminintigravity-cli\conversations"
    )
    AGY_EXE = os.path.expandvars(
        r"%LOCALAPPDATA%gyingy.exe"
    )
else:
    CONVERSATIONS_DIR = os.path.expanduser(
        "~/.gemini/antigravity-cli/conversations"
    )
    AGY_EXE = os.path.expanduser("~/.local/bin/agy")


def _get_gm_count(db_path):
    """Return the number of gen_metadata rows in the DB (0 if unavailable)."""
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM gen_metadata")
        n = cur.fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


def find_response_in_db(db_path):
    """Extract model response from agy SQLite conversation DB."""
    try:
        import sqlite3
        import blackboxprotobuf
    except ImportError:
        return None

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT data FROM gen_metadata ORDER BY idx DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if not row or not row[0]:
            return None

        msg, _ = blackboxprotobuf.decode_message(row[0])

        f1 = msg.get("1", {})
        if not isinstance(f1, dict):
            return None
        f2 = f1.get("2", [])
        if not isinstance(f2, list):
            f2 = [f2]

        for entry in reversed(f2):
            if not isinstance(entry, dict):
                continue
            text = entry.get("3", "")
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")
            text = str(text).strip()
            if not text:
                continue
            if text.startswith("<USER_REQUEST>"):
                continue
            if text.startswith("Created At:"):
                continue
            if text.startswith("Completed At:"):
                continue
            return text

    except Exception:
        pass
    return None


def run_and_collect(cmd, before_dbs, conv_id_hint, use_continue, poll_interval, kill_timeout):
    """
    Run agy, wait for it to exit naturally, then read the response from the DB.

    Returns (response_text, conv_id) or raises SystemExit on failure.

    Strategy change from v1.0.6+:
    - Previously we killed agy as soon as the first gen_metadata row appeared,
      to work around the text_drip CJK busy-loop (issue #134).
    - v1.0.6 fixed that hang, so we now wait for natural exit instead.
      This is required for models that use multi-step tool calls (e.g.
      gemini-2.5-pro): killing on the first DB write would abort the run
      mid-tool-chain and return an intermediate tool result instead of the
      final model response.
    - The kill-timeout still force-kills agy if it never exits (safety net).
    """
    # On Linux, agy needs a TTY to write conversation DB entries.
    # Allocate a pseudo-TTY via pty so it behaves as in an interactive session.
    import platform as _plat2
    if _plat2.system() != "Windows":
        import pty as _pty
        _master, _slave = _pty.openpty()
        proc = subprocess.Popen(cmd, stdin=_slave, stdout=_slave, stderr=_slave)
        os.close(_slave)
    else:
        # Redirect the child's stdout to avoid duplicate output: agy v1.0.15+
        # writes its own response directly to stdout, and we separately print
        # the response read from the DB below. Without this, the same text
        # would appear twice.
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL)
    start_time = time.monotonic()  # monotonic: unaffected by NTP/system clock changes

    target_db = None
    deadline = start_time + kill_timeout
    response = None
    conv_id = conv_id_hint  # pre-filled when --conversation was given

    # For --continue: snapshot mtime of all existing DBs so we can detect
    # which one gets updated (no new file is created).
    before_mtimes = {}
    before_gm_counts = {}  # db_path -> gen_metadata count before this run
    if use_continue:
        for p in glob.glob(os.path.join(CONVERSATIONS_DIR, "*.db")):
            try:
                before_mtimes[p] = os.path.getmtime(p)
                before_gm_counts[p] = _get_gm_count(p)
            except OSError:
                pass

    # For --conversation: track existing gen_metadata count in the target DB.
    before_gm_count = 0
    if conv_id_hint:
        candidate = os.path.join(CONVERSATIONS_DIR, f"{conv_id_hint}.db")
        before_gm_count = _get_gm_count(candidate)

    # For new conversations: track ALL new DB files created during this run.
    # agy can create more than one DB file per invocation; we must poll each
    # candidate and pick the first one that receives a gen_metadata entry.
    new_dbs_seen = set()

    try:
        while time.monotonic() < deadline:
            time.sleep(poll_interval)

            # ── discover the conversation DB ─────────────────────────────
            if target_db is None:
                if conv_id_hint:
                    # --conversation ID: target DB is known upfront
                    candidate = os.path.join(CONVERSATIONS_DIR, f"{conv_id_hint}.db")
                    if os.path.exists(candidate):
                        target_db = candidate
                elif use_continue:
                    # --continue: find the DB whose mtime changed since we started
                    for p in glob.glob(os.path.join(CONVERSATIONS_DIR, "*.db")):
                        try:
                            if os.path.getmtime(p) > before_mtimes.get(p, 0):
                                target_db = p
                                conv_id = os.path.splitext(os.path.basename(p))[0]
                                before_gm_count = before_gm_counts.get(p, 0)
                                break
                        except OSError:
                            pass
                else:
                    # new conversation: accumulate ALL new DB files and poll each
                    # one — agy may create multiple DBs in one run, and the
                    # response is not necessarily in the newest file by mtime.
                    current = set(glob.glob(os.path.join(CONVERSATIONS_DIR, "*.db")))
                    new_dbs_seen |= current - before_dbs
                    for db in new_dbs_seen:
                        if _get_gm_count(db) > 0:
                            target_db = db
                            conv_id = os.path.splitext(os.path.basename(db))[0]
                            break

            # ── Linux workaround: kill as soon as DB has a new response ────
            # agy -p does not exit naturally in SSH non-interactive sessions.
            import platform as _plat
            if _plat.system() != "Windows" and target_db is not None:
                _cur_count = _get_gm_count(target_db)
                if _cur_count > before_gm_count:
                    _resp_early = find_response_in_db(target_db)
                    if _resp_early:
                        if proc.poll() is None:
                            proc.kill()
                        time.sleep(0.3)
                        return _resp_early, conv_id

            # ── wait for natural exit ─────────────────────────────────────
            if proc.poll() is not None:
                if proc.returncode != 0:
                    sys.stderr.write(f"agy exited with code {proc.returncode}\n")
                    sys.exit(proc.returncode)
                # Process exited cleanly — give DB a moment to flush writes
                time.sleep(0.5)
                if target_db:
                    # For existing DBs, verify a new entry was actually written
                    if (conv_id_hint or use_continue) and _get_gm_count(target_db) <= before_gm_count:
                        sys.stderr.write(
                            f"agy exited cleanly but no new response written to "
                            f"{os.path.basename(target_db)}.\n"
                        )
                        sys.exit(1)
                    response = find_response_in_db(target_db)
                    if response:
                        return response, conv_id
                sys.stderr.write(
                    f"agy exited cleanly but no response found in "
                    f"{os.path.basename(target_db or 'DB')}.\n"
                )
                sys.exit(1)

        # ── hard timeout: force-kill and return whatever is in the DB ─────
        sys.stderr.write(
            f"agy did not exit within {kill_timeout}s; force-killing. "
            f"(use --kill-timeout to adjust)\n"
        )
        if proc.poll() is None:
            proc.kill()
        time.sleep(0.5)
        if target_db:
            response = find_response_in_db(target_db)
            if response:
                sys.stderr.write("Returning partial response from DB after timeout.\n")
                return response, conv_id
        sys.exit(1)

    finally:
        # Always clean up the agy process, even on Ctrl+C or sys.exit().
        if proc.poll() is None:
            proc.kill()


def main():
    # ── dependency check ─────────────────────────────────────────────────────
    try:
        import blackboxprotobuf  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "Error: blackboxprotobuf is required.\n"
            "Install it with: pip install blackboxprotobuf\n"
        )
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="agy -p wrapper: runs agy non-interactively and prints the response.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── prompt ──────────────────────────────────────────────────────────────
    parser.add_argument("prompt", nargs="+", help="Prompt to send to agy")

    # ── conversation flags (forwarded to agy) ────────────────────────────────
    conv_group = parser.add_argument_group("conversation (forwarded to agy)")
    conv_group.add_argument(
        "-c", "--continue", dest="cont", action="store_true",
        help="Continue the most recent agy conversation"
    )
    conv_group.add_argument(
        "--conversation", metavar="ID",
        help="Continue a specific conversation by UUID"
    )

    # ── agy passthrough flags ────────────────────────────────────────────────
    agy_group = parser.add_argument_group("agy flags (forwarded to agy)")
    agy_group.add_argument(
        "--model", metavar="MODEL",
        help=(
            'Model to use for this session. '
            'Valid values (internal labels): '
            '"Gemini 3.5 Flash (Low)" (default), '
            '"Gemini 3.5 Flash (Medium)", '
            '"Gemini 3.5 Flash (High)". '
            'Any other value silently falls back to Medium.'
        )
    )
    agy_group.add_argument(
        "--add-dir", metavar="PATH", action="append", default=[],
        help="Add a directory to the workspace (repeatable)"
    )
    agy_group.add_argument(
        "--dangerously-skip-permissions", action="store_true",
        help="Auto-approve all tool permission requests without prompting"
    )
    agy_group.add_argument(
        "--log-file", metavar="PATH",
        help="Override agy CLI log file path"
    )
    agy_group.add_argument(
        "--print-timeout", metavar="DURATION",
        help="agy-internal print mode timeout (e.g. 30s, 2m30s). Default: 5m0s"
    )
    agy_group.add_argument(
        "--sandbox", action="store_true",
        help="Run agy in sandbox with terminal restrictions enabled"
    )

    # ── our own flags (not forwarded) ────────────────────────────────────────
    our_group = parser.add_argument_group("wrapper-only flags (not forwarded)")
    our_group.add_argument(
        "--id-file", metavar="PATH",
        help="Save the new conversation UUID to this file"
    )
    our_group.add_argument(
        "--poll-interval", type=float, default=0.3, metavar="SECONDS",
        help="How often to check the DB for a response (default: 0.3)"
    )
    our_group.add_argument(
        "--kill-timeout", type=int, default=360, metavar="SECONDS",
        help="Seconds before force-killing the agy process (default: 360)"
    )

    args = parser.parse_args()
    prompt = " ".join(args.prompt)

    # ── build agy command ────────────────────────────────────────────────────
    cmd = [AGY_EXE]

    if args.conversation:
        cmd += ["--conversation", args.conversation]
    elif args.cont:
        cmd.append("--continue")

    for d in args.add_dir:
        cmd += ["--add-dir", d]

    if args.model:
        cmd += ["--model", args.model]
    if args.dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    if args.sandbox:
        cmd.append("--sandbox")
    if args.log_file:
        cmd += ["--log-file", args.log_file]
    if args.print_timeout:
        cmd += ["--print-timeout", args.print_timeout]

    cmd += ["-p", prompt]

    # ── snapshot DB state before running ─────────────────────────────────────
    before_dbs = set(glob.glob(os.path.join(CONVERSATIONS_DIR, "*.db")))

    # ── run agy and collect response via DB polling ───────────────────────────
    response, conv_id = run_and_collect(
        cmd=cmd,
        before_dbs=before_dbs,
        conv_id_hint=args.conversation,
        use_continue=args.cont,
        poll_interval=args.poll_interval,
        kill_timeout=args.kill_timeout,
    )

    # ── emit conversation ID for new conversations ────────────────────────────
    if not args.conversation and not args.cont:
        sys.stderr.write(f"CONV_ID: {conv_id}\n")
        if args.id_file:
            with open(args.id_file, "w") as f:
                f.write(conv_id)

    # ── print response ────────────────────────────────────────────────────────
    sys.stdout.buffer.write((response + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
