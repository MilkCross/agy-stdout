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

Flags forwarded to agy:
    -c / --continue              Continue most recent conversation
    --conversation ID            Continue specific conversation by UUID
    --add-dir PATH               Add directory to workspace (repeatable)
    --dangerously-skip-permissions  Auto-approve all tool requests
    --log-file PATH              Override agy log file path
    --print-timeout DURATION     agy-internal print timeout (e.g. 30s, 5m0s)
    --sandbox                    Run in sandbox mode

Our own flags (not forwarded):
    --id-file PATH               Save new conversation UUID to file
    --kill-timeout N             Seconds before force-killing agy process (default: 360)
"""

import argparse
import glob
import os
import subprocess
import sys
import time

CONVERSATIONS_DIR = os.path.expandvars(
    r"%USERPROFILE%\.gemini\antigravity-cli\conversations"
)
AGY_EXE = os.path.expandvars(
    r"%LOCALAPPDATA%\agy\bin\agy.exe"
)


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


def main():
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
        "--kill-timeout", type=int, default=360, metavar="SECONDS",
        help="Seconds before force-killing the agy process (default: 360)"
    )

    args = parser.parse_args()
    prompt = " ".join(args.prompt)

    # ── build agy command ────────────────────────────────────────────────────
    cmd = [AGY_EXE]

    # conversation flags
    if args.conversation:
        cmd += ["--conversation", args.conversation]
    elif args.cont:
        cmd.append("--continue")

    # workspace
    for d in args.add_dir:
        cmd += ["--add-dir", d]

    # boolean flags
    if args.dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    if args.sandbox:
        cmd.append("--sandbox")

    # value flags
    if args.log_file:
        cmd += ["--log-file", args.log_file]
    if args.print_timeout:
        cmd += ["--print-timeout", args.print_timeout]

    # prompt
    cmd += ["-p", prompt]

    # ── run ──────────────────────────────────────────────────────────────────
    before = set(glob.glob(os.path.join(CONVERSATIONS_DIR, "*.db")))

    try:
        result = subprocess.run(cmd, timeout=args.kill_timeout)
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"agy did not finish within {args.kill_timeout}s "
            f"(use --kill-timeout to adjust, or --print-timeout to set agy's own timeout)\n"
        )
        sys.exit(1)

    if result.returncode != 0:
        sys.stderr.write(f"agy exited with code {result.returncode}\n")
        sys.exit(result.returncode)

    # ── find the conversation DB ──────────────────────────────────────────────
    after = set(glob.glob(os.path.join(CONVERSATIONS_DIR, "*.db")))
    new_dbs = after - before

    if args.conversation:
        target_db = os.path.join(CONVERSATIONS_DIR, f"{args.conversation}.db")
        conv_id = args.conversation
    elif new_dbs:
        target_db = max(new_dbs, key=os.path.getmtime)
        conv_id = os.path.splitext(os.path.basename(target_db))[0]
    else:
        all_dbs = glob.glob(os.path.join(CONVERSATIONS_DIR, "*.db"))
        if not all_dbs:
            sys.stderr.write("No conversation DB found.\n")
            sys.exit(1)
        target_db = max(all_dbs, key=os.path.getmtime)
        conv_id = os.path.splitext(os.path.basename(target_db))[0]

    # emit conversation ID for new conversations
    if new_dbs:
        sys.stderr.write(f"CONV_ID: {conv_id}\n")
        if args.id_file:
            with open(args.id_file, "w") as f:
                f.write(conv_id)

    time.sleep(0.5)

    # ── extract and print response ────────────────────────────────────────────
    response = find_response_in_db(target_db)
    if response:
        sys.stdout.buffer.write((response + "\n").encode("utf-8"))
    else:
        sys.stderr.write(
            f"Could not extract response from {os.path.basename(target_db)}.\n"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
