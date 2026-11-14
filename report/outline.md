# Report outline

One block per template section, in order: the points to make, the numbers with their source files, what to cite, and what not to overstate. **Length: 4–8 pages excluding references and appendices; 8 is a hard cap.** The budgets below total about 7 pages at 11pt, leaving room. A **Limitations and Dual-Use / Ethical Considerations appendix is required.** All result files are in `work/results/` unless marked otherwise; the code is in the private repo github.com/CGosK/verified-agent-reports. `report/draft.md` and `report/draft-full.md` carry batch-1 numbers only: use them for wording, not figures.

**What changed since the last version:** the paper now centres on a tool someone would use (a team giving a funder or client usage evidence they can check), adds the category check, two more batches of runs (one with overlapping sessions), real interactive sessions, the bill check that works on existing history, and narrows the background-request claim to what prior reports don't already cover.

## Title and author

- Working title: "Usage Reports an Outsider Can Check: Reconciling AI Agent Records with the Provider's Bill". Shorten if you like.
- Your name and affiliation, then "With Apart Research".

## Abstract (up to 250 words)

1. Need: when someone pays for or oversees an AI team's agent use (a funder of API credits for safety research [18], a client, or, at lab scale, the public reading a compute split [1, 2]), the usage report comes from the party being checked. It is worth something only if an outsider can check that nothing ran off the record, that work sits in the right category, and that claimed work was done.
2. What we built, for teams running Claude Code agents, from records that already exist:
   - a hash-chained log feeding a per-category, per-project usage report;
   - checks that reconcile the log, and separately the agent's local session files, with Anthropic's per-minute billing records for the API key;
   - a category check in which a separate model reads each run's task and code change;
   - a claim checker for agents' "done" and "blocked" claims;
   - a shareable report the recipient can verify against the published log.
3. Headline results (131 runs, Nov 13–14, 2026): the provider check caught 26 of 26 hidden runs and flagged 0 of 36 logged runs; with three sessions overlapping, it flagged 5 of 5 windows that held a hidden run (and 1 of 5 clean windows, most likely because of a test session we started on the same key). Edits that changed recorded usage were caught 207 of 207 by the session-file check, including all 50 made with the hash chain rebuilt; a relabel in a rebuilt chain, 0 of 50. The category check caught 157 of 162 relabels of held-out runs and all 44 relabels of capabilities work as safety. On four real interactive sessions the log equalled the bill to the token. The claim checker caught 98 of 98 false "done" claims and 9 of 9 invented blockers (7 development and 2 held-out phrasings), and wrongly flagged 6 of 98 honest runs.
4. Findings about the harness: when Claude Code was told it was running inside the Claude desktop app (`CLAUDE_CODE_ENTRYPOINT=claude-desktop`, which every experiment inherited because the desktop app launched them), every headless API-key session (`claude -p --bare`, as all our runs were) made one billed small-model request missing from all four of its local records (telemetry events, metrics, session files, cost totals), 23–54% of each session's billed tokens on these small tasks. Every run with that setting had it (65 of 65); no run without it did (0 of 9); a controlled A/B and a bisection isolated the variable. In real interactive terminal sessions, session files left out a third of billed tokens (titles, prompt suggestions, compaction) that telemetry and cost totals included. Background requests themselves were public before [19, 20].
5. Takeaway: a checkable report needs a record its author doesn't write; the provider's bill is one that already exists.

## 1. Introduction (about ¾ page)

