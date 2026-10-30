# HANDOFF — m7-lite development

Last update: 2026-10-30, after step 3.
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
| 4 | install.sh + dry run in a temp project | todo |
| 5 | README/README.ru/LICENSE/NOTICE/CHANGELOG, personal-data scan, commit | todo |

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

## Next step

Step 4: install.sh (--target claude|codex, --project <path>, --uninstall),
merge hooks via python3 with .bak backup, idempotent; dry run in a temp
project for both targets, check foreign hooks survive uninstall.
