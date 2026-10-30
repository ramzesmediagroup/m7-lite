# HANDOFF — m7-lite development

Last update: 2026-10-30, v0.3.0 (step 6: optional integrations).
Statuses: ✅ verified (with evidence), ❓ assumed, ⏳ stale.

## Goal

Lightweight, agent-agnostic "understand first, change second" discipline:
method + skill + a guard hook that blocks premature edits. Works in Claude
Code now; Codex CLI and ChatGPT web later. Python 3 stdlib + bash only.

## Step plan

| Step | Content | State |
|---|---|---|
| 0 | Read M7 sources, check agent docs, write this file | done |
| 1 | core/METHOD.md, core/TASK_TEMPLATE.md, skills/m7-lite/SKILL.md | done |
| 2 | guard/m7_guard.py, adapters/claude-code, tests | done |
| 3 | Codex adapter, ChatGPT web instructions, consistency test | done |
| 4 | install.sh + dry run in a temp project | done |
| 5 | README/README.ru/LICENSE/NOTICE/CHANGELOG, personal-data scan, commit | done |

## Findings from M7 (source: github.com/DukeDeSouth/m7-mcp-oss, commit 74329b2, Apache-2.0)

- ✅ M7 is an MCP server with a 7-phase cycle (INTAKE, DISCOVERY, ARCHITECTURE,
  SOLUTION, IMPACT, SIMULATION, IMPLEMENTATION) and reflection gates with a
  one-time gate ID (M7-GUIDE.md §5; src/core/orchestrator/controlChannel.ts).
- ✅ Control channel idea: phase transitions are valid only from the tool's
  result, chat claims like "gate passed" are untrusted (controlChannel.ts,
  CONTROL_CHANNEL_NOTICE).
- ✅ Grounding idea: plan steps reference premises; a premise that is not
  KNOWN/HUMAN_CONFIRMED gives a strong warning on irreversible steps, soft on
  reversible ones (groundingGate.ts, warningSeverity()).
- ✅ Rules reused as ideas: "not in grep = does not exist", "bug is in code, not
  cache/env", "do not call same-chat code a bug without git diff", targeted
  edits, "find all causes" (M7-GUIDE.md §9-10; ANTI_HALLUCINATION_CHECKLIST.md).
- ✅ Rationale: freestyle loop symptom -> hypothesis -> patch; familiarity
  illusion and premature convergence (docs/M7_WHY_FULL_CYCLE.md §1).
- m7-lite keeps 4 steps (INTAKE, DISCOVERY, PLAN + IMPACT, IMPLEMENT), one task
  file, no server; wording is our own.

## Claude Code (source: code.claude.com/docs/en/hooks.md, /skills.md, read 2026-10-30)

- ✅ PreToolUse stdin: session_id, transcript_path, cwd, permission_mode,
  hook_event_name, tool_name, tool_input, tool_use_id. Write/Edit:
  tool_input.file_path; Bash: tool_input.command.
- ✅ Exit 2 blocks the tool call; stderr is the message Claude sees. Exit 0 +
  JSON is parsed; `systemMessage` = warning shown to the user. Claude never
  sees stderr of exit 0. Other exit codes: non-blocking error.
- ✅ settings.json: {"hooks": {"PreToolUse": [{"matcher": "...", "hooks":
  [{"type": "command", "command": "...", "timeout": N}]}]}}; matcher with
  characters other than letters/digits/_/-/space/,/| is a regex; timeout in
  seconds; ${CLAUDE_PROJECT_DIR} available. Files: ~/.claude/settings.json,
  .claude/settings.json, .claude/settings.local.json.
- ✅ Hooks also fire inside subagents.
- ✅ Skills: ~/.claude/skills/<name>/SKILL.md, .claude/skills/<name>/SKILL.md;
  frontmatter optional, `description` recommended; invoke with /name or
  automatically; follows the Agent Skills open standard (agentskills.io).
- ❓ MultiEdit / NotebookEdit input shapes are not in the fetched text; the
  adapter accepts file_path and notebook_path defensively.

## Codex CLI (source: github.com/openai/codex main, Rust sources, read 2026-10-30;
developers.openai.com is not reachable from this session)

- ✅ Hooks exist and are on by default: feature key `hooks`, Stage::Stable,
  default_enabled true (codex-rs/features/src/lib.rs).
- ✅ hooks.json is read from each config folder (`config_folder.join("hooks.json")`,
  codex-rs/hooks/src/engine/discovery.rs); format is the same shape as Claude
  Code: {"hooks": {"PreToolUse": [{"matcher", "hooks": [{"type": "command",
  "command", "timeout"}]}]}} (codex-rs/protocol/src/hooks.rs, MatcherGroup,
  HookHandlerConfig). Inline [hooks] in config.toml also exists.
