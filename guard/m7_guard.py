#!/usr/bin/env python3
"""m7-lite guard: decides whether an agent may change project files now.

Agent-neutral and standard library only. Adapters translate their agent's hook
input into a call to decide() and translate the Decision back.

Rules (see core/METHOD.md, rule R1):
- The mode is on only if <project>/.m7/active exists and names the task file.
- Writes to docs/m7/, .m7/ and HANDOFF.md are always allowed.
- Other project writes are allowed only when the task file has Status:
  IMPLEMENT, filled DISCOVERY and PLAN + IMPACT sections and a filled
  Go-ahead: line.
- Any internal error allows the call with a warning (fail-open).
"""

import os
import re
import sys
import tempfile

ALLOW = "allow"
BLOCK = "block"

WRITE = "write"
SHELL = "shell"
OTHER = "other"

ACTIVE_FILE = os.path.join(".m7", "active")
MIN_SECTION_CHARS = 20


class Decision(object):
    def __init__(self, action, message=""):
        self.action = action
        self.message = message

    @property
    def blocked(self):
        return self.action == BLOCK

    def __repr__(self):
        return "Decision(%r, %r)" % (self.action, self.message)


def decide(tool_kind, target_paths=(), shell_command=None, project_root=".", cwd=None):
    """Return a Decision for one tool call.

    tool_kind: WRITE (file edit tools), SHELL (a shell command) or OTHER.
    target_paths: paths a WRITE call changes (absolute or relative to cwd).
    shell_command: the command string for SHELL calls.
    project_root: the project directory; relative paths and cwd resolve
        against it. The mode itself is looked up per target: the nearest
        directory above a target that has .m7/active.
    cwd: working directory of the call; defaults to project_root.
    """
    try:
        return _decide(tool_kind, target_paths, shell_command, project_root, cwd)
    except Exception as exc:  # fail-open: a broken guard must not brick a session
        return Decision(ALLOW, "m7-lite guard: internal error (%s: %s); call allowed."
                        % (type(exc).__name__, exc))


def _decide(tool_kind, target_paths, shell_command, project_root, cwd):
    if tool_kind not in (WRITE, SHELL):
        return Decision(ALLOW)
    root = os.path.realpath(project_root or ".")
    base = os.path.realpath(os.path.join(root, cwd)) if cwd else root
    unresolved = []
    if tool_kind == WRITE:
        targets = [_resolve(p, base) for p in (target_paths or ()) if p]
    else:
        targets, unresolved = shell_write_targets(shell_command or "", base)
        if unresolved:
            # A write we cannot place; assume it lands in the working directory.
            targets.append(base)

    # Each target belongs to the nearest enclosing project that has .m7/active,
    # so a session started in a parent directory still sees the project's mode.
    by_root = {}
    for t in targets:
        m7_root = active_root(t)
        if m7_root:
            by_root.setdefault(m7_root, []).append(t)
    warnings = []
    for m7_root in sorted(by_root):
        d = _decide_root(m7_root, by_root[m7_root], unresolved)
        if d.blocked:
            return d
        if d.message:
            warnings.append(d.message)
    return Decision(ALLOW, "\n".join(warnings))


