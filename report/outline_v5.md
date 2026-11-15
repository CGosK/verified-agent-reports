# Report outline v5 (Nov 15, after the judge's read, the fact-check and two code reviews)

v4 with every finding from Sunday's reviews applied. Section budgets total about 6½ pages of text; tables add about 1½ pages, so 8 is tight: the cuts below are part of the plan, not optional. **Required:** Limitations and Dual-Use appendix. All result files are in `work/results/`; generated tables in `report/tables.md` (rerun `report/make_tables.py`, never edit by hand). Numbers below were checked against those files on Nov 15.

**What changed from v4:** a coverage matrix replaces most of Section 3; Results merge per-minute and per-day off-log checks; the category check leads with the written held-out cases and a keyword baseline; continuity and the new relabel-and-rebuild result close Table 2's 0/50 row; weaker-work and claim-checker results move to the appendix with one honest sentence in the Discussion; run counts, the 2 unlogged xterm sessions, the 400/400 wording and the "every check rests on an outside record" overclaim are fixed; the session count turned out to be reported by Claude Code itself: sessions run with its own telemetry off were billed but not counted (5.2), so the bill is the one record a team can't switch off. Either variable alone silences it, and vawr still logs such sessions, so the sessions check now calls a day with more in the log than Anthropic counted "uncounted" (not FAILED, not VERIFIED) and vawr warns a team that has either set.

## Title and author

- **Title:** "A Record the Author Doesn't Write: Checking AI Agent Usage Reports for Completeness"
- Your name and affiliation, then "With Apart Research".

## Abstract (≤250 words; keep three numbers)

