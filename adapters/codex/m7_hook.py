#!/usr/bin/env python3
"""m7-lite PreToolUse hook for Codex CLI.

Codex hooks follow the same contract as Claude Code hooks. Sources (openai/codex,
main branch, read 2026-10-30):
- codex-rs/protocol/src/hooks.rs: hooks.json shape {"hooks": {"PreToolUse":
  [{"matcher": ..., "hooks": [{"type": "command", "command": ..., "timeout": ...}]}]}}
- codex-rs/core/src/tools/hook_names.rs: file edits arrive as tool "apply_patch"
  (matcher aliases "Write", "Edit"); shell commands as tool "Bash".
- codex-rs/core/src/tools/handlers/apply_patch.rs: tool_input = {"command": <patch>}.
- codex-rs/hooks/src/events/pre_tool_use.rs: exit 2 with a reason on stderr blocks
  the call; a JSON "systemMessage" becomes a warning.
User docs: https://developers.openai.com/codex/hooks

Any error inside this script allows the call (fail-open).
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for candidate in (HERE, os.path.join(HERE, "..", "..", "guard")):
    if os.path.isfile(os.path.join(candidate, "m7_guard.py")):
        sys.path.insert(0, os.path.abspath(candidate))
        break

PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to):\s*(.+?)\s*$",
                           re.M)
SHELL_TOOLS = {"Bash", "shell", "exec_command", "local_shell"}


def patch_paths(patch):
    """Files an apply_patch envelope adds, updates, deletes or moves to."""
    return PATCH_FILE_RE.findall(patch or "")


def shell_text(command):
    """Shell tool input may be a string or an argv list (e.g. bash -lc '...')."""
    if isinstance(command, list):
        parts = [str(p) for p in command]
        if len(parts) >= 3 and os.path.basename(parts[0]) in ("bash", "sh", "zsh") \
                and parts[1] in ("-c", "-lc", "-ic"):
            return parts[2]
        import shlex
        return " ".join(shlex.quote(p) for p in parts)
    return command or ""


def translate(payload):
    """Map Codex hook input to guard arguments (kind, paths, command, cwd)."""
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()
    if tool in ("apply_patch", "Write", "Edit"):
        patch = tool_input.get("command") or tool_input.get("input") or ""
        if isinstance(patch, list):
            patch = "\n".join(str(p) for p in patch)
        return "write", patch_paths(patch), None, cwd
    if tool in SHELL_TOOLS:
        return "shell", [], shell_text(tool_input.get("command")), cwd
    return "other", [], None, cwd


def run(stdin_text, env=None):
    """Return (exit_code, stdout_text, stderr_text) for one hook call."""
    try:
        import m7_guard
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        kind, paths, command, cwd = translate(payload)
        root = m7_guard.find_project_root(cwd)
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
