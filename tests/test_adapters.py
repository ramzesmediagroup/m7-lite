import json
import os
import subprocess
import sys
import unittest

from helpers import REPO, Project, load_module

claude = load_module("m7_hook_claude", os.path.join(REPO, "adapters", "claude-code", "m7_hook.py"))
codex = load_module("m7_hook_codex", os.path.join(REPO, "adapters", "codex", "m7_hook.py"))

PATCH = """*** Begin Patch
*** Update File: app/server.py
@@
-    old()
+    new()
*** End Patch
"""


def claude_input(project, tool, tool_input):
    return json.dumps({
        "session_id": "abc123",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": project.root,
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": tool_input,
        "tool_use_id": "toolu_01",
    })


def codex_input(project, tool, tool_input):
    return json.dumps({
        "session_id": "s1",
        "turn_id": "t1",
        "transcript_path": None,
        "cwd": project.root,
        "hook_event_name": "PreToolUse",
        "model": "some-model",
        "permission_mode": "default",
        "tool_name": tool,
        "tool_input": tool_input,
        "tool_use_id": "call_1",
    })


class ClaudeCodeAdapter(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.env = {"CLAUDE_PROJECT_DIR": self.p.root}

    def tearDown(self):
        self.p.cleanup()

    def run_hook(self, tool, tool_input):
        return claude.run(claude_input(self.p, tool, tool_input), self.env)

    def test_no_mode_allows(self):
        self.assertEqual(self.run_hook("Write", {"file_path": self.p.path("app/a.py"),
                                                 "content": "x"}), (0, "", ""))

    def test_edit_blocked_before_implement(self):
        self.p.filled(status="PLAN")
        code, out, err = self.run_hook("Edit", {"file_path": self.p.path("app/server.py"),
                                                "old_string": "a", "new_string": "b"})
        self.assertEqual(code, 2)
        self.assertIn("m7-lite: blocked", err)

    def test_task_file_write_allowed(self):
        self.p.filled(status="PLAN")
        code, _, _ = self.run_hook("Write", {"file_path": self.p.path(
            "docs/m7/2026-01-15-nightly-crash.md"), "content": "x"})
        self.assertEqual(code, 0)

    def test_notebook_and_bash(self):
        self.p.filled(status="DISCOVERY")
        self.assertEqual(self.run_hook("NotebookEdit", {
            "notebook_path": self.p.path("app/a.ipynb"), "new_source": "x"})[0], 2)
        self.assertEqual(self.run_hook("Bash", {"command": "sed -i s/a/b/ app/server.py",
                                                "description": "edit"})[0], 2)
        self.assertEqual(self.run_hook("Bash", {"command": "git diff"})[0], 0)
        self.assertEqual(self.run_hook("Read", {"file_path": self.p.path("app/a.py")})[0], 0)

    def test_allowed_after_implement(self):
        self.p.filled()
        self.assertEqual(self.run_hook("Write", {"file_path": self.p.path("app/a.py"),
                                                 "content": "x"})[0], 0)

    def test_bad_json_fails_open_with_warning(self):
        code, out, err = claude.run("{not json", self.env)
        self.assertEqual(code, 0)
        self.assertIn("systemMessage", json.loads(out))

    def test_project_root_from_cwd_without_env(self):
        self.p.filled(status="DISCOVERY")
        payload = json.loads(claude_input(self.p, "Write", {"file_path": "app/a.py"}))
        payload["cwd"] = self.p.path("app")
        payload["tool_input"]["file_path"] = self.p.path("app/a.py")
        self.assertEqual(claude.run(json.dumps(payload), {})[0], 2)

    def test_as_subprocess(self):
        self.p.filled(status="DISCOVERY")
        script = os.path.join(REPO, "adapters", "claude-code", "m7_hook.py")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.p.root)
        res = subprocess.run([sys.executable, script], env=env, capture_output=True, text=True,
                             input=claude_input(self.p, "Write", {
                                 "file_path": self.p.path("app/a.py"), "content": "x"}))
        self.assertEqual(res.returncode, 2)
        self.assertIn("Status: IMPLEMENT", res.stderr)
        res = subprocess.run([sys.executable, script], env=env, capture_output=True, text=True,
                             input="")
        self.assertEqual(res.returncode, 0)


class CodexAdapter(unittest.TestCase):
    def setUp(self):
        self.p = Project()

    def tearDown(self):
        self.p.cleanup()

    def run_hook(self, tool, tool_input):
        return codex.run(codex_input(self.p, tool, tool_input))

    def test_patch_paths(self):
        patch = PATCH + "*** Add File: app/new.py\n*** Delete File: old.py\n*** Move to: b.py\n"
        self.assertEqual(codex.patch_paths(patch),
                         ["app/server.py", "app/new.py", "old.py", "b.py"])

    def test_apply_patch_blocked_before_implement(self):
        self.p.filled(status="DISCOVERY")
        code, _, err = self.run_hook("apply_patch", {"command": PATCH})
        self.assertEqual(code, 2)
        self.assertIn("app/server.py", err)

    def test_apply_patch_to_task_file_allowed(self):
        self.p.filled(status="DISCOVERY")
        patch = PATCH.replace("app/server.py", "docs/m7/2026-01-15-nightly-crash.md")
        self.assertEqual(self.run_hook("apply_patch", {"command": patch})[0], 0)

    def test_apply_patch_allowed_after_implement(self):
        self.p.filled()
        self.assertEqual(self.run_hook("apply_patch", {"command": PATCH})[0], 0)

    def test_bash_string_and_argv(self):
        self.p.filled(status="DISCOVERY")
        self.assertEqual(self.run_hook("Bash", {"command": "rm app/server.py"})[0], 2)
        self.assertEqual(self.run_hook("Bash", {"command": ["bash", "-lc",
                                                            "echo x > app/a.py"]})[0], 2)
        self.assertEqual(self.run_hook("Bash", {"command": ["git", "status"]})[0], 0)

    def test_no_mode_and_bad_input(self):
        self.assertEqual(self.run_hook("apply_patch", {"command": PATCH}), (0, "", ""))
        self.assertEqual(codex.run("[]")[0], 0)


if __name__ == "__main__":
    unittest.main()
