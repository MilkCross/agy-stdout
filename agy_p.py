#!/usr/bin/env python
"""
agy_p.py — agy -p wrapper that actually prints the response to stdout.

Usage:
    python agy_p.py "your prompt here"
    python agy_p.py -c "follow-up"                    # continue last conversation
    python agy_p.py --conversation ID "follow-up"     # continue specific conversation
    python agy_p.py "first message" --id-file id.txt  # save conv ID for later

Root cause of the bug (agy v1.0.4):
    printmode_manager.go silently drops responses when PlannerResponse has no
    ModifiedResponse. The actual text is saved to the SQLite conversation DB
    (gen_metadata table) even when stdout gets nothing. This script reads it back.

Conversation ID notes:
    - New conversation: ID is printed to stderr as "CONV_ID: {uuid}"
    - Use --id-file to capture it: agy_p.py "hi" --id-file /tmp/id.txt
    - Resume later: agy_p.py --conversation $(cat /tmp/id.txt) "follow-up"
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
        description="agy -p wrapper: runs agy non-interactively and prints the response."
    )
    parser.add_argument("prompt", nargs="+", help="Prompt to send to agy")
    parser.add_argument(
        "-c", "--continue", dest="cont", action="store_true",
        help="Continue the most recent agy conversation"
    )
    parser.add_argument(
        "--conversation", metavar="ID",
        help="Continue a specific conversation by UUID"
    )
    parser.add_argument(
        "--id-file", metavar="PATH",
        help="Save the conversation ID to this file (new conversations only)"
    )
    parser.add_argument(
        "--timeout", type=int, default=120, help="Max seconds to wait (default: 120)"
    )
    args = parser.parse_args()

    prompt = " ".join(args.prompt)

    cmd = [AGY_EXE]
    if args.conversation:
        cmd += ["--conversation", args.conversation]
    elif args.cont:
        cmd.append("--continue")
    cmd += ["-p", prompt]

    before = set(glob.glob(os.path.join(CONVERSATIONS_DIR, "*.db")))

    result = subprocess.run(cmd, timeout=args.timeout)

    if result.returncode != 0:
        sys.stderr.write(f"agy exited with code {result.returncode}\n")
        sys.exit(result.returncode)

    after = set(glob.glob(os.path.join(CONVERSATIONS_DIR, "*.db")))
    new_dbs = after - before

    if args.conversation:
        # --conversation: same DB is updated, no new file
        target_db = os.path.join(CONVERSATIONS_DIR, f"{args.conversation}.db")
        conv_id = args.conversation
    elif new_dbs:
        target_db = max(new_dbs, key=os.path.getmtime)
        conv_id = os.path.splitext(os.path.basename(target_db))[0]
    else:
        # --continue or fallback: most recently modified DB
        all_dbs = glob.glob(os.path.join(CONVERSATIONS_DIR, "*.db"))
        if not all_dbs:
            sys.stderr.write("No conversation DB found.\n")
            sys.exit(1)
        target_db = max(all_dbs, key=os.path.getmtime)
        conv_id = os.path.splitext(os.path.basename(target_db))[0]

    # Emit conversation ID for new conversations
    if new_dbs:
        sys.stderr.write(f"CONV_ID: {conv_id}\n")
        if args.id_file:
            with open(args.id_file, "w") as f:
                f.write(conv_id)

    time.sleep(0.5)

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