- ✅ File edits go through tool `apply_patch`, hook stdin tool_input =
  {"command": <patch text>}; matcher aliases "Write"/"Edit" select it
  (codex-rs/core/src/tools/hook_names.rs, handlers/apply_patch.rs:372-373).
  Shell tool hook name is "Bash".
- ✅ Blocking: exit 2 with non-empty stderr, or JSON permissionDecision "deny"
  (codex-rs/hooks/src/events/pre_tool_use.rs:248-281). systemMessage becomes
  a warning.
- ✅ Non-managed hooks run only when trusted (hash-based,
  HookTrustStatus::Trusted in discovery.rs:1000-1015).
- ❓ (search snippet of developers.openai.com/codex/hooks) Trust is given via
  `/hooks` in the CLI; project `.codex/` layer loads only for trusted projects;
  user location is `~/.codex/hooks.json`.
- ❓ (search snippet) Skills are loaded from `.agents/skills` (repo, cwd up to
  root) and `~/.agents/skills` (user); invoked with `$skill-name`
  (✅ sigil `$` in codex-rs/skills/src/mentions.rs). SKILL.md frontmatter
  name (max 64 chars) + description (✅ codex-rs/skills/src/parser.rs).
- ✅ AGENTS.md: discovered from project root down to cwd, AGENTS.override.md
  first; total budget 32 KiB (codex-rs/core/src/agents_md.rs,
  config/src/config_toml.rs DEFAULT_PROJECT_DOC_MAX_BYTES).

## ChatGPT web

- ❓ Custom GPT Instructions limit 8000 characters (community reports, not on
  help.openai.com, which is not reachable from here).
- ❓ Personalization custom instructions: 1500 (Free) / 5000 (paid) characters
  (search snippet of help.openai.com).
- ❓ Project instructions limit: not found in reachable sources.
  Decision: keep adapters/chatgpt-web/INSTRUCTIONS.md under 5000 characters
  (fits paid custom instructions and the reported 8000 GPT limit); a
  consistency test enforces the bound.

## Step 1-2 results

- ✅ core/METHOD.md defines rules R1-R8; SKILL.md carries all of them;
  skills/m7-lite/TASK_TEMPLATE.md is a copy of core/TASK_TEMPLATE.md.
- ✅ SKILL.md frontmatter: name `m7-lite`, description 371 chars.
- ✅ guard/m7_guard.py: decide(tool_kind, target_paths, shell_command,
  project_root, cwd=None); own shell tokenizer (quotes, heredoc bodies,
  $(...), cd tracking, bash -c, xargs, find -delete/-exec, git worktree
  subcommands). Task check also requires a filled `Go-ahead:` line (R1).
- ✅ adapters/claude-code/m7_hook.py and adapters/codex/m7_hook.py (Codex:
  apply_patch paths parsed from the patch envelope).
- ✅ `python3 -m unittest discover -s tests` -> 32 tests OK.
- ❓ Codex shell tool_input shape: handler source for the pre-tool payload of
  the shell tool was not found; adapter accepts a string or an argv list.
- ❓ Codex adapter not run inside a real Codex CLI (no Codex in this
  environment; Node is out of scope). Tested on sample stdin per
  pre-tool-use.command.input.schema.json fields.

## Step 3 results

- ✅ adapters/codex/AGENTS_SNIPPET.md, adapters/chatgpt-web/INSTRUCTIONS.md
  (3280 bytes, under the 5000-char bound).
- ✅ tests/test_consistency.py: every adapter text has R1-R8, both triggers,
  `m7: stop`, step names and status marks; skill template == core template;
  snippets <= 10 lines. `python3 -m unittest discover -s tests` -> 39 OK.

## Step 4 results

- ✅ install.sh --target claude|codex [--project <p>] [--uninstall]; merge via
  embedded python3, `.bak` before any change, refuses invalid JSON,
  idempotent ("unchanged" on the second run).
- ✅ Dry run in a temp git project with foreign PreToolUse/PostToolUse hooks
  and permissions: install -> mode off: Edit allowed (exit 0) -> DISCOVERY:
  Edit app/main.py blocked (exit 2, message lists 4 missing items), task file
  write allowed, `git diff` allowed, `sed -i` blocked -> IMPLEMENT with filled
  sections and go-ahead: Edit allowed -> --uninstall: settings.json equal to
  the original JSON, docs/m7 and .m7 kept. Codex: same cycle with apply_patch.
- ✅ tests/test_install.py repeats this on a temporary HOME; 46 tests OK.
- ✅ Fix found in the dry run: the mode is now looked up per target (nearest
  directory with .m7/active), so a user-level install still guards a project
  when the session starts in a parent directory (e.g. a workspace folder).
- ❓ Codex skill path `.agents/skills` (search snippet, not source).
- ❓ Codex project hook command uses an absolute path; moving the project
  needs a reinstall.
