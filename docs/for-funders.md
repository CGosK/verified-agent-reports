# Checking how your API credits were used

For programs that give researchers or contractors Anthropic API credits, and
want a usage report they can check without taking the recipient's word for it.

## Set up once

1. Keep the credits in a Claude Console organization you own, and issue each
   grantee their own API key from it, named after them (Anthropic's session
   counts name keys, not IDs, so names must be unique).
2. Create an Admin API key for that organization and put it in `~/.vawr/.env`
   as `ANTHROPIC_ADMIN_KEY` on the machine you'll check from. Always pass the
   key you issued with `--key-id`, so the check can't be pointed at another key.
3. Ask grantees to install vawr, run `vawr setup --write` and `vawr start`
   before they start work, and tag each project (`vawr tag safety --write`).

## Each reporting period

The grantee runs `vawr bundle --since <start> --until <end>` and sends you the
zip. You run:

```bash
vawr receive their-report.zip --key-id <the key you issued> --html report.html
```

- **VERIFIED**: the report matches the log; the log extends earlier reports
  you received from it entry for entry; and Anthropic's own records for the key
  you issued agree with it: the bill, minute by minute, with nothing missing and
  nothing extra, and its daily count of Claude Code sessions, day by day (for a
  day not yet over, "so far"). Every token in the report is on that key, and the
  period has ended. Claude Code reports that session count itself, so it catches
  sessions kept out of the log; the bill is the record a team can't switch off.
  Ask for whole UTC days: a period that starts or ends partway through a day
  can't always be confirmed by a whole-day count.
- **CONSISTENT**: the log and report hold together and nothing was edited after
  earlier reports, but not everything was checked against Anthropic's records:
  no Admin key, records that couldn't be read, usage marked as a Claude
  subscription, a period that hasn't ended, a day Anthropic's count can't
  confirm because the period covers only part of it, or sessions Claude Code
  didn't report to Anthropic because the grantee set `DISABLE_TELEMETRY` or
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` (vawr warns them; the bill still
  covers those tokens).
- **FAILED**: something didn't match, including usage the log claims on your key
  that Anthropic never billed, or a log that can't be read; the output says what.

`vawr team a.zip b.zip ...` checks every key in your organization at once and
lists keys that used credits with no report.

## What it can't tell you

- Usage on a Claude subscription (Pro, Max, Team): Anthropic offers no usage
  records for it, so such work is tamper-evident only.
- Whether the work was good. vawr checks usage, labels and history, not quality;
  the research harness's claim checker and test-outcome column aren't part of
  the report yet.
- Whether a category label is right for generic code; the category check flags
  labels the work contradicts.

vawr is a small Python program (standard library only, MIT licensed). It
reads Anthropic's records with your Admin key; Anthropic documents its Claude
Code Analytics API as free to use.
