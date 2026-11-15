# Clean-machine walkthrough (Nov 15, 2026, 08:30–09:08 UTC)

Followed the README in a fresh virtual environment (`pip install .` from the
repository), a fresh `VAWR_HOME`, a fresh Claude Code config folder, and a
shell with nothing inherited but HOME, USER, PATH and TERM. Port 4331 instead
of the default, because another vawr receiver already held 4318 on this machine
(`vawr status` now says when the receiver on a port writes a different log).

| Step | Result |
| --- | --- |
| `pip install .` | Works with network access; offline it fails on this machine's old pip/setuptools (Python 3.9 from Xcode), since the build needs setuptools 61 or later |
| `vawr setup`, `vawr setup --write` | Shows, then writes, the eight telemetry settings into the config folder's settings.json (backed up first) |
| `vawr start`, `vawr tag safety --write` | Receiver up; the project's settings.local.json gets the category and project tag |
| One `claude -p` session on the main key | 18 log entries, chain intact; 3 requests in session files, 3 in the log |
| `vawr check --since 1h` (35 minutes later) | Chain and coverage pass; **bill FAIL: 68,116 Haiku tokens at 08:33 that no log explains**, which were our own plugin-test sessions on the same key, run without telemetry minutes after the walkthrough session; sessions check skipped (day not over) |
| `vawr report --html`, `vawr bundle`, `vawr receive` | All ran as written; `receive` rebuilt the report and returned FAILED for the same unexplained tokens |
| `vawr stop` | Stopped |

Found and fixed during the walkthrough and plugin test: `vawr bundle` (and
other commands) crashed with a traceback when no log existed yet; `vawr status`
reported a receiver on its port without saying it wrote a different log.
