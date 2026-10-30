import json
import os
import subprocess
import sys
import unittest

from helpers import REPO, TASK_REL, Project, load_module, m7_guard

context = load_module("m7_context_claude",
                      os.path.join(REPO, "adapters", "claude-code", "m7_context.py"))
SCRIPT = os.path.join(REPO, "adapters", "claude-code", "m7_context.py")


class Trigger(unittest.TestCase):
    def test_start(self):
        for prompt in ("m7: bot crashes", "м7: бот падает", "M7: x", "М7:x", "  m7 : x"):
            with self.subTest(prompt=prompt):
                self.assertEqual(m7_guard.parse_trigger(prompt)[0], "start")
        self.assertEqual(m7_guard.parse_trigger("m7: bot crashes\nlog: ..."),
                         ("start", "bot crashes\nlog: ..."))
        self.assertEqual(m7_guard.parse_trigger("m7:"), ("start", ""))

    def test_stop(self):
        for prompt in ("m7: stop", "м7: stop", "M7: STOP", "m7:stop "):
            with self.subTest(prompt=prompt):
                self.assertEqual(m7_guard.parse_trigger(prompt), ("stop", ""))

    def test_not_a_trigger(self):
        for prompt in ("", "fix the bot", "see m7: later", "m77: x", "m7 x", "mm7: x"):
            with self.subTest(prompt=prompt):
                self.assertIsNone(m7_guard.parse_trigger(prompt))


class ContextHook(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        empty = self.p.path("no-tools")
        os.makedirs(empty)
        self.env = {"CLAUDE_PROJECT_DIR": self.p.root, "PATH": empty, "HOME": empty}

    def tearDown(self):
        self.p.cleanup()

    def session_start(self, source="startup"):
        return context.run(json.dumps({"session_id": "abc", "cwd": self.p.root,
                                       "hook_event_name": "SessionStart", "source": source}),
                           self.env)

    def prompt(self, text):
        return context.run(json.dumps({"session_id": "abc", "cwd": self.p.root,
                                       "permission_mode": "default",
                                       "hook_event_name": "UserPromptSubmit", "prompt": text}),
                           self.env, today="2026-01-15")

    def test_session_start_mode_off(self):
        self.assertEqual(self.session_start(), "")

    def test_session_start_after_compaction(self):
        self.p.filled(status="DISCOVERY")
        out = self.session_start("compact")
        self.assertIn(TASK_REL, out)
        self.assertIn("Status: DISCOVERY", out)
        self.assertIn("blocked until", out)

    def test_session_start_implement_ready(self):
        self.p.filled()
        out = self.session_start()
        self.assertIn("Status: IMPLEMENT", out)
        self.assertNotIn("blocked", out)

    def test_session_start_missing_task_file(self):
        self.p.write(".m7/active", "docs/m7/gone.md\n")
        self.assertIn("was not found", self.session_start())

    def test_prompt_start(self):
        out = self.prompt("м7: бот падает ночью")
        self.assertIn("docs/m7/2026-01-15-<ascii-slug>.md", out)
        self.assertIn(".m7/active", out)
        self.assertNotIn("another task", out)

    def test_prompt_start_while_other_task_active(self):
        self.p.filled(status="PLAN")
        out = self.prompt("m7: new problem")
        self.assertIn("another task is active", out)
        self.assertIn(TASK_REL, out)

    def test_prompt_start_without_description(self):
        self.assertIn("no task description", self.prompt("m7:"))

    def test_prompt_stop(self):
        self.assertIn("already off", self.prompt("m7: stop"))
        self.p.filled(status="PLAN")
        out = self.prompt("m7: stop")
        self.assertIn("Delete .m7/active", out)
        self.assertIn(TASK_REL, out)

    def test_ordinary_prompt_adds_nothing(self):
        self.p.filled(status="PLAN")
        self.assertEqual(self.prompt("what does cleanup.sh do?"), "")

    def test_bad_input(self):
        self.assertEqual(context.run("{oops", self.env), "")
        self.assertEqual(context.run("[]", self.env), "")
        self.assertEqual(context.run(json.dumps({"hook_event_name": "Stop"}), self.env), "")

    def test_as_subprocess_always_exits_zero(self):
        self.p.filled(status="DISCOVERY")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.p.root)
        for data in (json.dumps({"hook_event_name": "SessionStart", "cwd": self.p.root,
                                 "source": "startup"}), "not json", ""):
            res = subprocess.run([sys.executable, SCRIPT], env=env, input=data,
                                 capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stderr, "")
        res = subprocess.run([sys.executable, SCRIPT], env=env, capture_output=True, text=True,
                             input=json.dumps({"hook_event_name": "SessionStart",
                                               "cwd": self.p.root, "source": "startup"}))
        self.assertIn("m7-lite mode is on", res.stdout)


if __name__ == "__main__":
    unittest.main()
