"""Rule R5: irreversible actions are blocked before IMPLEMENT and must be in the plan."""

import unittest

from helpers import Project, m7_guard

SHELL = m7_guard.SHELL

TASK = """# m7 task: job errors

Status: {status}
Created: 2026-01-15
Go-ahead: user, 2026-01-15: "go"

## 2. DISCOVERY

- Findings: ✅ jobs.py:277 lets ConnectionError escape; ✅ job-cron.sh:15 maps
  exit 1 to "log in again".

## 3. PLAN + IMPACT

- Changes: jobs.py exit codes, job-cron.sh timeout and alert rules.
- Rollback: git revert of one commit.
{irreversible}
"""


class R5(unittest.TestCase):
    BLOCK = [
        "sudo systemctl restart worker",
        "systemctl --user restart bot.service",
        "service nginx reload",
        "crontab -r",
        "crontab /tmp/new.cron",
        "echo '15 0 * * * x' | crontab -",
        "sqlite3 data/app.db 'DELETE FROM messages WHERE id < 10'",
        "sqlite3 data/app.db \"update chats set archived = 1\"",
        "sqlite3 data/app.db 'PRAGMA journal_mode=WAL'",
        "sqlite3 data/app.db < migrate.sql",
        "sqlite3 data/app.db .import rows.csv t",
        "git push origin main",
        "git push --force origin fix",
        "git push -f",
        "git push origin +main",
        "git push origin :old-branch",
        "ssh prod 'cd /var/www/site && sudo ln -sfnT releases/x current.tmp && "
        "sudo mv -T current.tmp current'",
        "ssh -i ~/.ssh/key -o IdentitiesOnly=yes user@203.0.113.5 './deploy.sh'",
        "ssh prod 'rm -rf /var/www/site/releases/old'",
        "ssh prod 'tail -n 5 /var/log/x > /tmp/copy'",
        "scp dist.tar.gz prod:/var/www/",
        "rsync -av dist/ prod:/var/www/site/",
        "curl -X POST https://api.telegram.org/bot123/sendMessage -d text=hi",
        "curl -d 'a=1' http://localhost:3000/contact",
        "curl --json '{}' https://example.com/api",
        "wget --post-data=a=1 https://example.com",
        "pkill -f app.sync",
        "kill 1234",
        "killall python3",
        "docker compose down",
        "docker restart web",
        "docker rm -f old",
        "gh pr merge 5",
        "gh release create v1.0.0",
        "gh repo edit --visibility public",
        "gh api -X DELETE repos/o/r/git/refs/heads/x",
        "./scripts/deploy.sh",
        "bash scripts/package-release.sh",
        "uv run python scripts/publish.py",
        "npm publish",
        "make deploy",
        "rm -rf /var/backups/site-old",
        "find /srv/old -name '*.log' -delete",
    ]
    ALLOW = [
        "systemctl status worker",
        "systemctl --user list-timers",
        "systemctl is-active worker",
        "journalctl -u worker -n 50 --no-pager",
        "crontab -l",
        "crontab -l | grep sync",
        "sqlite3 -readonly data/app.db 'select count(*) from messages'",
        "sqlite3 data/app.db 'SELECT id, updated_at FROM chats LIMIT 5'",
        "sqlite3 data/app.db .tables",
        "sqlite3 data/app.db '.schema chats'",
        "git push --dry-run origin main",
        "git fetch origin",
        "git log origin/main..HEAD --oneline",
        "ssh prod 'tail -n 50 /var/log/nginx/error.log'",
        "ssh prod 'readlink /var/www/site/current; ls /var/www/site/releases | wc -l'",
        "ssh prod 'systemctl status nginx --no-pager'",
        "ssh prod 'curl -sI http://127.0.0.1/ 2>/dev/null | head -1'",
        "ssh -N -L 8080:localhost:80 prod",
        "scp prod:/var/log/app.log /tmp/app.log",
        "curl -sI https://example.com",
        "curl -s https://example.com | grep og:image",
        "curl -X GET https://example.com/api",
        "wget -qO- https://example.com",
        "kill -0 1234",
        "pgrep -af app.sync",
        "docker ps",
        "docker logs web --tail 50",
        "docker compose ps",
        "gh pr view 5",
        "gh pr list",
        "gh api repos/o/r",
        "cat scripts/deploy.sh",
        "grep -n deploy scripts/*.sh",
        "sed -n '1,40p' scripts/package-release.sh",
        "rm -rf /tmp/m7-scratch",
        "uv run python -m tools.actions archive 123",
        "uv run pytest -q tests/test_jobs.py",
    ]

    def setUp(self):
        self.p = Project()
        self.p.write(".m7/allow", "irreversible tools.actions --confirm\n")

    def tearDown(self):
        self.p.cleanup()

    def task(self, status, irreversible=""):
        self.p.activate(TASK.format(status=status, irreversible=irreversible))

    def sh(self, cmd):
        return m7_guard.decide(SHELL, (), cmd, self.p.root)

    def test_no_mode_allows_everything(self):
        for cmd in ("sudo systemctl restart worker", "git push --force", "crontab -r"):
            self.assertFalse(self.sh(cmd).blocked, cmd)

    def test_blocked_before_implement(self):
        self.task("DISCOVERY")
        for cmd in self.BLOCK + ["uv run python -m tools.actions archive 123 --confirm"]:
            with self.subTest(cmd=cmd):
                d = self.sh(cmd)
                self.assertTrue(d.blocked, "expected block: %r" % cmd)
                self.assertIn("rule R5", d.message)

    def test_read_only_forms_allowed(self):
        self.task("DISCOVERY")
        for cmd in self.ALLOW:
            with self.subTest(cmd=cmd):
                d = self.sh(cmd)
                self.assertFalse(d.blocked, "expected allow: %r -> %s" % (cmd, d.message))

    def test_block_message_points_to_read_only_forms(self):
        self.task("PLAN")
        d = self.sh("sudo systemctl restart worker")
        self.assertIn("systemctl restart", d.message)
        self.assertIn("systemctl status", d.message)
        self.assertIn("Irreversible steps", d.message)

    def test_implement_requires_the_plan_to_name_the_action(self):
        self.task("IMPLEMENT", "- Irreversible steps: none.")
        d = self.sh("sudo systemctl restart worker")
        self.assertTrue(d.blocked)
        self.assertIn("does not list", d.message)
        self.assertIn("Ask the user", d.message)

    def test_implement_with_listed_actions(self):
        self.task("IMPLEMENT", "- Irreversible steps: restart worker with systemctl "
                               "(premise ✅ unit file read); git push to origin.")
        self.assertFalse(self.sh("sudo systemctl restart worker").blocked)
        self.assertFalse(self.sh("git push origin fix/job-errors").blocked)
        self.assertTrue(self.sh("crontab /tmp/new.cron").blocked)
        d = self.sh("git push --force origin fix")
        self.assertTrue(d.blocked)
        self.assertIn("push + force", d.message)

    def test_plan_in_russian(self):
        self.task("IMPLEMENT", "- Необратимые шаги (Irreversible steps): запушить ветку "
                               "(git push), удалить старый релиз на проде через ssh "
                               "(rm каталога), перезапуск через systemctl.")
        self.assertFalse(self.sh("git push origin main").blocked)
        self.assertFalse(self.sh("ssh prod 'rm -rf /var/www/site/releases/old'").blocked)
        self.assertFalse(self.sh("rm -rf /var/backups/site-old").blocked)

    def test_project_pattern(self):
        self.task("IMPLEMENT", "- Irreversible steps: none.")
        cmd = "uv run python -m tools.actions archive 123 --confirm"
        self.assertTrue(self.sh(cmd).blocked)
        self.task("IMPLEMENT", "- Irreversible steps: run tools.actions with --confirm "
                               "for chat 123 (premise ✅ dry run output checked).")
        self.assertFalse(self.sh(cmd).blocked)
        self.assertEqual(m7_guard.load_irreversible(self.p.root),
                         [("tools.actions", "--confirm")])

    def test_done_blocks(self):
        self.task("DONE")
        self.assertTrue(self.sh("git push origin main").blocked)

    def test_deletes_inside_project_follow_file_rules(self):
        self.task("IMPLEMENT", "- Irreversible steps: none.")
        self.assertFalse(self.sh("rm -rf app/build").blocked)  # project file, plan approved

    def test_allowlisted_command_is_not_checked(self):
        self.p.write(".m7/allow", "command ssh prod ./status.sh\n")
        self.task("DISCOVERY")
        self.assertFalse(self.sh("ssh prod ./status.sh").blocked)
        self.assertTrue(self.sh("ssh prod ./deploy.sh").blocked)

    def test_repeat_notice_applies(self):
        self.task("DISCOVERY")
        for _ in range(2):
            self.sh("crontab -r")
        self.assertIn("same block 3 times", self.sh("crontab -r").message)


if __name__ == "__main__":
    unittest.main()