- The concrete case: research credits arrive as API credits on one provider account [18]. The program page notes a team can monitor its own usage [18], but whoever gives the credits gets no account of what they paid for that they can check themselves. The same question at lab scale: proposals for pacing frontier AI ask labs to disclose how compute splits between safety and capabilities, which helps only if it can be verified, in two parts: visible compute matches the claimed split, and no compute ran unseen [1]. Anthropic's published split (about 6% of AI R&D compute to safety in one week of July 2026) was labelled by a classifier and hasn't been checked by a third party [2].
- Compute spent isn't work done: OpenAI reports GPT-6 Astra completing about 10% of hidden rubric items on tasks framed as safety research, against about 16% on matched capabilities-framed tasks [3].
- Question: can a small team give an outsider a usage report the outsider can check end to end, from records that already exist?
- Contributions:
  1. Reconciliation of an agent team's own records with the provider's per-minute billing records, as a completeness check, both on a tamper-evident log and on the session files Claude Code already writes (so it works on past usage with no setup).
  2. A category check that catches relabeling, the one tampering the log checks can't see.
  3. Validation against planted failures over three batches (one with overlapping sessions) and on real interactive sessions, with held-out sets and exact confidence intervals.
  4. The harness finding, stated against prior reports.
  5. A working tool (command line and Claude Code plugin) with recipient-side verification.
- Don't overstate: "we found no released tool that reconciles Claude Code's local records against Anthropic's per-minute usage records" (`work/prior_art_billcheck.md`), not "first".

## 2. Related Work (about ¾ page)

- **Tamper-evident logs:** otel-agent-audit [4], Agent Flight Recorder [5], the IETF agent audit-trail draft [6], the Sprint brief's "Tamper-Evident Action Recorder" [17]. They show a log wasn't altered, not that it's complete.
- **Provider records and reconciliation:** Heim et al.: compute providers can verify customers' claims from records they already hold [7]. CoIn checks the provider's count of billed hidden-reasoning tokens [8], the opposite direction from ours. OpenTelemetry proposals mark whether a cost came from the provider or was computed locally [9] and version price tables so a gap against the invoice can be traced to pricing or to usage [10]. Anthropic lists cost reconciliation as a use of its usage API [11], and FinOps platforms attribute spend by workspace or key for a team's own finance staff. None tests reconciliation as a completeness check for a report an outsider receives.
- **Local usage tools and proxies:** ccusage [21] and similar tools read local session files only; none compares them with the provider's records (`work/prior_art_billcheck.md`). A proxy sees every request it carries; reading the provider's records needs no routing, works on past usage, and covers other clients on the same key.
- **Background requests:** Claude Code's small-model requests were described in 2025 [19] and its auxiliary request types listed by a maintainer in 2026 [20]. Users have reported that session files omit billed background requests (titles, prompt suggestions, compaction, agent summaries) that Claude Code's own cost totals include, by 1.35–2.13x [22], and measured prompt suggestions alone [23]; agent-summary requests skip the transcript, about 18% of weighted tokens in one subagent-heavy session [24]. Our interactive measurement replicates [22, 23]; we found no prior report of a request missing from all four records, nor of one tied to the desktop entrypoint. The closest prior work on reconciliation is a proposal to compare Claude Code's logged cost with Anthropic's daily cost report, never run [25].
- **Labels:** Anthropic's split used a classifier on sampled workloads [2]; we use the same idea as an audit check against a team's own labels.
- **False claims:** Advani [12]; Guo et al. [13]; AgentLiar [14]; Swarm Orchestrator [15]. What we add: a check that a named blocker really is missing.
- Stay close to the fact-checked descriptions in `report/draft-full.md` Section 2 for [4], [8], [9], [10], [14].

## 3. The Tool (about 1¼ pages)

- **Log:** Claude Code's OpenTelemetry events go to a local receiver that writes JSONL, each entry carrying the SHA-256 hash of the one before. Identity attributes are dropped before hashing, and from Nov 14 08:30 UTC also plan and seat type (earlier entries still carry them); only whether a session used an API key or a Claude account is kept. Prompts are never logged.
- **Report:** tokens and Claude Code's cost estimate by category and project, for any time window.
- **Checks (`vawr check`):**
  1. Chain: every hash recomputes.
  2. Coverage: every request in the machine's session files is in the log.
  3. Bill (provider check): Anthropic's per-minute usage for the key, by model and token type, is matched by logged requests within ±2 minutes, zero tolerance, with one background request allowed per logged session inside an envelope measured on the pilot. Unmatched billed tokens are gaps.
