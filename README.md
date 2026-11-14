# vawr: checkable usage reports for Claude Code

`vawr` answers two questions about AI agent work that nothing else answers
from records you already have:

1. **Is everything Anthropic billed you accounted for?** `vawr billcheck`
   compares what Anthropic billed an API key, minute by minute, with what
   Claude Code's own session files on your machine record. It works on the
   history you already have: no setup, nothing to have run first.
2. **Can someone else check your usage report?** `vawr` keeps a tamper-evident
   log of your Claude Code sessions, totals usage by category (safety,
   capabilities, other), and audits it three ways: the log's hash chain, your
   local session files, and Anthropic's billing records. You can hand the
   result to a funder or a reviewer, and they can rerun the checks.

Chris Graham, AI x Epistemics Research Sprint (Track 2, Trust Infrastructure),
Apart Research, November 2026. Python 3.9+, standard library only. MIT license.

**Paper:** the Sprint report (link to be added on submission).

## What you'll see

`vawr billcheck` on a 46-minute window from our own test runs:

```
Bill check, 2026-11-13 20:50 to 21:36 UTC, key apikey_…

  Billed by Anthropic                    238,904 tokens
  In this machine's session files         96,605   40.4%
  Claude Code background requests         83,546   35.0%  billed, recorded nowhere locally (11 sessions)
  Unexplained                             58,753   24.6%
      21:06           16,095 tokens  claude-haiku-5-5
      21:19           16,016 tokens  claude-haiku-5-5, claude-sonnet-5-5
      21:29           26,642 tokens  claude-haiku-5-5, claude-opus-5-5
  In session files, not billed here             0
```

The three unexplained minutes are the three runs we deliberately ran with
telemetry and session files turned off. Nothing else was flagged.

Two things stood out in our runs (one API key, one machine, Claude Code 2.1.322):

