# vawr: checkable usage reports for Claude Code

`vawr` answers three questions about AI agent work that nothing else answers
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
3. **Can whoever pays check it without taking your word for it?** `vawr bundle`
   puts the report, the checks and the log in one file. Whoever owns the API
   key's account runs `vawr receive` on it with their own Admin key, and checks
   it against Anthropic's records for that key: the bill minute by minute, and
   Anthropic's daily count of Claude Code sessions. An organization admin can
   check everyone's bundles at once with `vawr team`.

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
- **Anthropic's daily count of Claude Code sessions matches the log.**
  Anthropic's Claude Code Analytics API (Admin API, daily, per API key and
  terminal type) counted 98 Claude Code sessions on our key on Nov 14 (as of
  17:17 UTC). The 91 headless ones are the 66 the log has plus exactly the 25
  we hid; its Sonnet and Opus tokens beyond the log's equal, to the token,
  what the bill check found unexplained in those runs. The 5 in the
  interactive sessions' terminal type match the log, tokens included. The
  other 2 were our own plugin test at 10:45 UTC, run without telemetry: the
  bill check flags exactly their 35,936 Haiku tokens too. Its tokens differ
  from the bill only by the desktop background request (Haiku) and 9 tokens of
  an older Haiku. But Claude Code reports this count itself: two sessions run
  with `DISABLE_TELEMETRY=1` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`
  were billed (about 34,500 tokens) and never counted, while two identical
  sessions without them were (`work/results/telemetry_off_test.json`); either
  variable alone does it (0 of 2 each, `telemetry_off_bisect.json`). So the
  count catches sessions kept out of the team's log, not a team that also
  switches off Claude Code's reporting. The bill is the record a team can't
  switch off. vawr still logs sessions run with either variable, so an honest
  team that sets one has more in its log than Anthropic counted. The sessions
  check calls such a day "uncounted": not a failure, since nothing is hidden
  (the bill check covers the tokens), but the report stops at CONSISTENT, and
  `vawr setup`, `vawr status` and `vawr bundle` warn when either is set.

## Install

As a Claude Code plugin (slash commands, and a hook that keeps the receiver running):

```
/plugin install vawr --marketplace <owner>/<repo>
```

Then `/vawr:billcheck`, `/vawr:setup` (once), `/vawr:tag safety`, `/vawr:check`,
`/vawr:report`, `/vawr:bundle --since 30d`; recipients use `/vawr:receive <file>`
and admins `/vawr:team <files>`. Python 3.9+ must be on PATH.

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
| Sessions | Anthropic's daily count of Claude Code sessions and tokens on the key equals the log's, per terminal type (a count, not a list: it shows how many are missing, not which) | Sessions run with Claude Code's own telemetry off (it doesn't count them); days the log only partly covers; anything within the last hour |

Each result carries a level: **checked against Anthropic's records** (the
chain is intact and the bill check passed), **tamper-evident only** (chain
intact, no bill check: no Admin key, or a Claude subscription, for which
Anthropic offers no usage records to anyone) or **a check failed**. Reports
show how much of their usage was on an API key and how much on a subscription.

## Send a report to whoever pays

The strongest setup: whoever pays (a funder, a client, your employer) owns the
API key's account and issues you the key. They then hold Anthropic's records
themselves, and nothing in your report rests on your word.

```bash
vawr tag safety --project grant-x --write        # once, in the project's folder
vawr bundle --since 2026-11-01 --until 2026-12-01 --project grant-x --title "Grant X, November"
```

That runs `vawr check` and writes one zip: the report, the checks, a report
page, and the log. The log goes whole, because the chain can only be checked
whole. It holds token counts, models, times, session IDs, tool names, project
tags and categories. It does not hold prompts or responses: `vawr bundle`
refuses if it finds any (Claude Code only sends them if you turned on
`OTEL_LOG_USER_PROMPTS` or `OTEL_LOG_TOOL_DETAILS`), and lists any other
projects' sessions the log holds.

Whoever receives it runs:

```bash
vawr receive vawr-report-20261101T0000_20261201T0000.zip --html report.html
```

On our four interactive sessions, with the account's Admin key:

```
PASS  chain        293 entries, head b5816ab239402278
PASS  report       rebuilt from the log: same tokens per category
SKIP  continuity   first report from this log
PASS  bill         730,927 tokens billed: 730,927 logged, 0 Claude Code background, 0 unexplained
SKIP  sessions     no whole day the log covers to compare yet
        2026-11-14  Anthropic counted 98 Claude Code sessions, the log has 5 (the log started this day); ...
          non-interactive  partial     Anthropic 91, log 0; ...
          xterm            partial     Anthropic 2, log 0; ...
          xterm-256color   pass so far Anthropic 5, log 5
        the last day isn't over: run `vawr receive` again an hour after it ends (UTC) for the final count

