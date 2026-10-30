#!/usr/bin/env python3
"""m7-lite context hook for Claude Code: SessionStart and UserPromptSubmit.

- SessionStart (startup, resume, clear, compact): if .m7/active exists, tell
  the agent which task is active, its status and what still blocks edits, so
  the task survives a new session or a context compaction.
- UserPromptSubmit: a message starting with "m7:" / "м7:" gets a note that
  starts the m7-lite skill; "m7: stop" gets a note to turn the mode off.

For both events Claude Code adds plain stdout to the agent's context
(https://code.claude.com/docs/en/hooks). This hook never blocks: it always
exits 0, and any error only means no context is added.
"""

import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for candidate in (HERE, os.path.join(HERE, "..", "..", "guard")):
    if os.path.isfile(os.path.join(candidate, "m7_guard.py")):
        sys.path.insert(0, os.path.abspath(candidate))
        break


def run(stdin_text, env=None, today=None):
    """Return the text to print (may be empty)."""
    env = os.environ if env is None else env
    try:
        import m7_guard
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict):
            return ""
        cwd = payload.get("cwd") or os.getcwd()
        root = env.get("CLAUDE_PROJECT_DIR") or m7_guard.find_project_root(cwd)
        event = payload.get("hook_event_name")
        if event == "SessionStart":
            return m7_guard.mode_summary(root)
        if event == "UserPromptSubmit":
            today = today or datetime.date.today().isoformat()
            return m7_guard.prompt_context(root, payload.get("prompt") or "", today)
    except Exception:
        return ""
    return ""


def main():
    try:
        data = sys.stdin.read()
    except Exception:
        data = ""
    out = run(data)
    if out:
        sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
