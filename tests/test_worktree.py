"""Linked git worktrees belong to the m7 task of their main working tree."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import FILLED_TASK, REPO, TASK_REL, load_module, m7_guard

WRITE, SHELL = m7_guard.WRITE, m7_guard.SHELL
context = load_module("m7_context_wt",
                      os.path.join(REPO, "adapters", "claude-code", "m7_context.py"))

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


class Worktree(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="m7wt-"))
        self.main = os.path.join(self.tmp, "site")
        self.wt = os.path.join(self.tmp, "site-fix")  # next to the project, not inside
        os.makedirs(os.path.join(self.main, "src"))
        self.write(self.main, "src/Base.astro", "<meta>\n")
        self.write(self.main, ".gitignore", ".m7/\n")
        self.git(self.main, "init", "-q", "-b", "main")
        self.git(self.main, "add", "-A")
        self.git(self.main, "commit", "-q", "-m", "init")
        self.git(self.main, "worktree", "add", "-q", "-b", "fix/meta", self.wt)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, cwd, *args):
        subprocess.run(["git", "-C", cwd] + list(args), env=GIT_ENV, check=True,
                       capture_output=True)

    def write(self, base, rel, text):
        path = os.path.join(base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def set_task(self, status):
        self.write(self.main, TASK_REL, FILLED_TASK.format(status=status, goahead='user: "go"'))
        self.write(self.main, ".m7/active", TASK_REL + "\n")

    def edit(self, path, cwd=None):
        return m7_guard.decide(WRITE, [path], None, cwd or self.wt)

    def test_worktree_main_found(self):
        self.assertEqual(m7_guard.worktree_main(self.wt), self.main)
        self.assertIsNone(m7_guard.worktree_main(self.main))  # .git is a directory there

    def test_no_mode_in_main_allows_worktree_edits(self):
        self.assertFalse(self.edit(os.path.join(self.wt, "src/Base.astro")).blocked)

    def test_worktree_edit_blocked_before_implement(self):
        self.set_task("DISCOVERY")
        d = self.edit(os.path.join(self.wt, "src/Base.astro"))
        self.assertTrue(d.blocked)
        self.assertIn("site-fix/src/Base.astro", d.message)
        self.assertTrue(m7_guard.decide(SHELL, (), "sed -i s/a/b/ src/Base.astro",
                                         self.wt).blocked)
        self.assertTrue(m7_guard.decide(SHELL, (), "cd ../site-fix && echo x > src/new.astro",
                                         self.main).blocked)

    def test_worktree_allowed_zones_and_reads(self):
        self.set_task("DISCOVERY")
        self.assertFalse(self.edit(os.path.join(self.wt, "docs/m7/notes.md")).blocked)
        self.assertFalse(m7_guard.decide(SHELL, (), "git diff main --stat", self.wt).blocked)

    def test_worktree_edit_allowed_at_implement(self):
        self.set_task("IMPLEMENT")
        self.assertFalse(self.edit(os.path.join(self.wt, "src/Base.astro")).blocked)

    def test_relative_gitdir(self):
        # Git can write relative gitdir paths (worktree.useRelativePaths).
        gitdir = os.path.join(self.main, ".git", "worktrees", "site-fix")
        with open(os.path.join(self.wt, ".git"), "w") as fh:
            fh.write("gitdir: " + os.path.relpath(gitdir, self.wt) + "\n")
        self.assertEqual(m7_guard.worktree_main(self.wt), self.main)
        self.set_task("PLAN")
        self.assertTrue(self.edit(os.path.join(self.wt, "src/Base.astro")).blocked)

    def test_submodule_style_git_file_is_not_a_worktree(self):
        other = os.path.join(self.tmp, "lib")
        os.makedirs(other)
        with open(os.path.join(other, ".git"), "w") as fh:
            fh.write("gitdir: " + os.path.join(self.main, ".git", "modules", "lib") + "\n")
        self.set_task("DISCOVERY")
        self.assertIsNone(m7_guard.worktree_main(other))
        self.assertFalse(self.edit(os.path.join(other, "x.py"), cwd=other).blocked)

    def test_session_in_worktree_sees_main_task(self):
        self.set_task("PLAN")
        out = context.run(json.dumps({"hook_event_name": "SessionStart", "cwd": self.wt,
                                      "source": "startup"}),
                          {"CLAUDE_PROJECT_DIR": self.wt, "PATH": self.tmp, "HOME": self.tmp})
        self.assertIn(TASK_REL, out)
        self.assertIn("Status: PLAN", out)


if __name__ == "__main__":
    unittest.main()