- **What Claude Code records depends on how it was launched.** When Claude
  Code 2.1.322 was told it was running inside the Claude desktop app
  (`CLAUDE_CODE_ENTRYPOINT=claude-desktop`, which the app sets for the
  sessions it starts), every headless API-key session we ran (`claude -p`) made one billed small-model
  (Haiku) request that appeared in none of its own records: telemetry events,
  metrics, session files or cost totals. On our small tasks it was a quarter
  to a half of each session's billed tokens. Every run with that setting had
  it (65 of 65) and no run without it did (0 of 9); a controlled A/B and a
  bisection isolated the variable. In interactive terminal sessions, session
  files leave out session titles, prompt suggestions and compaction, which
  Claude Code's cost totals and telemetry do include, as others have reported
  ([#104358](https://github.com/anthropics/claude-code/issues/104358),
  [#106219](https://github.com/anthropics/claude-code/issues/106219)); in our
  sessions that was a third of billed tokens. Background requests have been
  described publicly before (for example
  [anthropics/claude-code#3404](https://github.com/anthropics/claude-code/issues/3404)
  and [#82274](https://github.com/anthropics/claude-code/issues/82274)). The
  bill check accounts for all of this; anything beyond it shows up, except
  small-model usage that fits inside the per-session allowance it makes for
  the desktop request. (We didn't test the desktop app's own interactive
  sessions.)
- **Usage nobody on this machine recorded stands out.** Another machine or a
  script using the key, a run with session files turned off, or a leaked key
  all show up as unexplained minutes.

## Install

As a Claude Code plugin (slash commands, and a hook that keeps the receiver running):

```
/plugin install vawr --marketplace <owner>/<repo>
```

Then `/vawr:billcheck`, `/vawr:setup` (once), `/vawr:tag safety`, `/vawr:check`,
`/vawr:report`. Python 3.9+ must be on PATH.

Or as a command-line tool:

```bash
git clone <this repository> vawr && cd vawr
pipx install .        # or: pip install .
```

Data goes to `~/.vawr` (set `VAWR_HOME` to change it).

## Keys

The bill check reads Anthropic's usage records, which needs:

- `ANTHROPIC_ADMIN_KEY`: an Admin API key, or an organization-scoped key
  belonging to an organization admin. It is only used to read usage records.
  On an individual Console account you may first need to set up an
  organization; ours returned 403 on every usage call until we did.
- `ANTHROPIC_API_KEY`: the key to check (or pass `--key-id`).

Put them in your environment, in a `.env` file in the folder you run from, or in
`~/.vawr/.env` (works from any project; `chmod 600` it).
Never commit them.

## Check your bill

```bash
vawr billcheck --since 7d
vawr billcheck --since 2026-11-13T20:50 --until 2026-11-13T21:36 --json out.json
```

Anthropic documents its usage records as arriving within about 5 minutes; in
our runs they took 20–30 minutes, so by default the check
stops 30 minutes before now. Sessions signed in with a Claude account
(a subscription) never bill an API key and are left out.

## Keep a verified log

```bash
vawr setup            # shows the change to ~/.claude/settings.json
vawr setup --write    # applies it (the old file is backed up first)
vawr start            # receiver in the background
cd my-project && vawr tag safety --write   # this project's sessions count as safety
# ... use Claude Code as usual ...
vawr status           # receiver up? chain intact?
vawr check --since 24h
vawr report
```

`vawr report --html report.html --check check.json` (with `vawr check --json
check.json` first) writes one self-contained page to hand to a funder or
client: usage by category and project, each check with what it does and
doesn't show, and how they can verify it themselves (`vawr verify-report`).
Example, from four real interactive sessions:
[`work/samples/report_interactive.html`](work/samples/report_interactive.html).

`vawr check` runs three checks:

| Check | What it shows | What it can't show |
| --- | --- | --- |
| Chain | No entry was edited, deleted or reordered since it was written | That the log was never rebuilt end to end by whoever holds it |
| Coverage | Every request in this machine's session files reached the log | Work on another machine, or with session files turned off |
| Bill | Everything billed to the API key is in the log, apart from Claude Code's own background requests | Usage on other keys or providers; subscription usage |

The category check (`vawr validate category` in this repository) adds an
outside view of the labels: a separate model reads what each run was asked to
do and what it changed, and flags labels it disagrees with.

## How well it works

We planted failures on purpose and counted what each check caught, over 131
Claude Code runs on a dedicated API key and a Claude subscription (Nov 13–14,
2026, Claude Code 2.1.322) plus four real interactive sessions. Exact 95%
intervals are in `work/results/summary.md` and the Sprint report.

| What we planted or checked | Result |
| --- | --- |
| Runs hidden from the log (telemetry off, some with session files off too) | 26 of 26 caught by the bill (provider) check; 0 of 36 logged runs flagged |
| Hidden runs that still wrote session files | 13 of 13 caught by the session-file check |
| Hidden runs among three overlapping logged sessions | 5 of 5 windows caught; 1 of 5 clean windows also flagged (9 tokens, most likely a test session we started on the same key that minute) |
| Edits to a copy of the log that change recorded usage | 207 of 207 caught by the session-file check, including all 50 made with the hash chain rebuilt |
| A run relabeled (say, capabilities work as safety) and the chain rebuilt | 0 of 50 caught by the log checks; the category check caught 157 of 162 relabels of held-out runs, and every relabel of capabilities work as safety |
| Real interactive sessions (follow-ups, a subagent, `/compact`) | Log equals the bill exactly; bill check from session files alone: 0 unexplained |

Session files from those interactive sessions left out about a third of
what Anthropic billed (prompt suggestions, session titles, compaction); the
bill check credits it from each session's own cost totals.

## What the log keeps

Claude Code's events and token and cost metrics, with prompts redacted
(`OTEL_LOG_USER_PROMPTS` is never set). Before hashing, the receiver drops
`user.email`, `user.account_uuid`, `user.account_id`, `user.id`,
`organization.id`, `anthropic.plan` and `anthropic.seat_type`, keeping only
whether a session used an API key or a Claude account (`auth`). Logs written
before Nov 14, 2026 08:30 UTC still carry the plan and seat type.

## What predates the sprint

Nothing in this repository: all code, tasks and data were made during the
Sprint (Nov 13–15, 2026).

## Data

`work/` holds everything the results come from: the hash-chained logs
(`work/log/`, `work/pilot/log/`, `work/interactive/log/`), one manifest per run
(`work/manifests/`), Anthropic's saved per-minute usage records for the test
key (`work/provider_minutes.json`), and every result file (`work/results/`).
Identity attributes are dropped before hashing; file paths in manifests show
the machine's username.

## Reproducing the Sprint results

The research harness runs 15 small tasks (`tasks/repo`, five per category,
each with a test that fails on the stub and passes with a reference solution
the agents never see) under planted failures.

```bash
python3 -m vawr serve                                  # receiver; leave it running
python3 -m vawr batch --set sprint --plan tasks/run_plan.json
python3 -m vawr batch --set sprint --plan tasks/run_plan_batch2.json
python3 -m vawr batch --set sprint --plan tasks/run_plan_concurrency.json
python3 -m vawr provider-cache --start <UTC start> --end <UTC end>   # once records cover the runs
python3 -m vawr validate all                           # tamper, off-log, claims, category
python3 -m vawr results                                # writes work/results/summary.md
python3 -m unittest discover -s tests -t .             # tool tests
```

Runs on a Claude subscription use `--setting-sources project`,
`--strict-mcp-config` and `--disable-slash-commands` so the person's own
plugins, hooks and MCP servers stay out; API-key runs use `--bare`.

## Limits

- The bill check and the provider check cover one API key at per-minute
  resolution. Subscription usage has no provider-side record to check against.
- Coverage relies on session files on the team's own machine; whoever
  controls the machine can turn them off. The bill check is the one record
  the team doesn't write.
- Category labels are the team's own. The category check catches labels the
  work contradicts, but generic code (a cache, a statistic) can't confirm its
  own purpose, and it needs the team to share prompts and diffs.
- Claude Code's background request was measured on version 2.1.322; the
  allowance for it (`BACKGROUND_ENVELOPE` in `vawr/auditor.py`) may need
  re-measuring for other versions (Claude Code's cost reporting changed in
  2.1.325).
- Anthropic's minute buckets are per API key, not per session: concurrent
  sessions, or another client using the same key, share a bucket.
- The usage endpoint the bill check reads (`/v1/organizations/usage_report/messages`)
  is now labelled legacy by Anthropic but still supported; its successor, the
  Usage and Cost Analytics API (beta), has the same per-minute data with a
  4–24 hour delay.
- A proxy in front of Claude Code would also see every request it carries. The
  bill check doesn't need one, works on past usage, and also covers other
  clients using the same key.