Opening sentence (from the judge's read): "Tamper-evident logs show that an AI agent's usage record wasn't edited, not that it is complete; we argue completeness is the missing layer in AI observability, and show it can be checked today against provider records the reporting team doesn't write."

Then, in four or five sentences: who needs it (whoever pays for or oversees a team's agent use: a client, a funder of API credits, an employer; at lab scale, the public reading a compute split [1]); what we built for Claude Code (a hash-chained log and per-category report, reconciled with Anthropic's per-minute billing records and its daily count of Claude Code sessions, a category check by a separate model, and a bundle the payer checks with their own Admin key); three numbers: **26 of 26 hidden runs caught with 0 of 36 logged runs flagged; on real interactive sessions the log equalled the bill to the token; the category check caught 157 of 162 relabels** (or the written-case result, 24/24 vs a keyword baseline's 15/24, if you'd rather show the model earns its place); the existence proof (one launch setting made every headless session's billed request vanish from all four local records, and only the bill noticed); and the takeaway: completeness is checkable for API usage today because the bill is a record the team can't switch off (Anthropic's own session count can be: Claude Code reports it, and an environment variable stops it), and not for subscription usage, which is an ask of providers.

## 1. Introduction (about ¾ page)

- **Track 2's question,** quoted from the sprint brief [17]: "What minimal tamper-evident layer is missing from current AI observability standards?" Answer: tamper-evidence isn't the missing piece; completeness is. A hash chain proves a log wasn't edited, not that everything that ran is in it, and an agent's own records are measurably incomplete (5.1).
- **Who needs it:** whoever pays for or oversees agent use gets a report written by the party being checked. Lead with the case that works today: the payer owns the API account and issues the key (a client, an employer, a foundation buying credits in its own organization). Then they hold the provider's records themselves. Note honestly that in Anthropic's researcher program [18] the provider is the funder and already has the bill; there the new value is the category layer and checks an outsider can rerun. Lab scale is an analogy: verified allocation disclosures [1] ask that visible compute match the claimed split and nothing run unseen.
- **Compute isn't work done,** one clause: [3] reports weaker work on safety-framed tasks; we test only a planted version (Appendix B).
- **Question:** can a payer check, end to end, a usage report from a team they fund, using records that already exist?
- **Contributions (four):**
  1. An existence proof that an agent's own records are incomplete: a launch setting (`CLAUDE_CODE_ENTRYPOINT=claude-desktop`) made one billed request per headless session vanish from all four local records; interactive session files omit a third of billed tokens (the latter replicates [22, 23]).
  2. Completeness checks against the provider's per-minute bill, the one record here the team can't switch off, plus Anthropic's daily Claude Code session count (which we show Claude Code reports itself, so a team can silence it) and recipient-held hashes so history can't be rewritten between reports.
  3. A category check that catches relabeling, which the log checks can't see.
  4. Validation with planted failures, a full day checked by the payer, and a working tool (CLI and Claude Code plugin).
- Don't say "first"; say "we found no released tool that reconciles Claude Code's local records against Anthropic's per-minute usage records" (`work/prior_art_billcheck.md`).

## 2. Related Work (about ½ page; compress)

- **Tamper-evident logs:** otel-agent-audit [4], Agent Flight Recorder [5], the IETF agent audit-trail draft [6], the sprint's "Tamper-Evident Action Recorder" [17]: they show a log wasn't altered, not that it's complete.
- **Provider records and reconciliation:** compute providers can verify customers' claims from records they hold [7]; CoIn checks the provider's count of hidden tokens [8], the opposite direction; OpenTelemetry cost-source proposals [9, 10]; Anthropic lists cost reconciliation as a use of its usage API [11]; FinOps tools attribute spend for a team's own finance staff. None tests reconciliation as a completeness check on a report an outsider receives.
- **Local usage tools:** ccusage [21] reads session files only.
- **Background requests (two sentences):** described before [19, 20]; session files omitting titles, prompt suggestions and compaction reported in [22, 23]. We found no prior report of a request missing from all four records or tied to the desktop entrypoint.
- **Labels and claims:** Anthropic's split used a classifier [2]; false-claim work [12–15].

## 3. Design (about 1 page): a coverage matrix, not a manual

Replace the command-by-command description with one table (Table 1, new; fill from the numbers below). Rows are what a team could get wrong or hide; columns are the records compared, each named by the two records it compares:

| Failure or attack | Log vs its own hashes (chain) | Session files vs log (coverage) | Bill vs log, per minute | Bill vs session files (`billcheck`) | Anthropic's session count vs log, per day (reported by Claude Code) | Recipient-held hashes (continuity) | Category check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Run hidden from the log, session files kept | – | 13/13 | 26/26 (all hidden runs) | – (files explain it) | shortfall of 25 = 25 hidden (Nov 14) | – | – |
| Run hidden, no session files | – | – | (in 26/26) | 15/15 | (in the 25) | – | – |
| Hidden run overlapping logged runs | – | – | 5/5 windows (1/5 clean flagged) | – | counted per session | – | – |
| Edit or delete entries, chain not rebuilt | 400/400 | – | – | – | – | – | – |
| Edit usage, chain rebuilt | 0 | 207/207 | 167/167 (API-key requests) | – | – | caught before an earlier report's hashes (as for relabels) | – |
| Relabel, chain rebuilt | 0/50 | 0 | 0 | – | – | 98/98 edits before an earlier report's hashes | 48/50 |
| Usage claimed but never billed | – | – | fails (log excess) | – | uncounted (more in the log; not a failure on its own) | – | – |
| Session hidden with Claude Code's own telemetry off too | – | – | caught (billed) | caught if no session files | not counted (0 of 6; either variable alone) | – | – |
| Honest team with Claude Code's own telemetry off (false alarm to avoid) | – | – | passes (logged and billed) | – | uncounted: report stops at CONSISTENT, not FAILED; vawr warns | – | – |
| Unrecorded background request (honest) | – | – | credited (allowance) | credited | not counted by Anthropic either | – | – |

- Under the table, one paragraph each: the log and report (hash chain, identity fields dropped, prompts never logged); the bill check (Anthropic's per-minute usage per key by model and token type, matched to logged requests within ±2 minutes with no tolerance for unexplained tokens, except one small-model background request per logged session within a measured allowance); the session count (Anthropic's Claude Code Analytics API [26]: per key, UTC day and terminal type; a count, so it shows how many sessions are missing, not which; about an hour behind; reported by Claude Code itself, so it is a second view of the client, not an outside record); payer mode (`vawr bundle`, `vawr receive`: verdicts verified / consistent / failed; VERIFIED needs every token in the report on the payer's key, the period over, and no day where Anthropic counted fewer sessions than the log has); the category check (a separate model reads each run's prompt and diff).
- **Smallest hidden usage the bill check can miss:** Haiku usage that fits inside the background allowance of a logged session in the same minutes (≤1,000 input, ≤1,500 output, ≤7,010 cache-read tokens per logged session); any hidden Sonnet or Opus tokens show. Hidden work inside a logged session that the log under-reports is a log edit, caught by the bill check unless it fits that allowance.

## 4. Validation setup (about ½ page)

- 15 small tasks we wrote (five per category), one machine, one operator. Say plainly that intervals are exact Clopper–Pearson and conditional on these tasks and logs; "later runs" are new runs of the same tasks, not new tasks; the 36 written cases are the true held-out set for the category check.
- Runs: 131 validation runs on Claude Code 2.1.322 (batch 1: 14 key + 11 subscription; batch 2: 40 key + 15 subscription; concurrency: 35; environment A/B: 8; bisection: 8), 4 real interactive sessions, then 20 planted-weaker-work runs, 8 runs on 2.1.325, and a 5-session day on a second key. Hidden runs: 31 in all (6 in batch 1, 20 in batch 2, 5 in concurrency windows).
- Planted failures: hidden runs (telemetry off; some with session files off), tampered log copies (550), relabels, false "done" and invented blockers, weaker work told to hide it.
- Units: a run, a window (concurrency), an edited copy (tampering), a message (claims), a run or case (category).

## 5. Results (about 2½ pages with Tables 1–4)

**5.1 The agent's own records are incomplete (existence proof).** One paragraph: with `CLAUDE_CODE_ENTRYPOINT=claude-desktop` (inherited because the desktop app launched every experiment) every headless API-key session made one billed Haiku request missing from telemetry events, metrics, session files and cost totals: 65 of 65 runs with the setting, 0 of 9 without; an A/B and a bisection isolated the variable; 23–54% of each session's billed tokens on these small tasks; the provider check credited it to 62 of 62 desktop-environment logged sessions in the window (the other 4 logged sessions were clean A/B runs). Same on 2.1.325 (4 of 4 vs 0 of 4, cache read 7,010). Bisection details to Appendix B. Interactive terminal sessions made no such request, but their session files omitted 34% of billed tokens (248,395 of 730,927: titles, prompt suggestions, compaction), consistent with [22, 23]. The point: an upstream setting silently broke every local record, and only an outside record noticed.

**5.2 Work done off the log, per minute and per day.**
- Per minute (provider window 20:50 Nov 13 to 09:17 Nov 14, 747 minutes): 26 of 26 hidden runs in batches 1–2 caught (95% CI 87–100%), each as its own gap of 14,463–26,642 tokens; 0 of 36 logged key runs flagged (0–10%); no log excess. Session files: the coverage check caught 13 of 13 hidden runs that kept files; the bill check from session files alone flagged 15 of 15 hidden runs that left none (3 + 10 + 2 across batches and concurrency). Concurrency: 5 of 5 windows with a hidden run flagged; 1 of 5 clean windows, by 9 tokens of an older Haiku at 08:50 (cause unknown; timing suggests our own test launches).
- Per day: Anthropic's Claude Code count for Nov 14 (as of 17:17 UTC) was 98 sessions on the key: 91 headless, which is the 66 the log has plus 25, the number of runs we hid that day (a count, not a list), with the extra Sonnet and Opus tokens equal to the bill check's unexplained tokens to the token; 5 in the interactive sessions' terminal type, matching the log (4 sessions plus a test launch with no requests), tokens equal; and 2 more at 10:45 UTC that were our own plugin test run without telemetry, which the bill check also flags (35,936 Haiku tokens, equal in both records). Billed minus Anthropic's count is Haiku only (616,117 tokens, exactly the background requests of that day's 82 desktop-entrypoint runs) plus 9 tokens of an older Haiku.
- **The session count is reported by the client.** On Nov 15 we ran two one-line sessions on the main key with `DISABLE_TELEMETRY=1` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` (marked with their own terminal name) and two identical ones without: Anthropic counted 2 of 2 controls and 0 of 2 of the others, though the bill shows all four (69,848 Haiku tokens in that minute) (`telemetry_off_test.json`). Either variable alone does it: 0 of 2 each (`telemetry_off_bisect.json`, checked 65 to 91 minutes after; the controls had appeared within an hour). vawr's own log still records such sessions (1 of 1 with each, and a control; `telemetry_off_otel_*.json`), so an honest team with either set would have shown more sessions than Anthropic counted and, before we changed it, failed. The sessions check now calls such a day uncounted: not a failure, since the log has more, not less, and the bill covers its tokens, but not VERIFIED; `vawr setup`, `status` and `bundle` warn when either is set. So the count catches sessions kept out of the team's log, as the 25 above were, but not a team that also switches off Claude Code's own reporting. The bill is the record a team can't switch off. Say this plainly; it sharpens the thesis.
- Full day, payer side: on a second key with every session that day logged, `vawr receive` with the organization's Admin key after the day closed: VERIFIED; Anthropic 5 sessions, log 5, no token difference; 550,952 tokens billed, all logged.

**5.3 Tampering, rebuilds and relabels** (Table 2). Lead with the provider: of 550 edited copies of the log, every edit that changed API-key usage was caught by the bill check (167 of 167). The chain caught every edit or deletion made without rebuilding it (400 of 400); dropping the last entries isn't visible to a chain (0 of 50) and changes no totals unless requests drop. Session files caught 207 of 207 usage-changing edits, but a team that rebuilds the chain can edit those too, so count them as a check on honest mistakes. A relabel with the chain rebuilt: 0 of 50 by the log checks; in 50 fresh trials of the same edit the category check caught 48. Continuity: with an earlier report's hashes held by the recipient, 98 of 98 rebuilds that changed entries before that point were caught (by design 0 of 102 after it).

**5.4 Category check** (Table 3). Lead with the 36 written held-out cases (written by a separate agent from the definitions alone): clear cases 24 of 24 correct, against 15 of 24 for a keyword baseline fixed in advance; borderline 10 of 12, against 5 of 12; relabels caught 48 of 48 clear and 22 of 24 borderline. On our real runs a keyword baseline matches the model (92 of 100 each), because task folders give the purpose away; say so. Later runs of the same tasks: 5 of 81 correct labels flagged (all "unconfirmed" generic code, 0 contradicted); 157 of 162 relabels caught. Capabilities relabeled as safety: 44 of 44 across all sets (38 of 38 held out). Variance and the rebuild-from-session-file check to Appendix B. Scope: it targets honest artifacts with wrong labels, not fabricated artifacts.

**5.5 Real interactive sessions** (one short paragraph): log equalled the bill (730,927 tokens, none unexplained); from session files alone, 0 unexplained after crediting cost totals; two fixes the sessions exposed, and re-scoring changed nothing (details in Appendix B).

## 6. Discussion (about ¾ page)

- **Answer to Track 2:** completeness relative to the account the payer controls is checkable today. The checks that stop a dishonest team rest on a record it can't switch off (the bill) or a commitment it can't take back (hashes the recipient holds); the chain, session-file and session-count checks catch honest mistakes and naive hiding (we show Claude Code's own report to Anthropic can be silenced by an environment variable), and the category check catches mislabels.
- **Theory of change, in order:** (1) payers who own the account issue the key and run `vawr receive` (works today); (2) funders and clients ask for checkable reports, starting where they already control the account; (3) providers expose what's missing: usage records for subscription seats, per-session usage records counted on the provider's side rather than reported by the client, and client telemetry that includes every billed request; (4) at lab scale the same structure is an analogy for verified allocation disclosures [1], where provider and reporter can be the same party, so other records are needed.
- **Limits that matter:** one key per check; subscription usage is tamper-evident only; small hidden Haiku usage under the allowance (Section 3); the session count can be silenced by the client (5.2); toy tasks, one operator, one machine, a non-adaptive adversary (every hidden run was far above the allowance).
- **Work done, one sentence:** in a planted test of weaker work told to hide it (Appendix B), 8 of 11 weak runs disclosed it anyway and the claim checker flagged all 11 because each still claimed "done"; work that passes the tests but is subtly worse needs rubrics only the recipient holds.

## 7. Conclusion (three sentences)

- For API usage, a payer who owns the account can check a team's usage report end to end against the provider's bill, a record the team can't switch off.
- In our tests the bill caught every hidden run and flagged no logged one, the category check caught relabels the log couldn't, and on real interactive sessions the log matched the bill to the token.
- Agents' own records can silently miss billed work, so completeness needs an outside record; for subscription usage none exists yet.

## End matter (not counted)

- **Code and Data:** repository link; "What predates the sprint: nothing"; data in `work/`; identity attributes dropped; usernames in file paths.
- **Appendix A, Limitations and Dual-Use (required):** limitations as in Section 6, plus: category content isn't bound to the log; one model sample unless voting; Admin API needs a Console organization; versions 2.1.322 and 2.1.325 (the latter A/B only); the session count names keys, not IDs. Dual use: reconciliation could monitor individuals' agent use (identity fields dropped; checks run by or with the account holder); the background allowance is a size below which small hidden Haiku usage passes, so publishing it teaches evasion; the planted fake blockers are generic.
- **Appendix B:** pilot and bisection detail; per-run off-log table (Table B1); concurrency windows; claim checker (98/98 false "done"; invented blockers 9 of 9, 7 development and 2 held-out; true blockers wrongly flagged 0 of 9 and 0 of 4 held-out; honest runs flagged 6 of 98, all checker errors); weaker work told to hide it (Table 7: 11 of 15 weak; 8 of 11 disclosed; claim checker flagged 11 of 11, 3 of 3 hidden, 0 of 5 controls; 4 others pass hidden tests written after the runs, which 41 of 41 normal safety runs pass); category variance; 2.1.325 and continuity (Table B2); speed (100,000-entry log: verify 1 s, check 2 s, receive 5 s).
- **LLM Usage Statement:** Claude wrote code, ran experiments, drafted text, wrote the held-out category cases and fact-checked numbers; confirm or edit.
- **References:** [1]–[25] as in v4, plus [26] Anthropic, "Claude Code Analytics API", https://platform.claude.com/docs/en/manage-claude/claude-code-analytics-api.

## Claims to avoid

- "First" tool; that reconciling against billing is new; that session files are independent records.
- That we discovered background requests, or that the unrecorded one is the session-title request; that it affects terminal users (0 of 9 without the setting).
- That Lifland proposed hardware attestation; that funders currently require usage reports.
- That the session count identifies which sessions are missing (it's a count); that it is billing; that it's counted on Anthropic's side (Claude Code reports it; 0 of 6 telemetry-off sessions counted).
- That Nov 13 was checked by the session count; that Console-login users (by email) were tested.
- That continuity catches edits after the last hashes a recipient holds; that the tool detects covert underperformance or sandbagging; that the outcome column "caught" weak work (it shows it by definition).
- That the 08:50 9-token flag certainly came from our test sessions.
- "End to end" without "for a payer who owns the account".