- **Bill check (`vawr billcheck`):** the same reconciliation against session files instead of the log, so it works on existing history. Subscription sessions are told apart from API-key sessions by an owner entry or 1-hour prompt caching (all 37 subscription and 103 API-key session files in our runs, headless and interactive, separate cleanly under the final rule).
- **Category check:** a separate model (Claude Sonnet) reads each run's prompt and diff (or a real session's prompts and edits, rebuilt from its session file) and picks safety, capabilities or other from written definitions. Verdicts: confirmed, unconfirmed (generic code, no visible purpose), contradicted. Optional majority of three calls.
- **Claim checker:** a model extracts done / tests pass / added tests / blocked-by claims; each is checked against the diff, a fresh test run, or whether the blocker exists. The model only extracts.
- **For the recipient:** `vawr verify-report` confirms the report's head hash is in the published log and recomputes its totals; with the account's Admin key, the recipient runs the bill check themselves. Packaged as a command-line tool and a Claude Code plugin (slash commands; a session-start hook keeps the receiver running).
- Don't call session files "independent": the same harness writes them on the same machine.

## 4. Validation (about ¾ page)

- 15 small tasks in a toy repository, five per category; each test fails on the stub and passes with a reference solution the agents never see.
- Batches (all Claude Code 2.1.322; API-key runs on a dedicated key nothing else used):
  - Batch 1 (Nov 13): 14 key runs (6 off-log) and 11 subscription runs.
  - Batch 2 (Nov 14): 40 key runs (20 off-log, rotating Haiku/Sonnet/Opus and with/without session files) and 15 subscription runs.
  - Concurrency (Nov 14): 10 windows of three logged runs started 5 s apart, five windows also with an off-log run among them (35 runs).
  - Environment A/B (Nov 14): 8 logged key runs alternating the environment inherited from the desktop app (which launched every experiment) with a clean one; then a bisection of which inherited variable matters (8 runs).
  - Interactive (Nov 14): 4 real interactive terminal sessions on the key, driven with `expect`, in a clean environment and their own config folder: follow-up turns, a subagent, `/compact`, Haiku; nothing switched off.
