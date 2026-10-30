#!/usr/bin/env bash
# m7-lite installer. No sudo; needs bash and python3.
#
#   ./install.sh --target claude|codex [--project <path>] [--uninstall]
#
# Without --project, installs for the current user.
#
# claude, user:     ~/.claude/skills/m7-lite, ~/.claude/m7-lite, ~/.claude/settings.json
# claude, project:  <p>/.claude/skills/m7-lite, <p>/.claude/m7-lite, <p>/.claude/settings.json
# codex, user:      ~/.agents/skills/m7-lite, $CODEX_HOME/m7-lite, $CODEX_HOME/hooks.json
# codex, project:   <p>/.agents/skills/m7-lite, <p>/.codex/m7-lite, <p>/.codex/hooks.json
#
# The hook is merged into the existing settings/hooks file: other hooks and
# settings are kept, a .bak copy is written before any change, and running the
# installer twice gives the same result. --uninstall removes only m7-lite's
# own entries and files; task files (docs/m7, .m7) are never touched.

set -euo pipefail

usage() {
    sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

TARGET=""
PROJECT=""
UNINSTALL=0
while [ $# -gt 0 ]; do
    case "$1" in
        --target) TARGET="${2:-}"; shift 2 ;;
        --target=*) TARGET="${1#*=}"; shift ;;
        --project) PROJECT="${2:-}"; shift 2 ;;
        --project=*) PROJECT="${1#*=}"; shift ;;
        --uninstall) UNINSTALL=1; shift ;;
        -h|--help) usage 0 ;;
        *) echo "unknown argument: $1" >&2; usage 64 ;;
    esac
done

case "$TARGET" in
    claude|codex) ;;
    *) echo "--target must be claude or codex" >&2; usage 64 ;;
esac
command -v python3 >/dev/null 2>&1 || { echo "python3 not found" >&2; exit 1; }

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"

if [ -n "$PROJECT" ]; then
    [ -d "$PROJECT" ] || { echo "project directory not found: $PROJECT" >&2; exit 1; }
    PROJECT="$(cd "$PROJECT" && pwd)"
fi

if [ "$TARGET" = claude ]; then
    ADAPTER="$SRC/adapters/claude-code/m7_hook.py"
    MATCHER="Write|Edit|MultiEdit|NotebookEdit|Bash"
    if [ -n "$PROJECT" ]; then
        SKILL_DIR="$PROJECT/.claude/skills/m7-lite"
        HOOK_DIR="$PROJECT/.claude/m7-lite"
        CONFIG="$PROJECT/.claude/settings.json"
        HOOK_CMD='python3 "$CLAUDE_PROJECT_DIR/.claude/m7-lite/m7_hook.py"'
    else
        SKILL_DIR="$HOME/.claude/skills/m7-lite"
        HOOK_DIR="$HOME/.claude/m7-lite"
        CONFIG="$HOME/.claude/settings.json"
        HOOK_CMD="python3 \"$HOOK_DIR/m7_hook.py\""
    fi
else
    ADAPTER="$SRC/adapters/codex/m7_hook.py"
    MATCHER=""  # no matcher: the hook sees every tool and ignores the ones it does not handle
    if [ -n "$PROJECT" ]; then
        SKILL_DIR="$PROJECT/.agents/skills/m7-lite"
        HOOK_DIR="$PROJECT/.codex/m7-lite"
        CONFIG="$PROJECT/.codex/hooks.json"
    else
        SKILL_DIR="$HOME/.agents/skills/m7-lite"
        HOOK_DIR="$CODEX_HOME_DIR/m7-lite"
        CONFIG="$CODEX_HOME_DIR/hooks.json"
    fi
    HOOK_CMD="python3 \"$HOOK_DIR/m7_hook.py\""
fi

# Merge or remove the m7-lite PreToolUse entry. Entries are recognised by
# "m7-lite/m7_hook.py" in their command; everything else is left as is.
merge_hook() {
    python3 -I - "$1" "$2" "$3" "$4" <<'PY'
import json, os, shutil, sys

action, path, command, matcher = sys.argv[1:5]
MARK = "m7-lite/m7_hook.py"

if os.path.exists(path):
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        sys.exit("refusing to change %s: not valid JSON (%s)" % (path, exc))
else:
    raw, data = None, {}
if not isinstance(data, dict):
    sys.exit("refusing to change %s: top level is not a JSON object" % path)

hooks = data.get("hooks")
if hooks is not None and not isinstance(hooks, dict):
    sys.exit("refusing to change %s: 'hooks' is not an object" % path)
hooks = hooks or {}
groups = hooks.get("PreToolUse") or []

def ours(handler):
    return isinstance(handler, dict) and MARK in str(handler.get("command", ""))

kept = []
for group in groups:
    if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
        kept.append(group)
        continue
    rest = [h for h in group["hooks"] if not ours(h)]
    if rest:
        if len(rest) != len(group["hooks"]):
            group = dict(group, hooks=rest)
        kept.append(group)

if action == "install":
    entry = {"hooks": [{"type": "command", "command": command, "timeout": 10}]}
    if matcher:
        entry = {"matcher": matcher, "hooks": entry["hooks"]}
    kept.append(entry)

if kept:
    hooks["PreToolUse"] = kept
else:
    hooks.pop("PreToolUse", None)
if hooks:
    data["hooks"] = hooks
else:
    data.pop("hooks", None)

new = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
if raw is not None and new == raw:
    print("unchanged: %s" % path)
    sys.exit(0)
if raw is None and action == "uninstall":
    sys.exit(0)
if raw is not None:
    shutil.copy2(path, path + ".bak")
os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
tmp = path + ".m7-lite.tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    fh.write(new)
os.replace(tmp, path)
print("%s: %s%s" % ("updated" if action == "install" else "cleaned", path,
                    " (backup: %s.bak)" % path if raw is not None else ""))
PY
}

if [ "$UNINSTALL" = 1 ]; then
    merge_hook uninstall "$CONFIG" "" ""
    for dir in "$SKILL_DIR" "$HOOK_DIR"; do
        if [ -f "$dir/.m7-lite-installed" ]; then
            rm -rf -- "$dir"
            echo "removed: $dir"
        fi
    done
    echo "m7-lite uninstalled for $TARGET${PROJECT:+ in $PROJECT}."
    exit 0
fi

mkdir -p "$SKILL_DIR" "$HOOK_DIR"
cp "$SRC/skills/m7-lite/SKILL.md" "$SRC/skills/m7-lite/TASK_TEMPLATE.md" "$SKILL_DIR/"
cp "$SRC/guard/m7_guard.py" "$HOOK_DIR/m7_guard.py"
cp "$ADAPTER" "$HOOK_DIR/m7_hook.py"
touch "$SKILL_DIR/.m7-lite-installed" "$HOOK_DIR/.m7-lite-installed"
echo "skill: $SKILL_DIR"
echo "hook:  $HOOK_DIR/m7_hook.py"
merge_hook install "$CONFIG" "$HOOK_CMD" "$MATCHER"

if [ "$TARGET" = claude ]; then
    echo "Next: add adapters/claude-code/CLAUDE_SNIPPET.md to CLAUDE.md; restart Claude Code."
else
    echo "Next: add adapters/codex/AGENTS_SNIPPET.md to AGENTS.md; start codex and trust the"
    echo "new hook in /hooks (untrusted hooks do not run; project hooks also need a trusted project)."
fi