VERIFIED  checked against your own Anthropic records
```

(The key also ran our batch tests that day, so the day as a whole can't be
compared; the interactive sessions' own terminal type matches exactly.) On a
separate key whose every session that day was logged (3 interactive, 2
headless), the whole day checks out: Anthropic counted 5 Claude Code sessions
and the log has 5, with no token difference; 550,952 tokens billed, all
logged; VERIFIED. The
same bundle of our batch runs, which include 25 runs hidden from the log,
fails both the bill check and the sessions check (non-interactive: Anthropic
91, log 66).

`receive` rebuilds the report from the log for exactly the window, projects
and head the bundle states (a report.json claiming anything narrower fails),
checks the chain, and keeps a ledger of what it has received
(`~/.vawr/received.jsonl`, with each log's entry hashes beside it). A later
report from the same log must match the earlier one entry for entry wherever
they overlap (continuity), so history can't be rewritten between reports; once
a report for an API key has been verified, a report for that key from a
different log fails until someone explains why. VERIFIED needs the payer's
Admin key, a bill check with nothing billed missing from the log and nothing
in the log that wasn't billed, a sessions check that ran without failing or
finding uncounted days (a day not yet over counts "so far"), a window that has ended, and every token in
the report on that key. Usage marked as a Claude subscription can't be
checked, so a report with any is CONSISTENT, as is one received without an
Admin key (the log and report hold together; nothing was checked against a
bill). A log that makes the checks crash, or has negative token counts, is
FAILED. `--html` builds a fresh report page on the
recipient's machine from the log and their own checks; the team's own page in
the bundle is for reading without vawr and isn't checked. The zip is treated as
untrusted: only its five known files are read, no path from it is used, sizes
and compression ratios are capped, and its strings are stripped of control
characters before printing.

## Check a whole team

```bash
vawr team alice.zip bob.zip carol.zip
```

For an organization admin: every API key that billed usage in the window,
whether any bundle covers it ("NO REPORT" with its tokens if not), the bill
check over all bundles on that key, and Anthropic's session count against
their logs. Give each person their own key: Anthropic's minute records and
session counts are per key, and continuity can't tell two people's logs on one
key from a rebuilt log.

The category check (`vawr validate category` in this repository) adds an
outside view of the labels: a separate model reads what each run was asked to
do and what it changed, and flags labels it disagrees with.

Whether the work got done (research harness, `vawr validate claims`, not yet a
user command): the claim checker pulls "done", "tests pass", "added tests" and
"blocked by X" out of each run's final message and checks them against the
code; a "done" holds only if the change is there and the task's tests pass. We
told 15 safety-task runs to do a deliberately partial job and hide it. 11 left
work that fails the tests, but 8 of those 11 said so in their summaries anyway
(one refused to hide it); the claim checker flagged all 11, including the 3
that hid it, because each still claimed the work was done. It flagged none of
5 normal runs. The other 4 planted runs met both the visible tests and hidden
ones written afterwards from the task descriptions. Work that passes a
project's tests but is subtly worse needs tests or rubrics only the recipient
holds.

## How well it works

We planted failures on purpose and counted what each check caught: 131
validation runs on a dedicated API key and a Claude subscription (Nov 13–14,
2026, Claude Code 2.1.322), four real interactive sessions, then 20 runs of
planted weaker work, 8 runs on Claude Code 2.1.325 and a 5-session day on a
second key. All tasks are 15 small ones we wrote, on one machine; exact 95%
intervals (conditional on these tasks and logs) are in
`work/results/summary.md` and the Sprint report.

| What we planted or checked | Result |
| --- | --- |
| Runs hidden from the log (telemetry off, some with session files off too) | 26 of 26 caught by the bill (provider) check; 0 of 36 logged runs flagged |
| Hidden runs that left no session files, against the bill from session files alone (`vawr billcheck`) | 15 of 15 flagged (3 batch 1, 10 batch 2, 2 concurrency) |
| Hidden runs that still wrote session files | 13 of 13 caught by the session-file check |
| Hidden runs among three overlapping logged sessions | 5 of 5 windows caught; 1 of 5 clean windows also flagged (9 tokens, most likely a test session we started on the same key that minute) |
| Edits to a copy of the log that change recorded usage | 207 of 207 caught by the session-file check, including all 50 made with the hash chain rebuilt |
| A run relabeled (say, capabilities work as safety) and the chain rebuilt | 0 of 50 caught by the log checks; in 50 fresh trials of the same edit the category check caught 48 |
| Category check against a keyword baseline | Real runs: 92 of 100 each (our task folders give the purpose away); written held-out cases, clear: model 24 of 24, keywords 15 of 24; borderline: 10 of 12 vs 5 of 12 |
| Real interactive sessions (follow-ups, a subagent, `/compact`) | Log equals the bill exactly; bill check from session files alone: 0 unexplained |
| Anthropic's daily Claude Code session count vs the log (Nov 14, as of 17:17 UTC) | Headless: Anthropic 91, log 66, a shortfall equal to our 25 hidden runs; the Sonnet and Opus tokens they add equal the hidden runs' unexplained tokens. Interactive terminal type: 5 and 5, tokens equal. 2 more sessions were our unlogged plugin test, also flagged by the bill check (35,936 tokens) |
| Weaker work, told to hide it (15 planted safety runs, 5 controls) | 11 of 15 broke the task's tests; 8 of those 11 said so anyway; the claim checker flagged all 11 (3 of 3 that hid it) and 0 of 5 controls; the other 4 met hidden tests too |
| Sessions run with Claude Code's own telemetry off (`DISABLE_TELEMETRY=1`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`) | Billed, but not in Anthropic's session count: 0 of 2 counted with both, 0 of 2 with each alone, against 2 of 2 identical sessions without them; the bill check still sees them, and vawr still logs them (1 of 1 with each) |
| A whole day on a separate key, every session logged (payer's `vawr receive`) | VERIFIED: Anthropic counted 5 sessions, the log 5, no token difference; bill 550,952 tokens, 0 unexplained |
| Claude Code 2.1.325, environment A/B (desktop app's environment vs clean) | Unrecorded request in 4 of 4 desktop-environment runs (cache read 7,010, as on 2.1.322), 0 of 4 clean; bill and session-file checks pass |
| A report rebuilt after an earlier report was received (200 trials) | Continuity caught 98 of 98 edits before the earlier report's head; by design, 0 of 102 after it |

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

- The sessions check reads Anthropic's Claude Code Analytics API: whole UTC
  days, available an hour or more later, API usage only. It names keys, not key
  IDs, so two keys with the same name can't be told apart (vawr says so and
  skips it). Console users signed in to Claude Code appear there by email; we
  only tested API-key sessions.
- A bundle shares the whole log, including other projects' token counts and
  project names, because the chain can only be checked whole. If that matters,
  a client's projects can have their own receiver and log
  (`VAWR_HOME=~/.vawr-client-a vawr start --port 4321`, then
  `vawr setup --project --port 4321 --write` in their folders); we haven't
  tested that setup.
- Continuity protects history only from the first report a recipient receives;
  edits after the last received head are caught by the other checks or not at
  all.
- `vawr receive` checks the API key the bundle names unless you pass
  `--key-id`; if you issued the key, pass it, so a sender holding two keys
  can't point the check at the other one.
- We haven't seen a session that runs past midnight UTC: vawr counts a session
  on the day it starts and its tokens on the day of each request, and
  Anthropic's daily records may split them differently. Treat the sessions
  check on such days with care.

- The bill check and the provider check cover one API key at per-minute
  resolution. Subscription usage has no provider-side record to check against.
- Coverage relies on session files on the team's own machine; whoever
  controls the machine can turn them off. The bill check is the one record
  the team doesn't write.
- Category labels are the team's own. The category check catches labels the
  work contradicts, but generic code (a cache, a statistic) can't confirm its
  own purpose, and it needs the team to share prompts and diffs.
- Claude Code's background request was measured on version 2.1.322 and
  checked again on 2.1.325 (same trigger, same 7,010-token cache read, inside the same allowance); the allowance for it
  (`BACKGROUND_ENVELOPE` in `vawr/auditor.py`) may need re-measuring for later
  versions.
- Anthropic's minute buckets are per API key, not per session: concurrent
  sessions, or another client using the same key, share a bucket.
- The usage endpoint the bill check reads (`/v1/organizations/usage_report/messages`)
  is now labelled legacy by Anthropic but still supported; its successor, the
  Usage and Cost Analytics API (beta), has the same per-minute data with a
  4–24 hour delay.
- A proxy in front of Claude Code would also see every request it carries. The
  bill check doesn't need one, works on past usage, and also covers other
  clients using the same key.
