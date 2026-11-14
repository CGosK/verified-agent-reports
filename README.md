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

Built for the Apart Research AI x Epistemics Sprint (Nov 13–15, 2026), Track 2
(Trust Infrastructure). All code here was written during the Sprint. Python
3.9+, standard library only.

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

Two things stand out on any API-key account:

- **Claude Code makes a billed request it doesn't record.** In every API-key
  session we checked, Claude Code 2.1.322 made one small-model (Haiku) request
  that appears in none of its own records: not its telemetry events, its
  metrics, its session files, or its cost totals. On small tasks it was about
  half of each session's billed tokens. Tools that read session files can't
  see it; the bill check shows it.
- **Usage nobody on this machine recorded stands out.** Another machine or a
  script using the key, a run with session files turned off, or a leaked key
  all show up as unexplained minutes.

## Install

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

Put them in your environment or in a `.env` file in the folder you run from.
Never commit them.

## Check your bill

```bash
vawr billcheck --since 7d
vawr billcheck --since 2026-11-13T20:50 --until 2026-11-13T21:36 --json out.json
```

Anthropic's usage records arrive 20–30 minutes late, so by default the check
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

We tested every check against failures we planted on purpose: runs hidden
from the log, edited and rebuilt logs, relabeled runs, and false claims by
agents. Results with exact 95% intervals are in `work/results/summary.md`
and the Sprint report.

## What the log keeps

Claude Code's events and token and cost metrics, with prompts redacted
(`OTEL_LOG_USER_PROMPTS` is never set). Before hashing, the receiver drops
`user.email`, `user.account_uuid`, `user.account_id`, `user.id`,
`organization.id`, `anthropic.plan` and `anthropic.seat_type`, keeping only
whether a session used an API key or a Claude account (`auth`). Logs written
before Nov 14, 2026 08:30 UTC still carry the plan and seat type.

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
  re-measuring for other versions.
