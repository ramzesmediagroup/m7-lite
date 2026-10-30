"""install.sh on a temporary HOME and a temporary project (no real config is touched)."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import FILLED_TASK, REPO, TASK_REL, read

INSTALL = os.path.join(REPO, "install.sh")

FOREIGN = {
    "permissions": {"allow": ["Bash(git status)"]},
    "hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
                                                      "command": "/opt/other/lint.sh"}]}],
        "PostToolUse": [{"matcher": "Write", "hooks": [{"type": "command",
                                                        "command": "/opt/other/fmt.sh"}]}],
    },
}


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="m7inst-"))
        self.home = os.path.join(self.tmp, "home")
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.home)
        os.makedirs(os.path.join(self.proj, "app"))
        self.env = dict(os.environ, HOME=self.home)
        self.env.pop("CODEX_HOME", None)
        self.env.pop("CLAUDE_PROJECT_DIR", None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def install(self, *args):
        res = subprocess.run(["bash", INSTALL] + list(args), env=self.env,
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        return res.stdout

    def write_json(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    def load(self, path):
        return json.loads(read(path))

    def m7_commands(self, config, event="PreToolUse"):
        cmds = []
        for group in config.get("hooks", {}).get(event, []):
            for h in group.get("hooks", []):
                if "m7-lite/m7_" in h.get("command", ""):
                    cmds.append(h["command"])
        return cmds

    def call_hook(self, command, payload, extra_env=None):
        # The agent runs the configured command through a shell, as here.
        env = dict(self.env, **(extra_env or {}))
        res = subprocess.run(["bash", "-c", command], env=env, input=json.dumps(payload),
                             capture_output=True, text=True)
        self.assertNotIn("can't open file", res.stderr)
        return res.returncode, res.stderr

    def set_task(self, status):
        path = os.path.join(self.proj, TASK_REL)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(FILLED_TASK.format(status=status, goahead='user: "go"'))
        os.makedirs(os.path.join(self.proj, ".m7"), exist_ok=True)
        with open(os.path.join(self.proj, ".m7", "active"), "w") as fh:
            fh.write(TASK_REL + "\n")

    def test_claude_project_cycle(self):
        settings = os.path.join(self.proj, ".claude", "settings.json")
        self.write_json(settings, FOREIGN)
        self.install("--target", "claude", "--project", self.proj)
        out = self.install("--target", "claude", "--project", self.proj)
        self.assertIn("unchanged", out)  # idempotent

        cfg = self.load(settings)
        self.assertEqual(len(self.m7_commands(cfg)), 1)
        self.assertEqual(cfg["permissions"], FOREIGN["permissions"])
        self.assertEqual(cfg["hooks"]["PostToolUse"], FOREIGN["hooks"]["PostToolUse"])
        self.assertIn(FOREIGN["hooks"]["PreToolUse"][0], cfg["hooks"]["PreToolUse"])
        self.assertEqual(self.load(settings + ".bak")["hooks"]["PreToolUse"][0],
                         FOREIGN["hooks"]["PreToolUse"][0])
        self.assertTrue(os.path.isfile(os.path.join(self.proj, ".claude", "skills", "m7-lite",
                                                    "SKILL.md")))

        command = self.m7_commands(cfg)[0]
        env = {"CLAUDE_PROJECT_DIR": self.proj}
        edit = {"hook_event_name": "PreToolUse", "cwd": self.proj, "tool_name": "Edit",
                "tool_input": {"file_path": os.path.join(self.proj, "app", "main.py"),
                               "old_string": "a", "new_string": "b"}}
        self.assertEqual(self.call_hook(command, edit, env)[0], 0)  # mode off
        self.set_task("DISCOVERY")
        code, err = self.call_hook(command, edit, env)
        self.assertEqual(code, 2)
        self.assertIn("Status: IMPLEMENT", err)
        self.set_task("IMPLEMENT")
        self.assertEqual(self.call_hook(command, edit, env)[0], 0)

        self.assertEqual(len(self.m7_commands(cfg, "SessionStart")), 1)
        self.assertEqual(len(self.m7_commands(cfg, "UserPromptSubmit")), 1)
        res = subprocess.run(["bash", "-c", self.m7_commands(cfg, "SessionStart")[0]],
                             env=dict(self.env, **env), capture_output=True, text=True,
                             input=json.dumps({"hook_event_name": "SessionStart",
                                               "cwd": self.proj, "source": "startup"}))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Status: IMPLEMENT", res.stdout)

        self.install("--target", "claude", "--project", self.proj, "--uninstall")
        cfg = self.load(settings)
        self.assertEqual(cfg, FOREIGN)
        self.assertFalse(os.path.exists(os.path.join(self.proj, ".claude", "m7-lite")))
        self.assertFalse(os.path.exists(os.path.join(self.proj, ".claude", "skills", "m7-lite")))
        self.assertTrue(os.path.isfile(os.path.join(self.proj, TASK_REL)))

    def test_claude_user_level_new_settings(self):
        self.install("--target", "claude")
        settings = os.path.join(self.home, ".claude", "settings.json")
        cfg = self.load(settings)
        cmd = self.m7_commands(cfg)[0]
        self.assertIn(self.home, cmd)
        self.assertEqual(cfg["hooks"]["PreToolUse"][0]["matcher"],
                         "Write|Edit|MultiEdit|NotebookEdit|Bash")
        self.install("--target", "claude", "--uninstall")
        self.assertEqual(self.load(settings), {})

    def test_claude_next_to_graphify_and_autonomous_plugin_hooks(self):
        # Shapes of hooks other tools register: a PreToolUse guard on searches
        # (graphify) and a Stop hook that keeps an autonomous loop going.
        neighbours = {"hooks": {
            "PreToolUse": [{"matcher": "Glob|Grep", "hooks": [
                {"type": "command", "command": "graphify hook-guard"}]}],
            "Stop": [{"hooks": [{"type": "command",
                                 "command": "python3 ~/.claude/plugins/loop/stop.py"}]}],
            "SessionStart": [{"matcher": "startup", "hooks": [
                {"type": "command", "command": "/opt/other/banner.sh"}]}],
        }}
        settings = os.path.join(self.proj, ".claude", "settings.json")
        self.write_json(settings, neighbours)
        for _ in range(2):
            self.install("--target", "claude", "--project", self.proj)
        cfg = self.load(settings)
        for event in ("PreToolUse", "SessionStart", "UserPromptSubmit"):
            self.assertEqual(len(self.m7_commands(cfg, event)), 1, event)
        for event, groups in neighbours["hooks"].items():
            for group in groups:
                self.assertIn(group, cfg["hooks"][event])
        self.install("--target", "claude", "--project", self.proj, "--uninstall")
        self.assertEqual(self.load(settings), neighbours)

    def test_claude_upgrade_from_0_1_0_config(self):
        settings = os.path.join(self.proj, ".claude", "settings.json")
        old = {"hooks": {"PreToolUse": [
            FOREIGN["hooks"]["PreToolUse"][0],
            {"matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash", "hooks": [{
                "type": "command", "timeout": 10,
                "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/m7-lite/m7_hook.py\""}]}]}}
        self.write_json(settings, old)
        self.install("--target", "claude", "--project", self.proj)
        cfg = self.load(settings)
        for event in ("PreToolUse", "SessionStart", "UserPromptSubmit"):
            self.assertEqual(len(self.m7_commands(cfg, event)), 1, event)
        self.assertEqual(cfg["hooks"]["PreToolUse"][0], FOREIGN["hooks"]["PreToolUse"][0])
        self.assertNotIn("matcher", cfg["hooks"]["SessionStart"][0])

    def test_codex_project_cycle(self):
        hooks = os.path.join(self.proj, ".codex", "hooks.json")
        foreign = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "/opt/other/check.sh"}]}]}}
        self.write_json(hooks, foreign)
        self.install("--target", "codex", "--project", self.proj)
        self.install("--target", "codex", "--project", self.proj)
        cfg = self.load(hooks)
        self.assertEqual(len(self.m7_commands(cfg)), 1)
        self.assertEqual(sorted(cfg["hooks"]), ["PreToolUse"])
        self.assertTrue(os.path.isfile(os.path.join(self.proj, ".agents", "skills", "m7-lite",
                                                    "SKILL.md")))

        command = self.m7_commands(cfg)[0]
        patch = {"hook_event_name": "PreToolUse", "cwd": self.proj, "tool_name": "apply_patch",
                 "tool_input": {"command": "*** Begin Patch\n*** Update File: app/main.py\n"
                                           "@@\n-a\n+b\n*** End Patch\n"}}
        self.set_task("PLAN")
        self.assertEqual(self.call_hook(command, patch)[0], 2)
        self.set_task("IMPLEMENT")
        self.assertEqual(self.call_hook(command, patch)[0], 0)

        self.install("--target", "codex", "--project", self.proj, "--uninstall")
        self.assertEqual(self.load(hooks), foreign)

    def test_codex_home_respected(self):
        self.env["CODEX_HOME"] = os.path.join(self.tmp, "codexhome")
        self.install("--target", "codex")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "codexhome", "hooks.json")))
        self.assertTrue(os.path.isfile(os.path.join(self.home, ".agents", "skills", "m7-lite",
                                                    "SKILL.md")))

    def test_invalid_json_is_not_overwritten(self):
        settings = os.path.join(self.proj, ".claude", "settings.json")
        os.makedirs(os.path.dirname(settings))
        with open(settings, "w") as fh:
            fh.write("{broken")
        res = subprocess.run(["bash", INSTALL, "--target", "claude", "--project", self.proj],
                             env=self.env, capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(read(settings), "{broken")

    def test_bad_arguments(self):
        res = subprocess.run(["bash", INSTALL, "--target", "vim"], env=self.env,
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 64)


if __name__ == "__main__":
    unittest.main()
