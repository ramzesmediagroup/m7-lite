# Changelog

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
