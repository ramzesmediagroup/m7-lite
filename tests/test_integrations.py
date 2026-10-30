"""Optional integrations: tool detection, allowlist, codex exec, repeated blocks."""

import os
import subprocess
import time
import unittest

from helpers import TASK_REL, Project, m7_guard

WRITE, SHELL = m7_guard.WRITE, m7_guard.SHELL


class ToolDetection(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.bin = self.p.path("fake-bin")
        self.home = self.p.path("fake-home")
        os.makedirs(self.bin)
        os.makedirs(self.home)
        self.env = {"PATH": self.bin, "HOME": self.home}

    def tearDown(self):
        self.p.cleanup()

    def stub(self, name):
        path = os.path.join(self.bin, name)
        with open(path, "w") as fh:
            fh.write("#!/bin/sh\nexit 0\n")
        os.chmod(path, 0o755)

    def test_nothing_installed(self):
        self.assertEqual(m7_guard.detect_tools(self.p.root, self.env), {})
        self.assertEqual(m7_guard.tools_note({}), [])

    def test_cli_tools_on_path(self):
        self.stub("graphify")
        self.stub("codex")
        tools = m7_guard.detect_tools(self.p.root, self.env)
        self.assertEqual(sorted(tools), ["codex", "graphify"])
        self.assertEqual(tools["graphify"], {"cli": True, "graph": False, "stale": None})
        note = "\n".join(m7_guard.tools_note(tools))
        self.assertIn("do not build a graph yourself", note)
        self.assertIn("m7: second opinion", note)

    def test_graph_without_cli(self):
        self.p.write("graphify-out/graph.json", "{}")
        tools = m7_guard.detect_tools(self.p.root, self.env)
        self.assertTrue(tools["graphify"]["graph"])
        note = "\n".join(m7_guard.tools_note(tools))
        self.assertIn("graphify query", note)
        self.assertIn("❓ until confirmed", note)

    def test_graph_older_than_last_commit_is_stale(self):
        env = dict(os.environ, HOME=self.home, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        git = lambda *a: subprocess.run(["git", "-C", self.p.root] + list(a), env=env,
                                        capture_output=True, check=True)
        git("init", "-q")
        self.p.write("app/x.py", "x = 1\n")
        git("add", "app/x.py")
        git("commit", "-q", "-m", "x")
        self.p.write("graphify-out/graph.json", "{}")
        old = time.time() - 3600
        os.utime(self.p.path("graphify-out/graph.json"), (old, old))
        tools = m7_guard.detect_tools(self.p.root, {"PATH": os.environ["PATH"],
                                                    "HOME": self.home})
        self.assertTrue(tools["graphify"]["stale"])
        self.assertIn("⏳", "\n".join(m7_guard.tools_note(tools)))
        os.utime(self.p.path("graphify-out/graph.json"), None)
        tools = m7_guard.detect_tools(self.p.root, {"PATH": os.environ["PATH"],
                                                    "HOME": self.home})
        self.assertFalse(tools["graphify"]["stale"])

    def test_context7_in_config(self):
        with open(os.path.join(self.home, ".claude.json"), "w") as fh:
            fh.write('{"mcpServers": {"context7": {"command": "npx"}}}')
        self.assertIn("context7", m7_guard.detect_tools(self.p.root, self.env))
        os.remove(os.path.join(self.home, ".claude.json"))
        self.p.write(".mcp.json", '{"mcpServers": {"Context7": {}}}')
        self.assertIn("context7", m7_guard.detect_tools(self.p.root, self.env))

    def test_tools_in_session_note(self):
        self.p.filled(status="DISCOVERY")
        self.p.write("graphify-out/graph.json", "{}")
        self.assertIn("graphify query", m7_guard.mode_summary(self.p.root, self.env))
        self.assertIn("graphify query",
                      m7_guard.prompt_context(self.p.root, "m7: new bug", "2026-01-15",
                                              self.env))

    def test_second_opinion(self):
        ctx = lambda: m7_guard.prompt_context(self.p.root, "m7: second opinion", "2026-01-15",
                                              self.env)
        self.assertIn("there is none", ctx())
        self.p.filled(status="PLAN")
        self.assertIn("not on PATH", ctx())
        self.stub("codex")
        out = ctx()
        self.assertIn("codex exec --sandbox read-only", out)
        self.assertIn(TASK_REL, out)
        self.assertIn("(codex)", out)
        self.assertIn("R8", out)
        self.assertEqual(m7_guard.parse_trigger("М7:  Second   Opinion"), ("second_opinion", ""))


class Allowlist(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.p.filled(status="DISCOVERY")

    def tearDown(self):
        self.p.cleanup()

    def sh(self, cmd):
        return m7_guard.decide(SHELL, (), cmd, self.p.root)

    def test_graphify_defaults(self):
        self.assertFalse(m7_guard.decide(WRITE, [self.p.path("graphify-out/GRAPH_REPORT.md")],
                                         None, self.p.root).blocked)
        self.assertFalse(self.sh("graphify update .").blocked)
        self.assertFalse(self.sh("graphify query 'what calls cleanup?' > graphify-out/q.txt")
                         .blocked)
        self.assertFalse(self.sh("rm -rf graphify-out/cache").blocked)
        self.assertTrue(self.sh("rm -rf graphify-outside").blocked)

    def test_allow_file(self):
        self.p.write(".m7/allow", "# extra\npath ./build/\npath ../escape\npath /etc\n"
                                  "command make docs\nnonsense line\n")
        paths, commands = m7_guard.load_allowlist(self.p.root)
        self.assertEqual(paths, ["graphify-out", "build"])
        self.assertEqual(commands, ["graphify", "make docs"])
        self.assertFalse(self.sh("rm -rf build").blocked)
        self.assertFalse(self.sh("make docs > app/docs.html").blocked)
        self.assertTrue(self.sh("make app > app/x").blocked)
        self.assertTrue(m7_guard.decide(WRITE, [self.p.path("../escape/x")], None,
                                        self.p.root).blocked is False)  # outside project

    def test_agent_cannot_widen_allowlist(self):
        self.assertTrue(m7_guard.decide(WRITE, [self.p.path(".m7/allow")], None,
                                        self.p.root).blocked)
        self.assertTrue(self.sh("echo 'path app' >> .m7/allow").blocked)
        self.assertFalse(self.sh("echo docs/m7/x.md > .m7/active").blocked)

    def test_allowlisted_command_does_not_hide_other_commands(self):
        self.assertTrue(self.sh("graphify update . && rm app/server.py").blocked)


class CodexExec(unittest.TestCase):
    BLOCK = [
        "codex exec 'fix the bug'",
        "codex e 'fix the bug'",
        "codex exec --sandbox workspace-write 'fix'",
        "codex exec -s danger-full-access 'fix'",
        "codex exec --sandbox read-only --yolo 'fix'",
        "codex exec -s read-only --dangerously-bypass-approvals-and-sandbox 'fix'",
        "codex exec -s read-only --approve-for-me 'fix'",
        "codex exec -s read-only --add-dir app 'fix'",
        "codex -m some-model exec 'fix'",
        "codex apply",
        "codex a",
        "cd app && codex exec 'fix'",
    ]
    ALLOW = [
        "codex exec --sandbox read-only 'review the plan'",
        "codex exec -s read-only - < .m7/second-opinion.md",
        "codex exec --sandbox=read-only 'review'",
        "codex exec -sread-only 'review'",
        "codex exec -c 'sandbox_mode=\"read-only\"' 'review'",
        "codex -s read-only exec 'review'",
        "codex exec --sandbox read-only --ephemeral --skip-git-repo-check -C . - < .m7/x.md",
        "codex --version",
        "codex login status",
        "codex exec -C /tmp 'fix something elsewhere'",
    ]

    def setUp(self):
        self.p = Project()
        self.p.filled(status="PLAN")

    def tearDown(self):
        self.p.cleanup()

    def test_write_capable_blocked(self):
        for cmd in self.BLOCK:
            with self.subTest(cmd=cmd):
                self.assertTrue(m7_guard.decide(SHELL, (), cmd, self.p.root).blocked)

    def test_read_only_allowed(self):
        for cmd in self.ALLOW:
            with self.subTest(cmd=cmd):
                d = m7_guard.decide(SHELL, (), cmd, self.p.root)
                self.assertFalse(d.blocked, d.message)

    def test_block_message_suggests_read_only(self):
        d = m7_guard.decide(SHELL, (), "codex exec 'fix'", self.p.root)
        self.assertIn("codex exec --sandbox read-only", d.message)

    def test_allowed_after_implement(self):
        self.p.filled(status="IMPLEMENT")
        self.assertFalse(m7_guard.decide(SHELL, (), "codex exec --yolo 'apply the plan'",
                                         self.p.root).blocked)


class RepeatedBlocks(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.p.filled(status="DISCOVERY")

    def tearDown(self):
        self.p.cleanup()

    def edit(self, rel="app/server.py"):
        return m7_guard.decide(WRITE, [self.p.path(rel)], None, self.p.root)

    def test_third_identical_block_says_stop(self):
        self.assertNotIn("times in a row", self.edit().message)
        self.assertNotIn("times in a row", self.edit().message)
        third = self.edit()
        self.assertTrue(third.blocked)
        self.assertIn("same block 3 times in a row", third.message)
        self.assertIn("go back to DISCOVERY", third.message)
        self.assertIn("4 times", self.edit().message)

    def test_different_block_resets(self):
        self.edit()
        self.edit()
        self.edit("app/other.py")
        self.assertNotIn("times in a row", self.edit().message)

    def test_progress_in_task_file_resets(self):
        self.edit()
        self.edit()
        self.p.filled(status="PLAN")  # status changed: the block message differs
        self.assertNotIn("times in a row", self.edit().message)

    def test_unwritable_state_fails_open(self):
        os.makedirs(self.p.path(".m7/blocks.json"))  # a directory: cannot be written
        for _ in range(4):
            d = self.edit()
            self.assertTrue(d.blocked)


if __name__ == "__main__":
    unittest.main()
