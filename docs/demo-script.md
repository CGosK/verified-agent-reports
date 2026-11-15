# Demo video script (3–4 minutes)

Optional for the Sprint submission. Every command uses files already in this
repository; the receive and bill commands need `ANTHROPIC_ADMIN_KEY` (and for
`billcheck`, `ANTHROPIC_API_KEY`) in `~/.vawr/.env`. Use a fresh home so earlier
receives don't change what continuity shows:

```bash
export VAWR_HOME=$(mktemp -d)
```

## 1. The problem (30 s, voice over the README's first screen)

"A team that spends someone else's money on AI agents sends a usage report.
Today the report comes from the party being checked. A tamper-evident log
proves the log wasn't edited; it doesn't prove the log is complete."

## 2. The agent's own records miss billed work (45 s)

```bash
vawr billcheck --since 2026-11-13T20:50 --until 2026-11-13T21:36
```

Point at two lines: "Claude Code background requests: billed, recorded nowhere
locally" (the desktop-entrypoint request, 35% of this window), and the three
unexplained minutes: the runs we hid on purpose, with telemetry and session
files off. "Only the bill noticed."

## 3. The payer checks a report (60 s)

```bash
vawr receive work/samples/full-day.zip --key-id apikey_01ACxYY1jehtHaxqdPihHsqV
```

"This is what a funder runs on the file a grantee sends, with their own Admin
key." Point at: the report rebuilt from the log; the bill matching to the token
(550,952); Anthropic's count of Claude Code sessions (which Claude Code reports
to it), 5 and 5; VERIFIED.

## 4. A report with hidden work (45 s)

```bash
vawr receive work/samples/batch-runs-with-hidden.zip
```

Point at: FAIL bill (430,844 tokens unexplained: the runs we hid, minute by
minute); the sessions NOTE (this bundle's log stops at 09:17, and Anthropic's
whole-day count includes runs logged after that, so vawr says the day can't be
confirmed rather than guessing); and the NOTE that subscription usage can't be
checked against any record. (Anthropic's count for that day, compared with
every log we kept, is Table 6 in the paper: a shortfall of exactly the 25 runs
we hid.)

## 5. Someone edits the report (30 s)

Unzip `full-day.zip`, change one number in `report.json`, zip it again and
receive it: FAILED, "differs from the log". Then receive the untouched file
twice: continuity says "the same log as a report you received".

## 6. The ask (20 s)

"For API usage this works today, if the payer owns the account. For a Claude
subscription, no record exists that anyone outside Anthropic can read. That's
the missing piece providers could add."
