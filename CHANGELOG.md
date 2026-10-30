# Changelog

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
