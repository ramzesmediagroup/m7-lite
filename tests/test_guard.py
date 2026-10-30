import unittest

from helpers import TASK_REL, TEMPLATE, Project, m7_guard, read

WRITE, SHELL = m7_guard.WRITE, m7_guard.SHELL


class GuardDecisions(unittest.TestCase):
    def setUp(self):
        self.p = Project()

    def tearDown(self):
        self.p.cleanup()

    def write(self, *paths):
        return m7_guard.decide(WRITE, [self.p.path(x) for x in paths], None, self.p.root)

    def sh(self, command):
        return m7_guard.decide(SHELL, (), command, self.p.root)

    def test_no_mode_allows_everything(self):
        self.assertFalse(self.write("app/server.py").blocked)
        self.assertFalse(self.sh("sed -i s/a/b/ app/server.py").blocked)

    def test_docs_m7_write_allowed(self):
        self.p.activate()
        self.assertFalse(self.write("docs/m7/2026-01-15-nightly-crash.md").blocked)
        self.assertFalse(self.write(".m7/active").blocked)
        self.assertFalse(self.write("HANDOFF.md").blocked)

    def test_code_write_in_discovery_blocked(self):
        self.p.filled(status="DISCOVERY")
        d = self.write("app/server.py")
        self.assertTrue(d.blocked)
        self.assertIn("Status: IMPLEMENT (current: DISCOVERY)", d.message)
        self.assertIn("app/server.py", d.message)
        self.assertIn("What to do", d.message)

    def test_template_only_blocked_with_all_reasons(self):
        self.p.activate()
        d = self.write("app/server.py")
        self.assertTrue(d.blocked)
        self.assertIn("DISCOVERY section is empty", d.message)
        self.assertIn("PLAN + IMPACT section is empty", d.message)
        self.assertIn("Go-ahead", d.message)

    def test_implement_with_filled_sections_allowed(self):
        self.p.filled()
        self.assertFalse(self.write("app/server.py").blocked)
        self.assertFalse(self.sh("sed -i 's/a/b/' app/server.py").blocked)

    def test_empty_sections_with_implement_blocked(self):
        text = read(TEMPLATE)
        text = text.replace("Status: INTAKE", "Status: IMPLEMENT")
        text = text.replace("Go-ahead: TODO", 'Go-ahead: user: "go"')
        self.p.activate(text)
        d = self.write("app/server.py")
        self.assertTrue(d.blocked)
        self.assertIn("DISCOVERY section is empty", d.message)
        self.assertNotIn("Status: IMPLEMENT (current", d.message)

    def test_missing_goahead_blocked(self):
        self.p.filled(goahead="TODO")
        d = self.write("app/server.py")
        self.assertTrue(d.blocked)
        self.assertIn("Go-ahead", d.message)

    def test_done_blocks(self):
        self.p.filled(status="DONE")
        d = self.write("app/server.py")
        self.assertTrue(d.blocked)
        self.assertIn("DONE", d.message)

    def test_write_outside_project_allowed(self):
        self.p.filled(status="DISCOVERY")
        self.assertFalse(m7_guard.decide(WRITE, ["/tmp/m7-scratch.txt"], None,
                                         self.p.root).blocked)

    def test_relative_path_resolved_against_cwd(self):
        self.p.filled(status="DISCOVERY")
        d = m7_guard.decide(WRITE, ["server.py"], None, self.p.root, cwd="app")
        self.assertTrue(d.blocked)

    def test_bad_input_fails_open(self):
        self.p.filled(status="DISCOVERY")
        d = m7_guard.decide(WRITE, 12345, None, self.p.root)  # not iterable
        self.assertFalse(d.blocked)
        self.assertIn("internal error", d.message)

    def test_missing_task_file_fails_open(self):
        self.p.write(".m7/active", "docs/m7/does-not-exist.md\n")
        d = self.write("app/server.py")
        self.assertFalse(d.blocked)
        self.assertIn("not found", d.message)

    def test_empty_active_fails_open(self):
        self.p.write(".m7/active", "\n")
        d = self.write("app/server.py")
        self.assertFalse(d.blocked)
        self.assertTrue(d.message)

    def test_status_with_markdown_bold(self):
        self.p.filled()
        text = read(self.p.path(TASK_REL))
        text = text.replace("Status: IMPLEMENT", "**Status:** IMPLEMENT")
        self.p.activate(text)
        self.assertFalse(self.write("app/server.py").blocked)

    def test_find_project_root(self):
        self.p.activate()
        self.assertEqual(m7_guard.find_project_root(self.p.path("app")), self.p.root)


