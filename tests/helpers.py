"""Shared fixtures for m7-lite tests."""

import importlib.util
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "guard"))

import m7_guard  # noqa: E402

TEMPLATE = os.path.join(REPO, "core", "TASK_TEMPLATE.md")
TASK_REL = "docs/m7/2026-01-15-nightly-crash.md"

FILLED_TASK = """# m7 task: nightly crash

Status: {status}
Created: 2026-01-15
Go-ahead: {goahead}

## 1. INTAKE

- Task: service exits at 03:10 after the cleanup cron job.

## 2. DISCOVERY

- Findings: ✅ cleanup.sh:14 removes the socket dir; ✅ app/server.py:88 never
  recreates it (journalctl line 03:10:02 "No such file").

## 3. PLAN + IMPACT

- Changes: app/server.py create the socket dir on start; cleanup.sh skip it.
- Rollback: git revert of one commit.
- Objections: dir permissions differ -> use the same mode as packaging.

## 4. IMPLEMENT

- Edits: TODO
"""


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Project(object):
    """A temporary project directory with an optional m7 task."""

    def __init__(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="m7test-"))
        os.makedirs(os.path.join(self.root, "app"))

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def path(self, rel):
        return os.path.join(self.root, rel)

    def write(self, rel, text):
        full = self.path(rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)

    def activate(self, task_text=None, rel=TASK_REL):
        if task_text is None:
            task_text = read(TEMPLATE)
        self.write(rel, task_text)
        self.write(".m7/active", rel + "\n")

    def filled(self, status="IMPLEMENT", goahead='user, 2026-01-15: "go, apply the plan"'):
        self.activate(FILLED_TASK.format(status=status, goahead=goahead))
