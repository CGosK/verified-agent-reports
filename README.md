# Verified agent work reports

A small team's disclosure of how its AI agents' work was split across safety,
capabilities and other work, plus the checks an outsider can run to see
whether the disclosure is complete and whether the agents' claims about their
work held up. Built for the Apart Research AI x Epistemics Sprint
(Nov 13–15, 2026), Track 2. All code here was written during the Sprint.

## What it does

1. **Log.** Claude Code's own OpenTelemetry events go to a local receiver
   (`vawr serve`) that appends each one to a JSONL file. Every entry carries
   the SHA-256 hash of the entry before it.
2. **Allocation report.** `vawr report` totals tokens and Claude Code's
   estimated cost by category, taken from a tag set when each run starts.
3. **Auditor view.** `vawr audit` runs four checks:
   - **chain**: the hashes recompute, so nothing was edited, deleted or reordered
   - **totals**: the published report matches a fresh recount of the log
   - **session files**: every request in Claude Code's local session files
     for the task runs is in the log, and the token counts agree
   - **provider**: Anthropic's per-minute usage records for the Sprint API key
     are matched by logged requests; leftover provider tokens are work done
     off the log
4. **Claim checker.** `vawr validate claims` pulls "done", "tests pass",
   "added tests" and "blocked by X" claims from each run's final message and
   checks them against the diff, a fresh test run, and whether the named
   blocker really is missing.

The two checks we found no prior work for are the provider check, used as a
completeness check on an allocation disclosure, and the per-category rate of
agent claims that held up.

## Setup

Python 3.9+ standard library only; Claude Code 2.1.322 was used throughout.

`.env` (never committed) holds two keys:

- `ANTHROPIC_API_KEY`: the Sprint key that validation runs bill to
- `ANTHROPIC_ADMIN_KEY`: an Admin key, or an organization-scoped personal key
  belonging to an organization admin, used only to read usage records

```bash
python3 -m vawr serve                       # receiver; leave it running
python3 -m vawr run --task s1_refusals --mode subscription
python3 -m vawr batch --set sprint          # the planned Sprint-key schedule
python3 -m vawr report
python3 -m vawr audit
python3 -m unittest discover -s tests       # tool tests
```

Runs on a Claude subscription use `--setting-sources project`,
`--strict-mcp-config` and `--disable-slash-commands` so the person's own
plugins, hooks and MCP servers stay out. Sprint-key runs use `--bare`.

## Reproducing the results

```bash
python3 -m vawr provider-cache --start <UTC start> --end <UTC end>   # once records cover the runs
python3 -m vawr validate all        # tamper trials, off-log scoring, claim checks
python3 -m vawr results             # writes work/results/summary.md
```

Anthropic's usage records lagged 20 to 30 minutes behind real time during
this work, so the provider check can only run that long after the last run.

## The harness's background request

Claude Code 2.1.322 makes one small-model (Haiku) request per session that
Anthropic bills but that appears in none of Claude Code's own records:
telemetry events, token metrics, session files or its per-model cost totals.
`CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` does not stop it. The provider check
allows one such request per logged session within an envelope measured on
the pilot batch (`BACKGROUND_ENVELOPE` in `vawr/auditor.py`); anything beyond
it, or with no logged session nearby, is a gap. On the Sprint tasks this
request was about half the provider-recorded tokens per run.

## What is and isn't logged

The receiver records Claude Code's log events and its token and cost metrics:
prompts are redacted by Claude Code unless `OTEL_LOG_USER_PROMPTS=1`, which
this project never sets.
It drops the identity attributes Claude Code attaches to every event
(`user.email`, `user.account_uuid`, `user.account_id`, `user.id`,
`organization.id`) before hashing, so the log can be published.

## Tasks

`tasks/repo` is a toy research-utilities package with 15 tasks, five per
category. Each task's test fails on the stub and passes with the reference
solution in `tasks/solutions` (checked by `tests/test_task_suite.py`). Agents
never see the solutions.

## Limits

- Categories are self-labeled; the tool checks totals, not labels.
- The provider check covers only runs on the API key. Subscription runs get
  the session-file check, which a person who controls the machine can defeat
  by turning off both telemetry and session files.
- The hash chain alone can be rebuilt end to end by whoever holds the log;
  the completeness checks catch rebuilt logs only where token counts change.
