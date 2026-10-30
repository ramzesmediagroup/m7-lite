#!/usr/bin/env python3
"""m7-lite PreToolUse hook for Claude Code.

Reads the hook JSON from stdin, asks guard/m7_guard.py, and answers with the
Claude Code hook contract (https://code.claude.com/docs/en/hooks):
- exit 2 + reason on stderr: the tool call is blocked, Claude sees the reason;
- exit 0 + {"systemMessage": ...} on stdout: allowed, warning shown to the user;
- exit 0 and no output: allowed.

Any error inside this script allows the call (fail-open).
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for candidate in (HERE, os.path.join(HERE, "..", "..", "guard")):
    if os.path.isfile(os.path.join(candidate, "m7_guard.py")):
        sys.path.insert(0, os.path.abspath(candidate))
        break

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash"}


def translate(payload):
    """Map Claude Code hook input to guard arguments (kind, paths, command, cwd)."""
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()
    if tool in WRITE_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        return "write", [path] if path else [], None, cwd
    if tool in SHELL_TOOLS:
        return "shell", [], tool_input.get("command") or "", cwd
    return "other", [], None, cwd


def run(stdin_text, env=None):
    """Return (exit_code, stdout_text, stderr_text) for one hook call."""
    env = os.environ if env is None else env
    try:
        import m7_guard
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        kind, paths, command, cwd = translate(payload)
        root = env.get("CLAUDE_PROJECT_DIR") or m7_guard.find_project_root(cwd)
        decision = m7_guard.decide(kind, paths, command, root, cwd=cwd)
    except Exception as exc:
        msg = "m7-lite hook: internal error (%s: %s); call allowed." % (type(exc).__name__, exc)
        return 0, json.dumps({"systemMessage": msg}), ""
    if decision.blocked:
        return 2, "", decision.message + "\n"
    if decision.message:
        return 0, json.dumps({"systemMessage": decision.message}), ""
    return 0, "", ""


def main():
    try:
        data = sys.stdin.read()
    except Exception:
        data = ""
    code, out, err = run(data)
    if out:
        sys.stdout.write(out + "\n")
    if err:
        sys.stderr.write(err)
    return code


if __name__ == "__main__":
    sys.exit(main())