def active_root(path):
    """Nearest directory at or above path that contains .m7/active, or None."""
    cur = path
    while True:
        if os.path.isfile(os.path.join(cur, ACTIVE_FILE)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _decide_root(root, targets, unresolved):
    protected = sorted(set(t for t in targets if not _allowed_zone(t, root)))
    if not protected:
        return Decision(ALLOW)

    with open(os.path.join(root, ACTIVE_FILE), encoding="utf-8", errors="replace") as fh:
        rel = next((ln.strip() for ln in fh if ln.strip()), "")
    if not rel:
        return Decision(ALLOW, "m7-lite guard: %s is empty; mode treated as off." % ACTIVE_FILE)
    task_path = os.path.realpath(os.path.join(root, rel))
    if not _inside(task_path, root) or not os.path.isfile(task_path):
        return Decision(ALLOW, "m7-lite guard: task file '%s' named in %s not found; "
                               "call allowed." % (rel, ACTIVE_FILE))

    with open(task_path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    missing, status = check_task(text)
    if not missing:
        return Decision(ALLOW)

    shown = [os.path.relpath(t, root) for t in protected[:5]]
    lines = [
        "m7-lite: blocked a change to project files (%s) before Status: IMPLEMENT."
        % ", ".join(shown),
        "Task file: %s (Status: %s)." % (rel, status or "missing"),
        "Missing:",
    ]
    lines += ["  - " + m for m in missing]
    if unresolved:
        lines.append("Could not resolve write target(s): %s. Use a literal path if it is "
                     "outside the project." % ", ".join(unresolved[:3]))
    lines += [
        "What to do: finish DISCOVERY and PLAN + IMPACT in the task file, get the user's "
        "explicit go-ahead in chat and quote it in the Go-ahead: line (or record the "
        "autonomous self-check), then set Status: IMPLEMENT (rule R1).",
        "Allowed now: reading, read-only commands, writes to docs/m7/, .m7/, HANDOFF.md. "
        "Only the user can turn the mode off (\"m7: stop\").",
    ]
    return Decision(BLOCK, "\n".join(lines))


# ---------------------------------------------------------------- task file

_STATUS_RE = re.compile(r"^[ \t>*_-]*Status[*_]*[ \t]*:[ \t*_]*([A-Za-z]+)", re.M)
_GOAHEAD_RE = re.compile(r"^[ \t>*_-]*Go-ahead[*_]*[ \t]*:(.*)$", re.M | re.I)
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t#]*$")
_COMMENT_RE = re.compile(r"<!--.*?(-->|\Z)", re.S)
_PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME)\b")
_WORDCHAR_RE = re.compile(r"[^\W_]", re.U)


def check_task(text):
    """Return (missing, status): what prevents project edits, and the status."""
    clean = _COMMENT_RE.sub("", text)
    m = _STATUS_RE.search(clean)
    status = m.group(1).upper() if m else ""
    missing = []
    if status == "DONE":
        missing.append("the task is DONE; start a new m7 task for further changes")
    elif status != "IMPLEMENT":
        missing.append("Status: IMPLEMENT (current: %s)" % (status or "no Status: line"))
    sections = _sections(clean)
    if _filled_chars(sections.get("DISCOVERY", "")) < MIN_SECTION_CHARS:
        missing.append("DISCOVERY section is empty or template text only")
    if _filled_chars(sections.get("PLAN", "")) < MIN_SECTION_CHARS:
        missing.append("PLAN + IMPACT section is empty or template text only")
    g = _GOAHEAD_RE.search(clean)
    value = g.group(1).strip() if g else ""
    if not g or _PLACEHOLDER_RE.search(value) or len(_WORDCHAR_RE.findall(value)) < 3:
        missing.append("Go-ahead: line (quote of the user's go-ahead, or the autonomous "
                       "self-check)")
    return missing, status


def _sections(text):
    """Map DISCOVERY / PLAN to the body under the first matching heading."""
    lines = text.splitlines()
    found = {}
    for i, line in enumerate(lines):
        h = _HEADING_RE.match(line)
        if not h:
            continue
        title = h.group(2)
        for key in ("DISCOVERY", "PLAN"):
            if key in found or not re.search(r"\b%s\b" % key, title, re.I):
                continue
            level = len(h.group(1))
            body = []
            for nxt in lines[i + 1:]:
                h2 = _HEADING_RE.match(nxt)
                if h2 and len(h2.group(1)) <= level:
                    break
                body.append(nxt)
            found[key] = "\n".join(body)
    return found


def _filled_chars(body):
    """Count letters/digits a human wrote, ignoring headings, labels, TODOs."""
    total = 0
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or _PLACEHOLDER_RE.search(s):
            continue
        s = re.sub(r"^(?:[>*+-]|\d+[.)])[ \t]*", "", s)
        s = re.sub(r"^\[[ xX]\][ \t]*", "", s)
        s = s.replace("**", "").replace("__", "")
        label = re.match(r"^[^:]{1,40}:(.*)$", s)
        if label:
            s = label.group(1)
        total += len(_WORDCHAR_RE.findall(s))
    return total


# ---------------------------------------------------------------- paths

def _resolve(path, base):
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(base, path)
    return os.path.realpath(path)


def _inside(path, root):
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def _allowed_zone(path, root):
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    if rel == "HANDOFF.md":
        return True
    for zone in ("docs/m7", ".m7"):
        if rel == zone or rel.startswith(zone + "/"):
            return True
    return False


def find_project_root(start):
    """Nearest directory at or above start that has .m7/ or .git; else start."""
    start = os.path.realpath(start or ".")
    cur = start
    while True:
        if os.path.isdir(os.path.join(cur, ".m7")) or os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return start
        cur = parent


# ---------------------------------------------------------------- shell

_REDIR_RE = re.compile(r"(\d*)(&>>|&>|>>|>\||>&|>|<<<|<<-|<<|<&|<>|<)")
_CTRL_OPS = ("&&", "||", ";;", "|&", ";", "|", "&", "(", ")", "{", "}")
_WORD_STOP = set(" \t\n;&|()<>")


class _Tok(object):
    __slots__ = ("kind", "value", "raw")

    def __init__(self, kind, value, raw=None):
        self.kind = kind    # "word", "op", "redir"
        self.value = value  # word text / operator / redirect operator
        self.raw = raw      # redirect target word


def _read_word(s, i, subs):
    """Read one shell word starting at i. Returns (text, end, unresolved_flag)."""
    out = []
    dynamic = False
    n = len(s)
    while i < n and s[i] not in _WORD_STOP:
        c = s[i]
        if c == "\\" and i + 1 < n:
            if s[i + 1] != "\n":
                out.append(s[i + 1])
            i += 2
        elif c == "'":
            j = s.find("'", i + 1)
            j = n if j == -1 else j
            out.append(s[i + 1:j])
            i = j + 1
        elif c == '"':
            i += 1
            while i < n and s[i] != '"':
                if s[i] == "\\" and i + 1 < n:
                    out.append(s[i + 1])
                    i += 2
                elif s.startswith("$(", i):
                    end = _match_paren(s, i + 1)
                    subs.append(s[i + 2:end])
                    out.append("$(...)")
                    dynamic = True
                    i = end + 1
                elif s[i] == "`":
                    j = s.find("`", i + 1)
                    j = n if j == -1 else j
                    subs.append(s[i + 1:j])
                    dynamic = True
                    i = j + 1
                else:
                    if s[i] == "$":
                        dynamic = True
                    out.append(s[i])
                    i += 1
            i += 1
        elif s.startswith("$(", i):
            end = _match_paren(s, i + 1)
            subs.append(s[i + 2:end])
            out.append("$(...)")
            dynamic = True
            i = end + 1
        elif c == "`":
            j = s.find("`", i + 1)
            j = n if j == -1 else j
            subs.append(s[i + 1:j])
            dynamic = True
            i = j + 1
        else:
            if c == "$":
                dynamic = True
            out.append(c)
            i += 1
    return "".join(out), i, dynamic


def _match_paren(s, i):
    """s[i] == '('; return index of the matching ')' (or len(s))."""
    depth = 0
    quote = None
    n = len(s)
    while i < n:
        c = s[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "\\":
            i += 1
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _tokenize(s, subs):
    toks = []
    heredocs = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t":
            i += 1
            continue
        if c == "\\" and s.startswith("\\\n", i):
            i += 2
            continue
        if c == "#":
            j = s.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "\n":
            toks.append(_Tok("op", ";"))
            i += 1
            for delim, strip_tabs in heredocs:
                while i < n:
                    j = s.find("\n", i)
                    line = s[i:] if j == -1 else s[i:j]
                    i = n if j == -1 else j + 1
                    if (line.lstrip("\t") if strip_tabs else line) == delim:
                        break
            heredocs = []
            continue
        if s.startswith(("<(", ">("), i):
            end = _match_paren(s, i + 1)
            subs.append(s[i + 2:end])
            toks.append(_Tok("word", "/dev/fd/63"))
            i = end + 1
            continue
        m = _REDIR_RE.match(s, i)
        if m and (m.group(1) == "" or i == 0 or s[i - 1] in " \t\n;&|()"):
            op = m.group(2)
            i = m.end()
            while i < n and s[i] in " \t":
                i += 1
            word, i, dynamic = _read_word(s, i, subs)
            if op in ("<<", "<<-"):
                heredocs.append((word, op == "<<-"))
            elif op in (">&", "<&") and (word.isdigit() or word == "-"):
                pass  # file descriptor duplication, e.g. 2>&1
            elif op.startswith(">") or op.startswith("&>") or op == "<>":
                toks.append(_Tok("redir", op, ("$" + word) if dynamic and "$" not in word else word))
            continue
        for op in _CTRL_OPS:
            if s.startswith(op, i):
                if op in ("{", "}") and not (i + 1 >= n or s[i + 1] in " \t\n;"):
                    continue
                toks.append(_Tok("op", op))
                i += len(op)
                break
        else:
            word, i, dynamic = _read_word(s, i, subs)
            if dynamic and "$" not in word:
                word = "$" + word
            toks.append(_Tok("word", word))
    return toks


_WRAPPERS = {"sudo", "env", "nohup", "time", "nice", "ionice", "command", "builtin",
             "exec", "stdbuf", "timeout", "doas", "then", "do", "else", "!", "if",
             "while", "until"}
_WRAPPER_VALUE_OPTS = {"sudo": {"-u", "-g", "-C", "-h", "-p"}, "nice": {"-n"},
                       "ionice": {"-c", "-n"}, "env": {"-u", "-C"}, "timeout": {"-s", "-k"}}
_WRITERS_ALL_ARGS = {"rm", "rmdir", "unlink", "shred", "touch", "truncate", "mkdir", "mv",
                     "tee"}
_WRITERS_LAST_ARG = {"cp", "install", "ln", "rsync"}
_VALUE_OPTS = {"truncate": {"-s", "-r"}, "mkdir": {"-m"}, "install": {"-m", "-o", "-g"},
               "tee": set(), "cp": {"-S"}, "mv": {"-S"}, "ln": {"-S"}}
_GIT_WORKTREE = {"apply", "am", "checkout", "switch", "restore", "reset", "stash", "clean",
                 "merge", "rebase", "pull", "cherry-pick", "revert", "rm", "mv"}


def shell_write_targets(command, cwd):
    """Return (targets, unresolved) for obvious file writes in a command.

    targets: absolute paths the command writes to or deletes.
    unresolved: write targets that depend on variables or substitutions.
    """
    targets, unresolved = [], []
    _analyze(command, cwd, targets, unresolved, depth=0)
    return targets, unresolved


def _analyze(command, cwd, targets, unresolved, depth):
    if depth > 4 or not command:
        return
    subs = []
    toks = _tokenize(command, subs)
    for sub in subs:
        _analyze(sub, cwd, targets, unresolved, depth + 1)
    words = []
    for tok in toks + [_Tok("op", ";")]:
        if tok.kind == "word":
            words.append(tok.value)
        elif tok.kind == "redir":
            _add_target(tok.raw, cwd, targets, unresolved)
        else:
            if words:
                cwd = _simple_command(words, cwd, targets, unresolved, depth)
            words = []


def _add_target(word, cwd, targets, unresolved):
    if word is None or word == "":
        return
    if word.startswith("$HOME"):
        word = "~" + word[5:]
    elif word.startswith("${HOME}"):
        word = "~" + word[7:]
    if word.startswith(("$TMPDIR", "${TMPDIR")):
        word = tempfile.gettempdir()
    if "$" in word:
        unresolved.append(word)
        return
    targets.append(_resolve(word, cwd))


def _strip_wrappers(words):
    while words:
        w = words[0]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):
            words = words[1:]
            continue
        if w not in _WRAPPERS:
            break
        value_opts = _WRAPPER_VALUE_OPTS.get(w, set())
        words = words[1:]
        while words and (words[0].startswith("-") or (w == "env" and "=" in words[0])):
            if words[0] in value_opts:
                words = words[1:]
            words = words[1:]
        if w == "timeout" and words:
            words = words[1:]  # duration
    return words


def _operands(args, value_opts=()):
    out = []
    i = 0
    end_opts = False
    while i < len(args):
        a = args[i]
        if not end_opts and a == "--":
            end_opts = True
        elif not end_opts and a.startswith("-") and a != "-":
            if a in value_opts:
                i += 1
        else:
            out.append(a)
        i += 1
    return out


def _simple_command(words, cwd, targets, unresolved, depth):
    """Record write targets of one simple command; return the cwd after it."""
    words = _strip_wrappers(list(words))
    if not words:
        return cwd
    cmd = os.path.basename(words[0])
    args = words[1:]
    add = lambda w: _add_target(w, cwd, targets, unresolved)

    if cmd in ("cd", "pushd"):
        ops = _operands(args)
        dest = ops[0] if ops else "~"
        if "$" in dest or dest == "-":
            return cwd
        return _resolve(dest, cwd)
    if cmd in ("bash", "sh", "zsh", "dash") and "-c" in args:
        idx = args.index("-c")
        if idx + 1 < len(args):
            _analyze(args[idx + 1], cwd, targets, unresolved, depth + 1)
        return cwd
    if cmd == "eval":
        _analyze(" ".join(args), cwd, targets, unresolved, depth + 1)
        return cwd
    if cmd == "xargs":
        inner = _xargs_inner(args)
        if inner:
            before = len(targets) + len(unresolved)
            _simple_command(inner, cwd, targets, unresolved, depth + 1)
            if _is_writer(inner) and len(targets) + len(unresolved) == before:
                targets.append(cwd)
        return cwd
    if cmd == "find":
        _find_targets(args, cwd, targets, unresolved, depth)
        return cwd
    if cmd == "git":
        _git_targets(args, cwd, targets)
        return cwd

    if cmd in _WRITERS_ALL_ARGS:
        for op in _operands(args, _VALUE_OPTS.get(cmd, ())):
            add(op)
    elif cmd in _WRITERS_LAST_ARG:
        if "-t" in args and args.index("-t") + 1 < len(args):
            add(args[args.index("-t") + 1])
        else:
            ops = _operands(args, _VALUE_OPTS.get(cmd, ()))
            if len(ops) >= 2:
                add(ops[-1])
    elif cmd == "dd":
        for a in args:
            if a.startswith("of="):
                add(a[3:])
    elif cmd == "sed" and _sed_in_place(args):
        files = _script_operands(args, script_opts=("-e", "--expression", "-f", "--file"),
                                 value_opts=("-l", "--line-length"))
        for f in files or ["."]:
            add(f)
    elif cmd == "perl" and any(re.match(r"^-[a-zA-Z]*i", a) for a in args):
        files = _script_operands(args, script_opts=("-e", "-E"), value_opts=("-I", "-M"))
        for f in files or ["."]:
            add(f)
    elif cmd == "patch" and "--dry-run" not in args:
        targets.append(cwd)
    return cwd


def _is_writer(words):
    words = _strip_wrappers(list(words))
    if not words:
        return False
    cmd = os.path.basename(words[0])
    if cmd == "sed":
        return _sed_in_place(words[1:])
    return cmd in _WRITERS_ALL_ARGS or cmd in _WRITERS_LAST_ARG


def _sed_in_place(args):
    for a in args:
        if a == "--":
            break
        if a == "--in-place" or a.startswith("--in-place="):
            return True
        if a.startswith("-") and not a.startswith("--"):
            cluster = a[1:]
            for ch in cluster:
                if ch == "i":
                    return True
                if ch in "efl":  # option with a value; rest of cluster is the value
                    break
    return False


def _script_operands(args, script_opts, value_opts):
    """Operands of sed/perl after dropping the script (first operand if no -e)."""
    files = []
    have_script = False
    i = 0
    while i < len(args):
        a = args[i]
        if a in script_opts:
            have_script = True
            i += 2
            continue
        if any(a.startswith(o + "=") for o in script_opts if o.startswith("--")):
            have_script = True
        elif a in value_opts:
            i += 1
        elif a.startswith("-") and a != "-":
            if re.match(r"^-[A-Za-z]*e$", a) and not a.startswith("--"):
                have_script = True
                i += 2
                continue
        else:
            files.append(a)
        i += 1
    if not have_script and files:
        files = files[1:]
    return files


def _xargs_inner(args):
    value_opts = {"-I", "-i", "-n", "-P", "-d", "-L", "-l", "-s", "-a", "-E", "-e"}
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] in value_opts:
            i += 1
        i += 1
    return args[i:]


