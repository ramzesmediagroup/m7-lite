# Changelog

## 0.3.0 - 2026-10-30

- Optional integrations, used only when present: graphify (graph queries in
  DISCOVERY and IMPACT; graph findings ❓ until checked in the source, ⏳ when
  the graph predates the last commit), Context7 (library docs as evidence),
  Codex CLI (`m7: second opinion`: read-only review of the plan).
- Guard: `.m7/allow` for extra paths and command prefixes (defaults:
  `graphify-out/`, `graphify`); agent writes to `.m7/allow` are blocked before
  IMPLEMENT; `codex exec` without `--sandbox read-only`, or with `--yolo`,
  `--approve-for-me`, `--add-dir`, and `codex apply` count as project changes;
  the third identical block in a row tells the agent to stop retrying.
- Context hook: lists detected tools; handles `m7: second opinion`.
- Method: evidence may be a documentation page with the library version;
  derived indexes are not evidence; section "Optional tools".

## 0.2.0 - 2026-10-30

- Claude Code: context hook `m7_context.py` for `SessionStart` (reminds the
  agent of the active task, its status and what blocks edits, also after
  compaction) and `UserPromptSubmit` (a message starting with `m7:` / `м7:`
  reliably starts the skill; `m7: stop` turns the mode off).
- Guard: agent-neutral `parse_trigger()`, `mode_summary()`, `prompt_context()`.
- `install.sh`: registers several hook events; upgrading from 0.1.0 replaces
  the old entry without duplicates; uninstall removes m7-lite entries from all
  events.
- CI on GitHub Actions: Ubuntu and macOS, Python 3.8 / 3.10 / 3.12 / 3.13.
- Minimum Python is 3.8 (verified), not 3.7.

## 0.1.0 - 2026-10-30

First release.

- Method: four steps (INTAKE, DISCOVERY, PLAN + IMPACT, IMPLEMENT), fact
  statuses ✅/❓/⏳, rules R1-R8 (`core/METHOD.md`), task file template.
- Skill `m7-lite` in the Agent Skills format (Claude Code, Codex CLI).
- Guard (`guard/m7_guard.py`, Python 3 stdlib): blocks project file writes and
  obvious shell writes before `Status: IMPLEMENT`; fail-open on errors.
- Hook adapters for Claude Code and Codex CLI (PreToolUse); snippets for
  `CLAUDE.md` and `AGENTS.md`; instructions for the ChatGPT web app.
- `install.sh` for user or project level, with config merge, `.bak` backup
  and `--uninstall`.
- Tests: guard decisions, shell heuristics, adapters, installer, consistency
  of rule IDs across adapter texts.