class ShellHeuristics(unittest.TestCase):
    """Shell commands at DISCOVERY: obvious writes blocked, reads allowed."""

    BLOCK = [
        "sed -i 's/a/b/' app/server.py",
        "sed -i.bak -e 's/a/b/' app/server.py",
        "sed --in-place 's/a/b/' app/server.py",
        "sed -Ei 's/a/b/' app/server.py",
        "perl -pi -e 's/a/b/' app/server.py",
        "echo x > app/server.py",
        "echo x >> app/server.py",
        "printf x 1> app/new.txt",
        "cmd &> app/out.log",
        "echo hi | tee app/server.py",
        "echo hi | tee -a app/a app/b",
        "cat > app/config.ini <<'EOF'\n[main]\nkey = 1\nEOF",
        "mv app/a.py app/b.py",
        "mv /tmp/new.py app/server.py",
        "cp /tmp/new.py app/server.py",
        "cp -r /tmp/dir app",
        "rm -rf app",
        "rm app/server.py",
        "touch app/new.py",
        "mkdir app/sub",
        "ln -s /tmp/x app/link",
        "truncate -s 0 app/server.py",
        "dd if=/dev/zero of=app/blob bs=1 count=1",
        "cd app && echo x > server.py",
        "true; rm app/x.py",
        "ls && rm app/x.py",
        "bash -c 'echo x > app/server.py'",
        "sh -c \"sed -i s/a/b/ app/server.py\"",
        "sudo rm app/server.py",
        "FOO=1 rm app/server.py",
        "find app -name '*.pyc' -delete",
        "find app -name '*.py' -exec sed -i 's/a/b/' {} +",
        "git ls-files | xargs sed -i 's/a/b/'",
        "git checkout -- app/server.py",
        "git restore app/server.py",
        "git reset --hard HEAD",
        "git stash",
        "git apply fix.patch",
        "git clean -fd",
        "patch -p1 < fix.patch",
        "echo $(rm app/x.py)",
        "for f in app/*.py; do sed -i 's/a/b/' \"$f\"; done",
        "echo x > \"$OUT\"",
    ]

    ALLOW = [
        "cat app/server.py",
        "grep -rn 'socket' app",
        "rg -n foo app | head",
        "git status",
        "git diff",
        "git diff HEAD~1 -- app/server.py",
        "git log --oneline -20",
        "git log -p app/server.py",
        "git show HEAD:app/server.py",
        "git checkout -b fix-branch",
        "git stash list",
        "git apply --check fix.patch",
        "git clean -n",
        "git reset HEAD app/server.py",
        "python3 -m pytest -q",
        "python3 -m pytest > /dev/null 2>&1",
        "ls -la 2>/dev/null",
        "make test 2>&1 | tail -20",
        "journalctl -u svc --since today >/dev/null",
        "echo 'a > b'",
        "echo \"x > app/server.py\"",
        "echo a\\>b",
        "grep -c '>' app/server.py",
        "sed -n '1,20p' app/server.py",
        "sed 's/a/b/' app/server.py",
        "sed -e 's/i/I/' app/server.py",
        "awk '$1 > 3' app/data.txt",
        "test 1 -gt 0",
        "echo x > /tmp/m7-scratch.txt",
        "echo x > $TMPDIR/scratch.txt",
        "cp app/server.py /tmp/server.py.bak",
        "mkdir -p docs/m7 .m7",
        "echo docs/m7/2026-01-15-nightly-crash.md > .m7/active",
        "rm .m7/active",
        "tee HANDOFF.md < /dev/null",
        "cat > docs/m7/notes.md <<'EOF'\necho x > app/server.py\nrm -rf app\nEOF",
        "python3 - <<'EOF'\nprint(1 > 0)\nEOF",
        "# rm -rf app\nls",
        "find app -name '*.py'",
        "find app -name '*.py' -exec grep -l socket {} +",
        "cd /tmp && echo x > out.txt",
        "diff <(sort a) <(sort b)",
        "cmd 2>&1 >/dev/null",
        "echo x >&2",
    ]

    def setUp(self):
        self.p = Project()
        self.p.filled(status="DISCOVERY")

    def tearDown(self):
        self.p.cleanup()

    def test_obvious_writes_blocked(self):
        for cmd in self.BLOCK:
            with self.subTest(cmd=cmd):
                d = m7_guard.decide(SHELL, (), cmd, self.p.root)
                self.assertTrue(d.blocked, "expected block: %r" % cmd)

    def test_reads_allowed(self):
        for cmd in self.ALLOW:
            with self.subTest(cmd=cmd):
                d = m7_guard.decide(SHELL, (), cmd, self.p.root)
                self.assertFalse(d.blocked, "expected allow: %r -> %s" % (cmd, d.message))

    def test_unresolved_target_mentioned(self):
        d = m7_guard.decide(SHELL, (), 'echo x > "$OUT"', self.p.root)
        self.assertIn("Could not resolve", d.message)


if __name__ == "__main__":
    unittest.main()
