"""Every adapter text is derived from core/METHOD.md and must keep its rule IDs."""

import os
import re
import unittest

from helpers import REPO, m7_guard, read

ADAPTER_TEXTS = [
    "skills/m7-lite/SKILL.md",
    "adapters/claude-code/CLAUDE_SNIPPET.md",
    "adapters/codex/AGENTS_SNIPPET.md",
    "adapters/chatgpt-web/INSTRUCTIONS.md",
]
CHATGPT_MAX_CHARS = 5000


def method_rule_ids():
    return re.findall(r"^- \*\*(R\d+) ", read(os.path.join(REPO, "core", "METHOD.md")), re.M)


class Consistency(unittest.TestCase):
    def test_method_has_rules(self):
        ids = method_rule_ids()
        self.assertEqual(ids, ["R%d" % i for i in range(1, len(ids) + 1)])
        self.assertGreaterEqual(len(ids), 8)

    def test_adapters_carry_all_rule_ids(self):
        ids = method_rule_ids()
        for rel in ADAPTER_TEXTS:
            text = read(os.path.join(REPO, rel))
            for rid in ids:
                with self.subTest(file=rel, rule=rid):
                    self.assertRegex(text, r"\b%s\b" % rid)

    def test_adapters_carry_triggers_and_steps(self):
        for rel in ADAPTER_TEXTS:
            text = read(os.path.join(REPO, rel))
            for word in ("m7:", "м7:", "m7: stop", "INTAKE", "DISCOVERY", "PLAN + IMPACT",
                         "IMPLEMENT", "✅", "❓", "⏳"):
                with self.subTest(file=rel, word=word):
                    self.assertIn(word, text)

    def test_skill_template_matches_core(self):
        self.assertEqual(read(os.path.join(REPO, "skills", "m7-lite", "TASK_TEMPLATE.md")),
                         read(os.path.join(REPO, "core", "TASK_TEMPLATE.md")))

    def test_skill_frontmatter(self):
        text = read(os.path.join(REPO, "skills", "m7-lite", "SKILL.md"))
        m = re.match(r"^---\nname: ([a-z0-9-]+)\ndescription: (.+)\n---\n", text)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "m7-lite")
        self.assertLessEqual(len(m.group(2)), 1024)

    def test_chatgpt_instructions_size(self):
        text = read(os.path.join(REPO, "adapters", "chatgpt-web", "INSTRUCTIONS.md"))
        self.assertLessEqual(len(text), CHATGPT_MAX_CHARS)

    def test_examples_are_complete_task_files(self):
        folder = os.path.join(REPO, "examples")
        for name in sorted(os.listdir(folder)):
            if name.endswith(".md"):
                missing, status = m7_guard.check_task(read(os.path.join(folder, name)))
                self.assertEqual(status, "DONE", name)
                self.assertEqual(len(missing), 1, (name, missing))

    def test_snippets_are_short(self):
        for rel in ("adapters/claude-code/CLAUDE_SNIPPET.md", "adapters/codex/AGENTS_SNIPPET.md"):
            lines = [ln for ln in read(os.path.join(REPO, rel)).splitlines() if ln.strip()]
            self.assertLessEqual(len(lines), 10, rel)


if __name__ == "__main__":
    unittest.main()
