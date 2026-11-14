# Checking how your API credits were used

For programs that give researchers or contractors Anthropic API credits, and
want a usage report they can check without taking the recipient's word for it.

## Set up once

1. Keep the credits in a Claude Console organization you own, and issue each
   grantee their own API key from it, named after them (Anthropic's session
   counts name keys, not IDs, so names must be unique).
2. Create an Admin API key for that organization and put it in `~/.vawr/.env`
   as `ANTHROPIC_ADMIN_KEY` on the machine you'll check from.
3. Ask grantees to install vawr, run `vawr setup --write` and `vawr start`
   before they start work, and tag each project (`vawr tag safety --write`).

## Each reporting period

The grantee runs `vawr bundle --since <start> --until <end>` and sends you the
zip. You run:

```bash
vawr receive their-report.zip --key-id <the key you issued> --html report.html
```

- **VERIFIED**: the report matches the log, the log hasn't been rewritten since
  earlier reports, and Anthropic's own records for the key you issued (the bill,
  minute by minute, and its daily count of Claude Code sessions) agree with it.
- **CONSISTENT**: the log and report hold together, but nothing was checked
  against Anthropic's records (no Admin key, or the key isn't in your
  organization).
- **FAILED**: something didn't match; the output says what.

`vawr team a.zip b.zip ...` checks every key in your organization at once and
lists keys that used credits with no report.

## What it can't tell you

- Usage on a Claude subscription (Pro, Max, Team): Anthropic offers no usage
  records for it, so such work is tamper-evident only.
- Whether the work was good. The report's "work passing its tests" column helps
  where projects have tests; it's not a review.
- Whether a category label is right for generic code; the category check flags
  labels the work contradicts.

vawr is a small Python program (standard library only, MIT licensed). It
reads Anthropic's records with your Admin key; Anthropic documents its Claude
Code Analytics API as free to use.