- Uninstall leaves an empty `{}` config file and empty `skills/` folders if
  the installer created them (cannot tell user-created empty files apart).

## Step 5 results

- ✅ README.md (EN), README.ru.md, LICENSE (Apache-2.0 text, copyright line
  "The m7-lite authors"), NOTICE (credit to M7), CHANGELOG.md (0.1.0),
  .gitignore, examples/ (generic nightly-cron scenario; a consistency test
  checks it is a complete task file).
- ✅ Personal-data scan (grep for names, emails, home/workspace paths, bot and
  client names, tokens, keys): no hits in tracked files. `__pycache__` files
  that slipped into earlier commits were removed from the history before
  publication.
- ✅ `python3 -m unittest discover -s tests` -> 47 tests OK.

## v0.2.0 (after 0.1.0 was pushed to the session branch)

- ✅ Claude Code SessionStart input has `source` (startup | resume | clear |
  compact | fork); UserPromptSubmit input has `prompt`; for both, plain stdout
  is added to the agent's context; UserPromptSubmit has no matcher support
  (code.claude.com/docs/en/hooks.md, read 2026-10-30).
- ✅ adapters/claude-code/m7_context.py + guard functions parse_trigger(),
  mode_summary(), prompt_context(); never blocks, exits 0.
- ✅ install.sh registers PreToolUse + SessionStart + UserPromptSubmit for
  claude (PreToolUse only for codex); m7-lite entries recognised by
  "m7-lite/m7_" in the command; upgrade from the 0.1.0 config gives no
  duplicates (tests/test_install.py).
- ✅ .github/workflows/tests.yml: Ubuntu + macOS, Python 3.8/3.10/3.12/3.13
  via uv. Same steps run locally with uv Python 3.8.20 as python3 -> OK.
- ✅ 62 tests OK on Python 3.8, 3.11, 3.12, 3.13 (local).
- ✅ First CI run on GitHub (run 41019041423, commit aa75571): all 8 jobs
  green (ubuntu-latest and macos-latest x Python 3.8/3.10/3.12/3.13).
- ❓ Context hooks not yet seen in a live Claude Code session.

## Step 6: optional integrations (v0.3.0)

- ✅ graphify CLI per its README (Graphify-Labs/graphify, master, read
  2026-10-30; safishamsi/graphify serves the same file): `graphify query`,
  `graphify path`, `graphify explain`, `graphify update .`, output
  `graphify-out/graph.json`. `graphify extract` may use an LLM backend chosen
  from API keys in the environment -> the method never builds the graph itself.
- ❓ `get_pr_impact` / `shortest_path` (named in the request) are not CLI
  commands in that README; likely tools of graphify's MCP server, whose names
  "come from the server". Not used by name.
- ✅ Codex CLI flags (openai/codex main: utils/cli/src/shared_options.rs,
  sandbox_mode_cli_arg.rs, exec/src/cli.rs, cli/src/main.rs): `-s/--sandbox
  read-only|workspace-write|danger-full-access`, `--yolo`
  (= --dangerously-bypass-approvals-and-sandbox), `--approve-for-me`
  (= --not-so-yolo, workspace-write), `-C/--cd`, `--add-dir`, `--ephemeral`,
  `--skip-git-repo-check`, prompt `-` = stdin; aliases `exec`/`e`, `apply`/`a`.
  Default sandbox comes from config -> guard needs explicit read-only.
- ✅ Guard: `.m7/allow` (defaults graphify-out/, graphify; agent cannot write
  the file before IMPLEMENT), codex exec/apply detection, repeat counter in
  `.m7/blocks.json` (3rd identical block -> "go back to DISCOVERY"),
  detect_tools() + tools_note() + `m7: second opinion` in the context hook.
- ✅ Tests: tests/test_integrations.py (detection with stub binaries and fake
  HOME, stale graph via a real git repo, allowlist, 12 blocked / 10 allowed
  codex commands, repeat counter, unwritable state fails open); install test
  next to graphify-like PreToolUse(Glob|Grep), a Stop hook and a foreign
  SessionStart hook. 81 tests OK locally.
- ❓ Not run against real graphify / Codex / Context7 installations.
- ❓ Context7 detection is a substring check in config files.

## Next step

- Live check on the VPS: install on one project, run `m7: <task>`, confirm the
  SessionStart note after `/compact` and the block at DISCOVERY.
- Candidate: R5 guard for irreversible commands (systemctl, crontab, sqlite3
  writes, migrations, git push --force) before IMPLEMENT.
- Candidate: Codex SessionStart / UserPromptSubmit (events exist in
  codex-rs/hooks; output semantics not checked yet).
- After the VPS inventory: adapter notes for the specific autonomous plugin
  in use; extra `.m7/allow` defaults if other tools write into projects.