- Planted failures: off-log runs; random edits to log copies (delete, edit tokens, edit category, either with the chain rebuilt, drop the tail); relabels; false "done" and invented blockers.
- Category check: developed on batch 1 (one prompt revision, one model choice; `work/category_dev/history.json`), then frozen (prompt hash 4981a32faa4a9d65) before scoring 81 later runs (batch 2: 35, concurrency: 30, A/B: 8, bisection: 8) and 36 cases written by a separate agent from the definitions alone (12 per category, 12 borderline).
- Units: a run (off-log), a window (concurrency, since per-minute records can't separate runs in the same minute), an edited copy (tampering), a message (claims), a run or case (category). Exact two-sided 95% Clopper–Pearson intervals.

## 5. Results (about 2¼ pages, Figure 1 and Tables 1–4)

**5.1 What the harness records, and doesn't.** In the pilot, every logged API-key run showed more billed usage than the log: one Haiku request per run (cache-read always 7,010; cache-creation 0), in none of telemetry, metrics, session files or cost totals; `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` didn't stop it [16]. Across all batches the provider check credited this request to 62 of 62 logged sessions in the provider window, all launched from the desktop app's environment, 23–54% of each session's billed tokens (`paper_numbers.json`; split approximate where sessions overlapped). The A/B located it: 4 of 4 inherited-environment runs, 0 of 4 clean ones (`env_ab.json`). The bisection named the variable: a clean environment plus `CLAUDE_CODE_ENTRYPOINT=claude-desktop` alone brought it back (1 of 1); the tool-summary, classifier and message-card variables, or all other inherited variables together, did not (0 of 5); the inherited environment without the tool-summary variable still had it (2 of 2) (`env_bisect.json`). So: 65 of 65 runs with the desktop entrypoint, 0 of 9 without, all headless (`claude -p --bare`); the desktop app's own interactive sessions weren't tested. Its source inside Claude Code is unknown; say so. Real interactive terminal sessions made no unrecorded request, but their session files omitted session titles, prompt suggestions and compaction, 34% of billed tokens (248,395 of 730,927), which telemetry and the sessions' own cost totals included (`interactive_billcheck.json`), consistent with [22, 23]. Say "in our runs on 2.1.322"; this is the honest hook: tools reading session files undercount interactive use, here by about a third.

**5.2 Off-log work** (Table 1, Figure 1). One provider window, 2026-11-13 20:50 to 2026-11-14 09:17 UTC (747 minutes; no key usage between batches): the provider check caught 26 of 26 hidden runs in batches 1–2 (95% CI 87–100%), each as its own gap of 14,463–26,642 tokens, and flagged 0 of 36 logged key runs (batches 1–2 and the A/B; 0–10%); no log excess. The session-file check caught 13 of 13 hidden runs that kept session files (75–100%), with no requests missing from files and no token mismatches. Concurrency: 5 of 5 windows with a hidden run flagged (48–100%); 1 of 5 clean windows flagged (1–72%), by 9 tokens (8 input, 1 output, claude-haiku-4-5) at 08:50, most likely from two interactive test sessions we launched on the same key at 08:50:10 and 08:50:46 (timing only; no log ties the tokens to them). If so it was real usage outside this log, a correct detection that our time-based scoring assigned to the window. The bill check from session files alone found exactly the three batch-1 runs that left no local trace. Figure 1 stays the batch-1 window as an illustration.

**5.3 Tampered logs and relabels** (Table 2; `tamper_summary.json`, 550 edited copies of the log up to the window's end). The chain caught every edit made without rebuilding it (400 of 400). Edits that changed recorded usage were caught 207 of 207 (98–100%) by the session-file check alone, including all 50 made with the chain rebuilt; the provider check caught all of those that touched API-key requests (167 of 167). A relabel in a rebuilt chain: 0 of 50 (0–7%). Truncations that dropped no requests (17) went unnoticed and change no totals.

**5.4 Category check** (Table 3; `category_check.json`, `category_heldout.json`, frozen prompt 4981a32faa4a9d65 on Sonnet). Development, batch 1: 3 of 19 correct labels flagged, 35 of 38 relabels caught. Held-out runs (81): 5 of 81 correct labels flagged, all "unconfirmed" generic code (an LRU cache, an n-gram counter), 0 contradicted; 157 of 162 relabels caught. Held-out written cases: clear 0 of 24 flagged, 48 of 48 relabels caught; borderline 2 of 12 flagged, 22 of 24. Capabilities relabeled as safety: 44 of 44 across all sets. Variance (`category_variance.json`): written cases gave the same pick on all three calls 36 of 36; real runs 47 of 54; the 7 that wavered were utility code (a cache, an n-gram counter, a packing helper) or eval statistics labelled safety (contamination, rater agreement); a majority of three flags 4 of 54 correct labels against 6 of 54 for one call. Rebuilding a real session's work from its session file matched the manifest's files in 20 of 20 sample runs.

**5.5 Claim checker** (Table 4; `claims_summary.json`, re-run over all runs). False "done" (an honest final message paired with untouched code): 98 of 98 caught (95% CI 96–100%). Invented blockers that exist: 9 of 9 caught; true blockers wrongly flagged: 0 of 9; held-out phrasings 2 of 2 and 0 of 4; denials with a spurious claim 0 of 2. Honest runs flagged: 6 of 98 (2–13%), all checker errors: three extraction mistakes on "added tests" (descriptions of the existing tests, and "I only ran the two provided tests"), and three runs that truthfully reported a denied shell command, which the checker reads as a blocker it can test for existence. Report this as a limitation (a "denied" claim type would fix it); the extraction prompt is unchanged since the first commit on Nov 13, before batch 2 (git history of `vawr/claims.py`). One held-out blocker label ("yaml") was corrected after the first round; disclose it. Prompted runs: told to claim work it hadn't done, the agent refused; the blocker run's claim held because the invented package really is missing.

**5.6 Real interactive sessions** (`interactive_check.json`, `interactive_billcheck.json`). `vawr check` passed all three checks: chain intact; all 22 requests in session files were in the log; 730,927 billed tokens, all logged, none unexplained. The bill check from session files alone: 66% matched to session files, 34% to the sessions' cost totals, 0 unexplained. Getting there took two fixes the sessions exposed (say so; it's evidence the test mattered): an earlier rule read these API-key sessions as subscription sessions, and back-to-back sessions confused earliest-first matching, now nearest-minute-first. Re-scoring the batches after both fixes changed no run's score, gap or count (before-and-after files in `work/results/before_fixes/`).

## 6. Discussion (about ¾ page)

- Main point: a usage report needs a record its author doesn't write. Self-reported records missed a billed request in every session launched from the desktop app's environment (62 of 62 in the window), with no bad intent.
- Who would use this, and why: a team that has to account for agent usage to someone else (a funder of API credits, a client, an internal auditor). When the recipient holds the account (programs that issue keys from their own organization), they run the bill check themselves and nothing rests on the team's word. When the team holds it, the recipient relies on the team's bill-check output; a read-only or provider-signed usage statement would close that gap, a concrete ask of providers.
- What it doesn't replace: FinOps tools for internal attribution; proxies for request-level capture.
- How the checks complement each other: the chain catches edits but not a rebuilt chain; session files are free but can be switched off; the provider record doesn't depend on the team's machine but covers one key per minute, about 5 minutes late by Anthropic's documentation, 20–30 minutes in our runs (4–24 hours on the newer API); the category check covers relabels for work whose content shows its purpose.

## 7. Conclusion (about three sentences)

- A team can give an outsider a usage report the outsider can check end to end, from records that already exist.
- In our tests the bill comparison caught every hidden run and flagged no logged one, the category check caught relabels the log couldn't, and on real interactive sessions the log matched the bill to the token.
- The unrecorded request shows that such a report needs at least one record the reporting party doesn't write.

## End matter (doesn't count toward the 8 pages)

- **Code and Data:** repository link (private until release); all code written during the Sprint ("What predates the sprint: nothing"); data in `work/`; identity attributes dropped; usernames appear in file paths.
- **Appendix A, Limitations and Dual-Use / Ethical Considerations (required):** limitations (category content not bound to the log; folder names count as evidence and could be gamed; one model sample unless voting; one key per check; version 2.1.322; 15 small author-written tasks; one operator and one machine; Admin API needs a Console organization). Dual use: the same reconciliation could be used to monitor individuals' agent use; the report drops identity fields, and checks are run by or with the consent of the account holder; disclosing exact gaps could teach evasion of the envelope (about 1,000 input and 1,500 output small-model tokens per logged session).
- **Appendix B:** pilot detail; per-run off-log table; per-window concurrency table; claim-checker and category-check development; variance.
- **LLM Usage Statement:** Claude was used to write code, run experiments, draft text, write the held-out category cases and fact-check numbers; confirm or edit.
- **References:** [1]–[17] as in `report/draft.md`, plus:
  - [18] Anthropic, "What is the External Researcher Access Program?", Claude Help Center, March 16, 2026, https://support.claude.com/en/articles/9125743-what-is-the-external-researcher-access-program
  - [19] anthropics/claude-code issue #3404, July 2025, https://github.com/anthropics/claude-code/issues/3404
  - [20] anthropics/claude-code issue #82274, July–August 2026, https://github.com/anthropics/claude-code/issues/82274
  - [21] ccusage, https://github.com/ryoppippi/ccusage
  - [22] anthropics/claude-code issue #104358, October 2026, https://github.com/anthropics/claude-code/issues/104358
  - [23] anthropics/claude-code issue #106219, October 2026, https://github.com/anthropics/claude-code/issues/106219
  - [24] anthropics/claude-code issue #86879, August–November 2026, https://github.com/anthropics/claude-code/issues/86879
  - [25] frederick-douglas-pearce/claude-code-sessions issue #148, July 2026, https://github.com/frederick-douglas-pearce/claude-code-sessions/issues/148

## Claims to avoid

- That session files are "independent" records.
- That every check was tested (the totals check is a recount).
- That this is the "first" such tool, or that reconciling against billing is a new idea.
- That we discovered Claude Code's background requests, or that the unrecorded one is the session-title request.
- That Lifland proposed hardware attestation.
- That the pilot replay of the envelope is an out-of-sample test.
- That per-category claim rates show a difference between categories.
- That funders currently require usage reports.
- That proxies miss Claude Code's background requests.
- That we discovered session files omitting background requests (reported in [22, 23]).
- That the desktop-entrypoint request affects terminal users (0 of 9 runs without it).
- That the 08:50 clean-window flag certainly came from our test sessions (timing only).

## Addendum (Nov 14 evening): payer mode, Anthropic's session count, continuity

New since outline v3; all numbers from `work/results/summary.md` (sections "Anthropic's Claude Code analytics" and "Continuity"). Suggested places:

- **Section 3 (The Tool), one paragraph:** who checks. `vawr bundle` writes one file (report, checks, report page, whole log); `vawr receive` is run by whoever owns the API key's account, with their own Admin key, so the bill check no longer rests on the team's word. Each result has a level: checked against Anthropic's records, tamper-evident only (no Admin key, or a Claude subscription, for which Anthropic offers no usage records), or failed. `vawr team` checks every key in an organization; keys with usage and no bundle are listed.
- **Section 3, the fourth check (sessions):** Anthropic's Claude Code Analytics API [26] reports each key's Claude Code sessions and tokens by model per UTC day and terminal type, counted on Anthropic's side. The log's sessions and tokens should equal it on any day the log fully covers.
- **Section 5, one short paragraph or a row in Table 1:** on Nov 14, Anthropic counted 91 non-interactive Claude Code sessions on the key; the log has 66; the manifests list 91 runs, 25 of them hidden. The Sonnet and Opus tokens Anthropic counted beyond the log (82,633 and 74,764) equal the bill check's unexplained Sonnet and Opus tokens for that day exactly. The interactive sessions matched exactly (5 sessions, no token difference). Billed minus Anthropic's count is Haiku only (616,117 tokens on Nov 14, plus 9 tokens of an older Haiku), consistent with Anthropic's count leaving out the desktop-entrypoint request. Unlike per-minute billing, this unit is the session, so overlapping hidden runs are counted one by one.
- **Section 5 or Appendix B, continuity:** 200 relabel-and-rebuild trials with an earlier report's head at a random point: 98/98 edits before that head caught, 0/102 after it (by design). This partly answers the 0/50 relabel-and-rebuild row: rebuilding is caught once a recipient holds an earlier head.
- **Section 6 (Discussion):** the no-brainer setup is the payer owning the account and issuing the key; subscription usage stays tamper-evident only, and that is a property of what Anthropic exposes, not of the tool.
- **Pending:** a whole day on the key with every session logged (Nov 15 UTC, 3 interactive and 2 headless sessions) to show the sessions check passing on a complete day; results in `work/demo-20261115/` after 02:00 UTC Nov 15, final after the day closes.
- **Reference:** [26] Anthropic, "Claude Code Analytics API", Claude Platform docs, https://platform.claude.com/docs/en/manage-claude/claude-code-analytics-api
- **Claims to avoid:** that Anthropic's analytics is billing (it's a separate count; it differs from the bill by the desktop request); that the Nov 13 day was checked (the main log started that day; its 26 sessions include pilot and setup runs on the key before it); that Console-login users (by email) were tested; that continuity catches edits after the last head a recipient holds.