def _find_targets(args, cwd, targets, unresolved, depth):
    starts = []
    i = 0
    while i < len(args) and not args[i].startswith(("-", "(", "!")):
        starts.append(args[i])
        i += 1
    starts = starts or ["."]
    rest = args[i:]
    hit = "-delete" in rest
    j = 0
    while j < len(rest):
        if rest[j] in ("-exec", "-execdir", "-ok", "-okdir"):
            k = j + 1
            inner = []
            while k < len(rest) and rest[k] not in (";", "+"):
                inner.append(rest[k].replace("{}", starts[0]))
                k += 1
            if inner and (_is_writer(inner) or os.path.basename(inner[0]) == "perl"):
                hit = True
            j = k
        j += 1
    if hit:
        for st in starts:
            _add_target(st, cwd, targets, unresolved)


def _git_targets(args, cwd, targets):
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] == "-C" and i + 1 < len(args):
            cwd = _resolve(args[i + 1], cwd)
            i += 1
        elif args[i] in ("-c", "--git-dir", "--work-tree"):
            i += 1
        i += 1
    if i >= len(args):
        return
    sub, rest = args[i], args[i + 1:]
    if sub not in _GIT_WORKTREE:
        return
    if sub == "apply" and any(a in rest for a in ("--check", "--stat", "--numstat", "--summary")):
        return
    if sub in ("checkout", "switch") and any(a in rest for a in ("-b", "-B", "-c", "-C")):
        return
    if sub == "reset" and not any(a in rest for a in ("--hard", "--merge", "--keep")):
        return
    if sub == "stash" and rest[:1] and rest[0] in ("list", "show"):
        return
    if sub == "clean" and any(a in rest for a in ("-n", "--dry-run")):
        return
    targets.append(cwd)


def main(argv=None):
    """Debug CLI: m7_guard.py <project_root> write <path>... | shell <command>"""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 3 or argv[1] not in (WRITE, SHELL):
        sys.stderr.write("usage: m7_guard.py <project_root> write <path>... | "
                         "shell <command>\n")
        return 64
    root, kind = argv[0], argv[1]
    if kind == WRITE:
        d = decide(WRITE, argv[2:], None, root)
    else:
        d = decide(SHELL, (), " ".join(argv[2:]), root)
    print(d.action)
    if d.message:
        print(d.message)
    return 2 if d.blocked else 0


if __name__ == "__main__":
    sys.exit(main())
