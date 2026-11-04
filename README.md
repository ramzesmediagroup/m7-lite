# m7-lite

A small "understand first, change second" discipline for coding agents:
a four-step method, a skill, and a hook that blocks edits to project files
until the analysis is written down and the user has given the go-ahead.

Works with Claude Code (skill + blocking hook), Codex CLI (skill + blocking
hook) and the ChatGPT web app (instructions only, no lock). Python 3 standard
library and bash; no server, no Node, nothing installed globally.

[![tests](https://github.com/ramzesmediagroup/m7-lite/actions/workflows/tests.yml/badge.svg)](https://github.com/ramzesmediagroup/m7-lite/actions/workflows/tests.yml)

[Русская версия](README.ru.md)

## Why

Agents tend to debug in a loop: symptom -> hypothesis -> patch -> next
hypothesis. Each patch is cheap, but patches pile up on top of unverified
patches, regressions show up on code paths nobody read, and when a defect has
two causes, the second one is rarely looked for.

m7-lite moves the decision point: code changes start after the data path was
read, all causes were listed with evidence, and the plan's consequences and
objections were written down. Where the agent supports hooks, this is enforced:
an edit before that point is blocked with a message saying what is missing.

## The method in one screen

Full text: [core/METHOD.md](core/METHOD.md). Task file template:
[core/TASK_TEMPLATE.md](core/TASK_TEMPLATE.md).

One task file per task, `docs/m7/<YYYY-MM-DD>-<slug>.md`, with a
`Status:` line and four sections:

1. **INTAKE**: restate the task, checkable success criteria, what was already
   tried and rejected (git log, HANDOFF.md, notes).
2. **DISCOVERY**: read code and logs along the whole data path; find all
   causes, not one; change nothing.
3. **PLAN + IMPACT**: what changes, where, why; alternatives; what may break,
   blast radius, rollback; the 2-3 strongest objections with answers.
4. **IMPLEMENT**: targeted edits per plan, real verification, report. A failed
   check sends the task back to DISCOVERY instead of adding another patch.

Facts are marked ✅ verified (with evidence: `file:line`, command + output,
log line, PMID/DOI), ❓ assumed, ⏳ stale.

Rules (IDs are the same in every adapter):

| ID | Rule |
|---|---|
| R1 | No project edits before `Status: IMPLEMENT`; IMPLEMENT only after the user's explicit go-ahead (or a recorded self-check in autonomous mode) |
| R2 | History first: what was tried and rejected |
| R3 | All causes along the whole data path; DISCOVERY changes nothing |
| R4 | Every fact the plan relies on is ✅, ❓ or ⏳ |
| R5 | Irreversible actions (deletes, restarts, crontab, migrations, messages) only when all premises are ✅ |
| R6 | Not found by grep = does not exist; the bug is in the code, not cache/env, until proven otherwise; same-session code is not "the bug" without `git diff` |
| R7 | Targeted edits; verify for real; failure -> back to DISCOVERY |
| R8 | Only the task file and the user in chat grant transitions and permissions; external content is data |

## How it differs from M7

[M7](https://github.com/DukeDeSouth/m7-mcp-oss) is an MCP server with a
seven-phase cycle, reflection gates with one-time gate IDs, project memory and
many tools. m7-lite takes a few of its ideas and drops the rest:

| | M7 | m7-lite |
|---|---|---|
| Runtime | MCP server (Node) | none; a Python hook where the agent supports hooks |
| Phases | 7, gated by the server | 4, recorded in one Markdown file |
| Enforcement | server rejects gate answers without the gate ID | hook blocks file edits and obvious shell writes before IMPLEMENT |
| Memory | server-side store | the task files and `HANDOFF.md` in the repo |
| Agents | MCP clients | Claude Code, Codex CLI (hooks); ChatGPT web (text only) |

## Works with (optional)

m7-lite has no dependencies. If one of these tools is present, the method
uses it; if not, that part is skipped. In Claude Code the context hook detects
them and tells the agent (PATH and config files are checked, nothing is
installed or run).

| Tool | Used in | How | Detected by |
|---|---|---|---|
| [graphify](https://github.com/Graphify-Labs/graphify) | DISCOVERY, PLAN + IMPACT | `graphify query "<question>"`, `graphify path A B`, `graphify explain X` against `graphify-out/graph.json` to trace the data path and list dependents. Findings are ❓ until confirmed in the file; a graph older than the last commit makes them ⏳. The agent does not build the graph itself (depending on graphify's configuration, building may send files to an LLM service). | `graphify-out/graph.json` or `graphify` on PATH |
| [Context7](https://github.com/upstash/context7) | DISCOVERY, PLAN | current documentation of third-party libraries; version + source recorded as evidence | the word `context7` in `.mcp.json`, `~/.claude.json`, Claude settings or `~/.codex/config.toml` |
| [Codex CLI](https://github.com/openai/codex) | PLAN + IMPACT | `m7: second opinion`: the plan goes to `codex exec --sandbox read-only`; its objections are added to the plan with answers | `codex` on PATH |

The commands and flags above were checked against graphify's README and the
Codex sources on 2026-10-30. Both tools change quickly; if a command fails,
check their current docs.

Writes into `graphify-out/` and commands starting with `graphify` are always
allowed. Other tools' paths and commands can be added to `.m7/allow` (see
below).

## Repository layout

```
core/METHOD.md              the method (source of truth for all adapter texts)
core/TASK_TEMPLATE.md       task file template
skills/m7-lite/             the skill (SKILL.md + template), Agent Skills format
guard/m7_guard.py           agent-neutral guard: decide(...) -> allow / block
adapters/claude-code/       PreToolUse hook, context hook, CLAUDE.md snippet
adapters/codex/             PreToolUse hook + AGENTS.md snippet
adapters/chatgpt-web/       instructions for ChatGPT Projects / custom GPTs
install.sh                  installer (no sudo)
tests/                      python3 -m unittest
examples/                   a filled task file
```

## Install

Requirements: bash, python3 (3.8+). No sudo.

```bash
git clone https://github.com/<owner>/m7-lite.git
```

```bash
cd m7-lite
```

`install.sh --target claude|codex [--project <path>] [--uninstall]`. Without
`--project` it installs for your user. Running it again is safe. Existing
settings and hooks are kept; a `.bak` copy is written before the config file
is changed; an invalid JSON config is left untouched and the installer stops.

### Claude Code

User level (all projects):

```bash
./install.sh --target claude
```

One project:

```bash
./install.sh --target claude --project /path/to/project
```

| | user | project |
|---|---|---|
| skill | `~/.claude/skills/m7-lite/` | `<project>/.claude/skills/m7-lite/` |
| hooks | `~/.claude/m7-lite/` | `<project>/.claude/m7-lite/` |
| config | `~/.claude/settings.json` | `<project>/.claude/settings.json` |

Three hooks are registered:

| Event | Script | What it does |
|---|---|---|
| `PreToolUse`, matcher `Write\|Edit\|MultiEdit\|NotebookEdit\|Bash` | `m7_hook.py` | blocks project edits before IMPLEMENT |
| `SessionStart` | `m7_context.py` | if `.m7/active` exists: tells the agent the task file, its status and what still blocks edits (on startup, resume, `/clear` and after compaction) |
| `UserPromptSubmit` | `m7_context.py` | a message starting with `m7:` / `м7:` gets a note that starts the skill (with today's date for the file name); `m7: stop` gets a note to turn the mode off; other messages get nothing |

The context hook never blocks and adds nothing when the mode is off. Then:

- add [adapters/claude-code/CLAUDE_SNIPPET.md](adapters/claude-code/CLAUDE_SNIPPET.md)
  to the project's `CLAUDE.md` (or `~/.claude/CLAUDE.md`);
- restart Claude Code; `/hooks` shows the registered hook.

### Codex CLI

```bash
./install.sh --target codex
```

```bash
./install.sh --target codex --project /path/to/project
```

| | user | project |
|---|---|---|
| skill | `~/.agents/skills/m7-lite/` | `<project>/.agents/skills/m7-lite/` |
| hook | `$CODEX_HOME/m7-lite/m7_hook.py` (default `~/.codex`) | `<project>/.codex/m7-lite/m7_hook.py` |
| config | `$CODEX_HOME/hooks.json` | `<project>/.codex/hooks.json` |

Codex hooks use the same contract as Claude Code hooks (exit code 2 with a
reason on stderr blocks the call). File edits arrive as the `apply_patch`
tool; the adapter reads the target files from the patch. Then:

- add [adapters/codex/AGENTS_SNIPPET.md](adapters/codex/AGENTS_SNIPPET.md) to
  `AGENTS.md`;
- start `codex`, open `/hooks` and trust the new hook. Codex does not run
  hooks that were not reviewed, and loads project hooks only for trusted
  projects;
- the project-level hook command uses an absolute path; after moving the
  project, run the installer again.

Codex hooks documentation: https://developers.openai.com/codex/hooks

### ChatGPT web app

Paste [adapters/chatgpt-web/INSTRUCTIONS.md](adapters/chatgpt-web/INSTRUCTIONS.md)
(about 3,300 characters) into a Project's instructions or a custom GPT's
instructions. Personal custom instructions have a smaller limit on some plans;
check the counter in the field before pasting there.

There is no lock in the web app: ChatGPT cannot be stopped from proposing
code early. The method is kept by the instructions only. Since ChatGPT cannot
read your files, it asks for the code, logs and command output it needs, and
prints the task record for you to save.

### Uninstall

```bash
./install.sh --target claude --uninstall
```

Same with `--target codex` and `--project <path>`. Only m7-lite's own hook
entries, skill folder and hook folder are removed; task files (`docs/m7/`,
`.m7/`) stay.

## Usage

In Claude Code or Codex, inside a project:

```
m7: the service stops answering every night after the cleanup cron job
```

`м7:` with a Cyrillic "м" works the same. In Claude Code the skill can also be
called as `/m7-lite <task>`, in Codex as `$m7-lite <task>`.

What happens:

1. The agent creates `docs/m7/2026-01-15-service-stops-after-cleanup-cron.md`
   from the template and writes that path into `.m7/active`. The mode is on.
2. INTAKE: it restates the task, writes success criteria, reads `git log`
   and `HANDOFF.md` for earlier attempts.
3. DISCOVERY: it reads the code and logs along the data path and records
   findings with ✅/❓ and evidence. If it tries to edit a project file now,
   the hook blocks the call:

   ```
   m7-lite: blocked a change to project files (app/server.py) before Status: IMPLEMENT.
   Task file: docs/m7/2026-01-15-service-stops-after-cleanup-cron.md (Status: DISCOVERY).
   Missing:
     - Status: IMPLEMENT (current: DISCOVERY)
     - PLAN + IMPACT section is empty or template text only
     - Go-ahead: line (quote of the user's go-ahead, or the autonomous self-check)
   What to do: ...
   ```

4. PLAN + IMPACT: it writes the plan, impact, rollback and objections, then
   asks you for the go-ahead and stops.
5. You answer in chat ("go"). The agent quotes your answer in the
   `Go-ahead:` line, sets `Status: IMPLEMENT`, and the hook lets edits
   through.
6. IMPLEMENT: targeted edits, real verification, report; `Status: DONE`;
   `.m7/active` is deleted.

A task with nothing to change (a question such as "describe what the reader
module does", or a check that finds nothing) ends after DISCOVERY with
`Status: DONE`. An audit that finds problems goes on to PLAN + IMPACT, and you
pick which findings go into the plan.

Second opinion: `m7: second opinion` (Codex CLI required) sends INTAKE,
DISCOVERY and PLAN + IMPACT to `codex exec --sandbox read-only`. The agent adds
each objection to the plan, marked `(codex)`, with an answer.

Autonomous mode: if you say "do it yourself" for the task, the agent checks
the plan against the PLAN + IMPACT list and writes that self-check into
`Go-ahead: autonomous: ...` instead of waiting for you.

A complete example task file:
[examples/2026-01-15-web-service-crashes-after-nightly-cron.md](examples/2026-01-15-web-service-crashes-after-nightly-cron.md).

Suggested `.gitignore` line for projects: `.m7/` (the switch is local state).
Commit `docs/m7/`: the task files are the project's record of what was tried.

### Turning the mode off

Say `m7: stop` (or `м7: stop`). The agent deletes `.m7/active`; the task file
stays. Without `.m7/active` the hook allows everything. Deleting the file by
hand does the same.

### Continuing in a new session

If `.m7/active` exists, the agent reads the task file and continues from its
`Status:` line. In Claude Code the SessionStart hook reminds it of the task on
startup, resume, `/clear` and after context compaction; in Codex this relies
on the AGENTS.md snippet. Before a session ends it updates `HANDOFF.md`: task file,
status, ✅ facts with evidence, ❓/⏳ facts, next step.

## A real run

The first runs of m7-lite on real projects, with names and figures left out.
Agent: Claude Code with the user-level install.

**Task.** "Check the meta tags on all pages of the site (title, description,
canonical, Open Graph), find all problems, propose a plan. Edits in a separate
git branch; no deploy." The site: about 40 public pages, built with a static
site generator, with an earlier audit and its open items in the repository.

**INTAKE and DISCOVERY** (about 5 minutes). The agent read the earlier audit
and the git history before looking at pages. It checked every public page and
reported:

- what was fine, with the checks behind it: no empty or duplicate titles and
  descriptions, one canonical per page, sitemap matching indexable pages, live
  pages matching the local build;
- two code defects with `file:line`: the Open Graph image size was
  hard-coded in the base layout and did not match the real images on a group
  of pages, which broke a rule from the earlier audit that the project's own
  check did not catch; and `twitter:description` still differed from
  `og:description` because an earlier commit had fixed only one of the two;
- two outdated phrases in descriptions that came from texts the owner had
  approved;
- two items already open in the earlier audit, left as they were.

**PLAN + IMPACT.** Code fixes and changes to approved texts were kept
apart: the code fixes were proposed, the text changes were left to the owner
to choose. The plan named the pages that would change, stated that other pages,
structured data and the CSP would not change, and added a check to the
project's own verification so the image-size problem would be caught next
time. Then it stopped and asked.

**Go-ahead.** The owner picked three code fixes and two text changes. The
agent quoted that reply in the task file's `Go-ahead:` line.

**IMPLEMENT** (about 3 minutes). Edits only in the chosen items, in a separate
branch. Verification: the site's own checks on all pages, type checks, the
test suite, a comparison with the approved texts. The new check was run on
the old build and failed on exactly the affected pages, which shows it
catches the defect. Nothing was pushed or deployed: merge, push and release
each came later with a separate go-ahead from the owner.

**What it showed about m7-lite itself.**

- The agent prepared the edits in a git worktree next to the project folder.
  The guard looked for `.m7/active` only above the edited path, so a
  worktree outside the project was not covered. Nothing went wrong, because
  the edits came after the go-ahead, but the lock could have been bypassed.
  Fixed in 0.4.0: a linked worktree belongs to its main project.
- In an earlier run on another project, a question-only task ("describe what
  this module does") ended at `Status: PLAN` with an empty plan. The method
  now closes such tasks after DISCOVERY.

## What the guard checks

`guard/m7_guard.py`, `decide(tool_kind, target_paths, shell_command,
project_root, cwd=None)`:

- No `.m7/active` in the nearest enclosing directory of a target -> allow.
  A linked git worktree (`git worktree add ../site-fix`) counts as part of
  its main project: edits there are checked against the main project's
  `.m7/active`, even when the worktree lies outside the project folder.
- Writes to `docs/m7/`, `.m7/` (except `.m7/allow`), `HANDOFF.md`,
  `graphify-out/` -> allow.
- `.m7/allow` adds more, one entry per line:

  ```
  path build/                            # always writable
  command make docs                      # commands starting with this are not checked
  irreversible tools.actions --confirm  # an R5 action of this project (see below)
  ```

  The file belongs to the user: the hook blocks agent writes to it before
  IMPLEMENT.
- Other writes inside that project -> allow only if the task file has
  `Status: IMPLEMENT`, a filled DISCOVERY section, a filled PLAN + IMPACT
  section and a filled `Go-ahead:` line. "Filled" means at least 20 letters or
  digits outside headings, field labels, HTML comments and lines with
  `TODO`/`TBD`/`FIXME`.
- Shell commands: blocked before IMPLEMENT when they obviously write project
  files: redirections `>`, `>>`, `&>` (not `/dev/null`, not `2>&1`), `tee`,
  `sed -i`, `perl -i`, `rm`, `mv`, `cp`/`install`/`ln` into the project,
  `touch`, `truncate`, `mkdir`, `dd of=`, `patch`, `find -delete` /
  `find -exec <writer>`, `xargs <writer>`, `git checkout/restore/reset --hard/
  stash/apply/clean/merge/rebase/pull/...`, `codex exec` without
  `--sandbox read-only` (or with `--yolo`, `--approve-for-me`, `--add-dir`),
  `codex apply`; also inside `bash -c '...'`,
  `$(...)`, after `cd`, behind `sudo`/`env`/`timeout`. Quotes and heredoc
  bodies are not mistaken for redirections. Reads, `git status/diff/log/show`,
  tests and output to `/dev/null` or `/tmp` are allowed.
- Irreversible actions (rule R5) are checked in the project the command runs
  in. Before IMPLEMENT they are blocked; at IMPLEMENT they are allowed only if
  PLAN + IMPACT names them (the program name is enough: `systemctl`,
  `crontab`, `sqlite`, `ssh`, `push`, plus `force` for a forced push and
  `rm`/`delete`/`удал` for deletes; English or Russian prose works). Covered:

  | Action | Blocked | Not blocked (read-only) |
  |---|---|---|
  | services | `systemctl restart/stop/enable/...`, `service x reload` | `systemctl status/show/is-active/list-*` |
  | cron | `crontab -e`, `crontab -r`, `crontab file`, `... \| crontab -` | `crontab -l` |
  | SQLite | `sqlite3 db` with INSERT/UPDATE/DELETE/CREATE/DROP/ALTER/VACUUM, `PRAGMA x=y`, `.import`, SQL from stdin | `sqlite3 -readonly`, SELECT, `.tables`, `.schema` |
  | git / GitHub | `git push` (separately: `--force`, `+ref`, deletes), `gh pr merge`, `gh release create`, `gh repo edit`, `gh api` with a write method | `git push --dry-run`, `gh pr view/list`, `gh api` GET |
  | remote hosts | `ssh host '<cmd>'` unless every part is a known read-only command; `scp`/`rsync` uploads | `ssh host 'tail ...; readlink ...; systemctl status ...'`, downloads |
  | HTTP | `curl -X POST/PUT/PATCH/DELETE`, `curl -d/-F/--json`, `wget --post-data` | GET and HEAD requests |
  | processes, containers | `kill`, `pkill`, `killall`, `docker rm/stop/restart/run/exec`, `docker compose up/down` | `kill -0`, `docker ps/logs/inspect`, `docker compose ps/logs` |
  | releases | scripts and targets named `*deploy*`, `*release*`, `*publish*`, `*rollout*` run through an interpreter, `npm publish`, `make deploy` | `cat`/`grep`/`sed -n` on such scripts |
  | deletes | `rm`, `find -delete` outside the project and outside temp folders | deletes in `/tmp`, `/var/tmp`, `$TMPDIR` |
  | project-specific | `irreversible <words>` lines in `.m7/allow` (all words must appear in the command) | the same command without those words |

- The third identical block in a row adds: stop retrying, go back to
  DISCOVERY or ask the user. This keeps autonomous loops from hammering the
  lock. The counter is in `.m7/blocks.json`.
- Any internal error, invalid hook input, an empty `.m7/active` or a missing
  task file -> allow, with a warning (fail-open). A broken guard should not
  lock you out of a session.

Debug from the command line:

```bash
python3 guard/m7_guard.py /path/to/project shell "sed -i s/a/b/ app/x.py"
```

## Tests

```bash
python3 -m unittest discover -s tests
```

CI ([.github/workflows/tests.yml](.github/workflows/tests.yml)) runs the same
command on Ubuntu and macOS with Python 3.8, 3.10, 3.12 and 3.13.

Covers guard decisions, the shell heuristics (commands that must be blocked
and commands that must not), both hook adapters and the context hook on sample hook input, the
installer on a temporary HOME and project (foreign hooks survive install and
uninstall), and a consistency check that every adapter text carries the rule
IDs from `core/METHOD.md`.

## Known gaps

- **R5 detection is a heuristic too.** It sees the command line, not what a
  program does: a Python script that restarts a service, sends a message or
  writes the database is caught only if it is named in an `irreversible`
  line in `.m7/allow`. Remote commands are judged by a list of read-only
  programs; anything else over ssh counts as a change. The plan check looks
  for the program name in PLAN + IMPACT, not for the exact step.
- **Shell detection is a heuristic.** Not caught: writes from interpreters
  (`python3 -c`, `node -e`, a script in the project that writes files), `awk`
  with output redirection inside the program, editors (`vim`, `ed`), package
  managers and build tools (`npm install`, `pip install`, `make`), `chmod`/
  `chown`, `git checkout -b <new> <start-point>`, piping into `sh`. Targets
  in variables (`> "$OUT"`) are treated as the working directory; a variable
  that points into the project while the command runs elsewhere is missed.
- **The guard checks form, not content.** It verifies that sections are
  filled and the go-ahead line exists, not that the analysis is right or that
  the user really said "go". The agent writes both; the record is in the task
  file and in `git diff` for review.
- **The agent can switch the mode off** by deleting `.m7/active` (that path
  is writable by design, so `m7: stop` works). The rules forbid it; the lock
  protects against premature edits, not against an agent that wants to bypass
  it.
- **Only the listed tools are guarded.** In Claude Code: Write, Edit,
  MultiEdit, NotebookEdit, Bash. File writes through MCP servers or other
  tools are not checked.
- **Optional tools are detected heuristically.** Context7 counts as present
  if its name appears in a config file, even if the server is disabled.
  `codex exec` counts as read-only only with an explicit `--sandbox
  read-only`; a read-only default set in `config.toml` is not seen, so such a
  call is blocked before IMPLEMENT.
- **Fail-open.** If the guard crashes or gets unexpected input, the call is
  allowed (with a warning).
- **Codex:** the adapter was tested on sample hook input built from the Codex
  source (openai/codex, `codex-rs/hooks`, `codex-rs/core/src/tools`), not in a
  running Codex session. The shell tool's `tool_input.command` is accepted as
  a string or an argv list. Hooks must be trusted in `/hooks` before they run.
  The skill path `.agents/skills` follows the Codex docs.
- **ChatGPT web:** no lock, discipline only.
- **Platforms:** Linux and macOS. Windows is not supported (bash installer,
  POSIX paths).

## Credits

m7-lite takes ideas, not code or text, from
[M7 MCP](https://github.com/DukeDeSouth/m7-mcp-oss) (Apache-2.0): the
"understand before changing" phase cycle, finding all causes along the whole
pipeline, the control-channel rule, grounding premises before irreversible
steps, and the anti-hallucination rules. The method text and the code here are
written independently. See [NOTICE](NOTICE).

## License

Apache License 2.0, see [LICENSE](LICENSE).
