# m7 task: web service crashes nightly after a cron job

Status: DONE
Created: 2026-01-15
Go-ahead: user, 2026-01-15 11:42: "ok, apply the plan, keep the cron change minimal"
<!--
Example task file. The project, paths and log lines are invented.
-->

## 1. INTAKE

- Task: the web service (`app/`, run by systemd unit `web.service`) stops
  answering every night shortly after 03:00 and stays down until restarted by
  hand.
- Success criteria:
  - after the nightly cron run, `curl -fsS localhost:8080/health`
    returns `ok` without a manual restart, three nights in a row;
  - `journalctl -u web.service --since 03:00` shows no traceback.
- Already tried / rejected:
  - ✅ `git log --oneline -- app/server.py` -> commit `a1b2c3d` "restart
    service in cron after cleanup" was reverted in `d4e5f6a` ("restart hides
    the bug, sessions are lost"). Do not restart from cron again.
  - ✅ HANDOFF.md (2026-01-10): "raised worker timeout to 120s, no effect".
- Open questions: none blocking. Asked the user whether the cleanup job may
  be changed: yes, if the change is small.

## 2. DISCOVERY

- Data path read: crontab entry -> `ops/cleanup.sh` -> `/var/lib/web/`
  (runtime dir) -> `app/server.py` (startup, socket, cache) -> `app/cache.py`
  -> systemd unit `deploy/web.service`.
- Findings:
  - ✅ `crontab -l` -> `0 3 * * * /opt/web/ops/cleanup.sh`.
  - ✅ `ops/cleanup.sh:14` runs `find /var/lib/web -mindepth 1 -mtime +1
    -delete`; this also deletes `/var/lib/web/run/` (socket dir, mtime set
    only at startup).
  - ✅ `app/server.py:88` creates the socket dir only in `main()` at startup;
    nothing recreates it later.
  - ✅ `journalctl -u web.service` 2026-01-14 03:00:07: `FileNotFoundError:
    [Errno 2] No such file or directory: '/var/lib/web/run/web.sock'`.
  - ✅ second cause: `app/cache.py:41` opens `/var/lib/web/cache.db` once at
    import; after cleanup deletes it, writes go to the unlinked inode and every
    read after 03:00 misses (`cache_hits` drops to 0 in `/metrics`, log line
    03:00:09 `cache miss rate 100%`).
  - ❓ worker timeout (HANDOFF 2026-01-10) is unrelated: no timeout lines in the
    log; not pursued.
- Causes and which symptoms each explains:
  1. cleanup deletes the socket dir -> service unreachable after 03:00 (main
     symptom).
  2. cleanup deletes the open cache DB -> slow responses and lost cache after
     a manual restart; would remain after fixing cause 1 alone.
- Unexplained symptoms: none.

## 3. PLAN + IMPACT

- Changes:
  1. `ops/cleanup.sh:14`: add `-not -path '/var/lib/web/run*' -not -name
     'cache.db*'` to the `find` (fixes causes 1 and 2 at the source).
  2. `app/server.py:88`: move socket-dir creation into `ensure_runtime_dir()`
     and call it also before re-binding (defence if the dir is removed by
     anything else; fixes cause 1 in the app).
- Alternatives rejected:
  - restart from cron (tried in `a1b2c3d`, reverted: loses sessions);
  - move runtime files to `/run/web` via `RuntimeDirectory=` in the unit:
    correct long-term, but changes packaging and permissions; noted as a
    follow-up, not in this task.
- Impact / blast radius: `cleanup.sh` keeps deleting everything else as before
  (checked with `find ... -print` dry run, list identical except the excluded
  paths); `ensure_runtime_dir()` is called from two places, no other callers
  of the old code (`rg -n "makedirs" app/` -> 1 hit).
- Rollback: `git revert` of one commit; crontab itself is not changed.
- Irreversible steps and premises: none in the change itself. Deploy restarts
  `web.service` once (R5): premises ✅ unit file read, ✅ restart done during
  low traffic by the user.
- Objections and answers:
  1. "Excluding paths in `find` is fragile if the layout changes." -> The
     app-side `ensure_runtime_dir()` covers the socket dir regardless; the
     follow-up moves runtime files to `/run/web`.
  2. "`cache.db*` might be large and should be cleaned." -> It is size-capped
     by `app/cache.py:12` (`MAX_ROWS`); cleanup was never meant to touch it
     (comment in `cleanup.sh:3`).
  3. "Maybe the crash is a memory issue at 03:00." -> No OOM lines in `dmesg`
     or the journal for 14 nights (`journalctl -k | grep -i oom` empty).
- Verification: run `ops/cleanup.sh` manually with `find -print` first, then
  for real on staging; check `curl /health` and `cache_hits`; then three
  nights in production.

## 4. IMPLEMENT

- Edits: `ops/cleanup.sh:14` (one line), `app/server.py:80-95` (function
  extracted, two call sites).
- Verification:
  - ✅ `bash -n ops/cleanup.sh` -> no output;
  - ✅ staging: `ops/cleanup.sh && curl -fsS localhost:8080/health` -> `ok`;
  - ✅ `python3 -m pytest -q tests/test_server.py` -> `14 passed`;
  - ✅ production, nights of 01-16, 01-17, 01-18: `/health` ok at 03:05,
    no traceback in `journalctl -u web.service --since 03:00`.
- Result: success criteria met.
- Remaining: follow-up task for `RuntimeDirectory=` in the unit file.
