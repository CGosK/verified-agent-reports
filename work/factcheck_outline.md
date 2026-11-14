# Fact-check: report/outline.md and README.md (results sections)

Checked 2026-11-14 against the repository data only (`work/results/*.json`, `work/manifests/*.json`, run-id lists, logs, `work/provider_minutes.json`, `work/pilot/`, `work/interactive/`, `work/category_dev/`, `work/category_sessions/`, `work/prior_art_billcheck.md`, code in `vawr/`). References [18]–[24] were opened on the web. TBD bisection items skipped. Nothing was run that calls the network, `claude` or the API, or writes into `work/`. The README example was recomputed offline by calling `vawr.billcheck.check(..., provider_minutes=<saved work/provider_minutes.json>)`, which reads `~/.claude/projects` and writes nothing. The 15 task tests were run on a scratch copy of `tasks/repo`.

Verdicts: **CORRECT** (matches data or source), **WRONG** (correct value given), **UNSUPPORTED** (no source found), **FLAG** (the number is right but a qualifier was dropped, the scope drifts, or the wording overclaims). Line numbers are those of the files as checked.

## Most important problems first

1. **Outline L91 (Discussion), WRONG:** "Self-reported telemetry missed a billed request on every API-key session" drops the qualifier the paper's own A/B depends on. Clean-environment sessions made no unrecorded request: 0 of 4 A/B runs (`env_ab.json`) and 0 of 4 interactive sessions (`interactive_check.json`, background_tokens = 0). Say "every API-key session launched from the desktop app's environment (62 of 62)".
2. **Outline L43, reference [24], WRONG:** "18–32% of spend" doesn't match the source. In #86879, 18% is a share of *weighted tokens* (one session) and ~32% is the most pessimistic *modeled* scenario. The one measured spend figure is ~10% (up to 24% in one 40-agent session). Suggested: "roughly 10–30% of spend or tokens in subagent-heavy sessions". The same wording is in `work/prior_art_billcheck.md` L161, which is probably where it came from.
3. **Outline L79, UNSUPPORTED, plus a dropped qualifier in the abstract and README:** the 9-token claude-haiku-4-5 request at 08:50 is stated as coming from "two interactive test sessions". The timing matches: screen logs show launches at 08:50:10 and 08:50:46 (`work/interactive/2026111…085010Z…`, `…085046Z…`). But no record ties the tokens to them. The test session's log entries hold no `api_request`, and the four real interactive sessions made no such request. Write "most likely". Separately, the abstract (L21) and README table (L144) give "5 of 5 windows" but leave out that **1 of 5 clean windows was also flagged** (95% CI 1–72%). The conclusion (L99) also says "flagged no logged one" without mentioning that window.
4. **Outline L56, WRONG count:** "all 37 subscription and 50 API-key session files … separated cleanly". 37 is right (26 batch + 11 pilot). The API-key count is stale: today there are **99 headless API-key session files (90 from batches + 9 from the pilot) plus 4 interactive = 103**. With the current `_signed_in` rule, all 140 files separate cleanly (0 misclassified). 50 = pilot 9 + batch 1 11 + batch 2 30, so it predates the concurrency, A/B and bisection runs.
5. **Outline L21, L81 and README L145, FLAG (overclaim in the headline):** "207 of 207 even with the hash chain rebuilt" reads as if all 207 copies had a rebuilt chain. Only 50 did (`rehash_tokens`). 33 were truncations, which leave the chain valid, and 124 (delete or edit_tokens) were also caught by the chain. Accurate version: "the session-file check alone caught 207 of 207, including all 50 made with the chain rebuilt".

Also important:
- **"9 of 9 invented blockers" (abstract L21, 5.5 L85)** pools 7 development phrasings with 2 held-out ones (`claims_summary.json`: `fake_blocker_caught_dev` 7/7, `held_out` 2/2). One held-out case ("yaml") had its label corrected *after* the run (`vawr/validate.py` L270–272). The correction is justified because PyYAML isn't installed, but it should be disclosed.
- **Outline L50: "plan and seat type are dropped before hashing"** is true of the current receiver, but the published data still carries them: 756 entries in `work/log/events.jsonl` (up to 2026-11-14 08:03 UTC) and 198 in `work/pilot/log/events.jsonl` include `anthropic.plan` and `anthropic.seat_type`. The README discloses this; the outline doesn't. No identity attributes (`user.email`, `user.account_uuid`, `user.account_id`, `user.id`, `organization.id`) appear in any log, and prompts are `<REDACTED>`.
- **Two UNSUPPORTED process claims (5.5, 5.6):** "the extraction prompt was frozen and wasn't tuned on these runs" has no recorded hash (unlike the category prompt). "Batch results were unchanged by both fixes" is only partly checkable: the batch-1 bill check is identical before the fix (`work/samples/billcheck_batch1.json`, 08:18 UTC) and after it (current code), but there's no saved pre-fix copy of `off_log.json` or `false_flags.json`.
- **Held-out set description (outline L72; `summary.md` label):** the 81 "held-out runs" are 35 from batch 2, 30 from concurrency, 8 from the A/B and 8 from the bisection, not "batch 2's runs". `summary.md` labels the row "held out (batch 2)", which is wrong.
- **Related work (L41–43) leaves out the closest prior art** listed in `work/prior_art_billcheck.md`: claude-code-sessions #148, a proposed (never run) reconciliation of Claude Code logs against the Admin cost report. For the four-record finding, write "we found no prior report of" rather than "what is ours" (notes §3c name #101954 and #86375 as nearest).

## Table

| # | Location | Claim | Verdict | Correct value / source | Note |
|---|---|---|---|---|---|
| 1 | Outline L3 | Code in private repo github.com/CGosK/verified-agent-reports | NOT CHECKED | — | Private; no git or network check made. |
| 2 | Outline L14 | Funder of API credits for safety research [18] | CORRECT | [18]: the External Researcher Access Program gives "free API credits" for safety/alignment research | |
| 3 | Outline L21 | 131 runs, Nov 13–14, 2026 | CORRECT | 131 manifests: batch 1 25, batch 2 55, concurrency 35, A/B 8, bisection 8; 2026-11-13T20:51Z to 2026-11-14T10:09Z | Excludes 23 pilot runs and 4 interactive sessions. |
| 4 | Outline L21, L79; README L142 | Provider check caught 26 of 26 hidden runs, 95% CI 87–100% | CORRECT | `off_log.json`; `rate(26,26)` → 0.8677–1 | |
| 5 | Outline L21, L79; README L142 | Flagged 0 of 36 logged runs (0–10%) | CORRECT / FLAG | `off_log.json`: 36 = 8 batch 1 + 20 batch 2 + 8 A/B; CI 0–9.74% | L79 places it "in batches 1–2", but batches 1–2 have 28 logged key runs; the other 8 are A/B runs. |
| 6 | Outline L21; README L144 | 5 of 5 overlapping windows with a hidden run caught (48–100%) | CORRECT / FLAG | `concurrency.json` | Abstract and README leave out that 1 of 5 clean windows was flagged (1–72%). |
| 7 | Outline L21, L81; README L145 | Usage-changing edits caught 207 of 207 (98–100%) "even with the chain rebuilt" | CORRECT / FLAG | `tamper_summary.json`: 24 deletes that touched requests + 100 edit_tokens + 50 rehash_tokens + 33 truncations | Only 50 had the chain rebuilt. The session-file check alone caught all 207; the provider check caught 167 of 167 on Sprint-key requests. |
| 8 | Outline L21, L81; README L146 | Relabel with rebuilt chain caught 0 of 50 (0–7%) | CORRECT | `tamper_summary.json` rehash_category | |
| 9 | Outline L81 | 550 edited copies; chain caught 400 of 400 unrebuilt edits; 17 no-request truncations unnoticed, change no totals | CORRECT | 200+100+100+50+50+50 = 550; chain 200+100+100; 50−33 = 17; `report.build` totals come only from api_request events | |
| 10 | Outline L21; README L146 | Category check caught 157 of 162 relabels of held-out runs; all 44 capabilities→safety relabels | CORRECT | `category_check.json`: held-out 157/162; 44 = 6 dev + 26 held-out runs + 8 clear + 4 borderline cases | 6 of the 44 come from the development set. |
| 11 | Outline L21, L87; README L147 | On four interactive sessions the log equalled the bill to the token | CORRECT | `interactive_check.json`: provider = logged = 730,927 for every token type; 0 gaps | |
| 12 | Outline L21, L85 | Claim checker: 98 of 98 false "done" (96–100%); 9 of 9 invented blockers; 6 of 98 honest runs flagged (2–13%) | CORRECT / FLAG | `claims_summary.json` | 9 = 7 dev + 2 held-out phrasings; the held-out "yaml" label was corrected after the run (`validate.py` L270–272). |
| 13 | Outline L22, L77; README L44 | 62 of 62 desktop-environment API-key sessions made one billed small-model request missing from telemetry events, metrics, session files and cost totals | CORRECT | `false_flags.json` background_by_session: 62/62 inherited, cache_read 7,010 each. Independent check over all 85 Sonnet API-key manifests: no Haiku in any log event or metric, in `model_usage`, or in any of the 79 session files | Provider minutes show exactly k×7,010 Haiku cache-read per minute in the concurrency windows, consistent with one request per session. |
| 14 | Outline L22, L77 | 23–54% of each session's billed tokens | CORRECT | background ÷ (background + logged): 22.7%–54.2%, median 48.5% | Conflicts with `summary.md` "0.0%–50.4% over 37 sessions", which uses a different metric (row 70). |
| 15 | Outline L22, L77; README L47–48 | Clean environment: 0 of 4 vs 4 of 4 | CORRECT | `env_ab.json` | |
| 16 | Outline L77 | "The A/B settled where it comes from" | FLAG | 4/4 vs 0/4, Fisher exact two-sided p≈0.029 | It shows the request depends on the inherited environment, not which variable causes it (bisection TBD). The 4 clean interactive sessions (0 unrecorded) add support. |
| 17 | Outline L22, L77, L87; README L49–54, L149 | Interactive session files left out a third of billed tokens (titles, prompt suggestions, compaction), which telemetry and cost totals included | CORRECT | `interactive_billcheck.json`: 248,395 of 730,927 = 34.0%; recorded_totals = 248,395. Log: titles 5,051 + prompt suggestions 217,279 + compaction 26,065 = 248,395 | Prompt suggestions are 87% of the omission. n = 4 sessions. |
| 18 | Outline L22, L43; README L54–57 | Background requests public before [19, 20] | CORRECT | #3404 (Jul 2025; contributor: "We do use Haiku for some small queries"); #82274 (maintainer lists auxiliary types, Aug 16, 2026) | |
| 19 | Outline L27 | Credits arrive as API credits on one provider account [18] | CORRECT | [18]: credits go to "a single Claude Console organization ID" | |
| 20 | Outline L27 | "Whoever gives them has no checkable account of what they paid for" | FLAG | [18] says a single organization lets a program "monitor usage across your team" | The funder (here Anthropic, or a program holding the organization) can see usage. What it lacks is a checkable account of what the usage was for. |
| 21 | Outline L27–28 | [1] two-part verification; [2] ~6% in one July 2026 week, classifier-labelled; [3] ~10% vs ~16% | CORRECT (vs draft) | Matches `report/draft-full.md` L13–15 | Not re-opened (outside [18]–[24]); draft-full says "coding tasks". |
| 22 | Outline L36 | "We found no released tool that reconciles…" (not "first") | CORRECT | `prior_art_billcheck.md` L237 | |
| 23 | Outline L41 | Anthropic lists cost reconciliation as a use of its usage API [11] | CORRECT | `prior_art_billcheck.md` §1.8 | |
| 24 | Outline L41–42 | None tests reconciliation as a completeness check; ccusage and similar tools don't compare with provider records | CORRECT / FLAG | `prior_art_billcheck.md` §1.1–1.3, §4 | Leaves out claude-code-sessions #148, the closest prior art per the notes (proposed, aggregate, never run). |
| 25 | Outline L42 | ccusage [21] reads local data only | CORRECT | ccusage README: "reads local usage data from coding agent CLIs"; no provider API | |
| 26 | Outline L43 | [22]: session files omit billed background requests that cost totals include, by 1.35–2.13x | CORRECT | #104358 (opened Oct 22, 2026): transcript sum "×1.35–2.13 below" cost-state, measured on 14 sessions | |
| 27 | Outline L43 | [23] measured prompt suggestions alone | CORRECT | #106219 (Oct 30, 2026; v2.1.309): 25 prompt_suggestion requests in OTel, none in the transcript | |
| 28 | Outline L43 | [24]: agent-summary requests skip the transcript and were 18–32% of spend | **WRONG** | #86879: skipTranscript ✓. Shares: 18.0% of weighted tokens; ~10% of estimated spend (up to 24%); modeled 13–32% of spend | Same error in `prior_art_billcheck.md` L161. |
| 29 | Outline L43 | Our interactive measurement replicates [22, 23] | CORRECT | Billed ÷ session-file tokens = 1/0.66 ≈ 1.51x, inside 1.35–2.13x | |
| 30 | Outline L43 | "What is ours is … a request missing from all four records" | FLAG | `prior_art_billcheck.md` §3c, L240 | Phrase as "we found no prior report of"; nearest are #101954 and #86375. |
| 31 | Outline L50 | SHA-256 hash chain; prompts never logged | CORRECT | `chainlog.entry_hash`; every `prompt` field is `<REDACTED>` in all three logs | |
| 32 | Outline L50 | Identity attributes, plan and seat type dropped before hashing | CORRECT (code) / FLAG (data) | `receiver.DROPPED_ATTRIBUTES` | No identity fields in any log, but 756 work/log entries and 198 pilot entries keep plan and seat type; the README discloses this. |
| 33 | Outline L55 | Bill check: ±2 min, zero tolerance, one background request per session inside a pilot envelope | CORRECT | shift_minutes 2; tolerance 0; `BACKGROUND_ENVELOPE` in `auditor.py` | |
| 34 | Outline L56 | All 37 subscription and 50 API-key session files separated cleanly | **WRONG** | 37 ✓. API-key: 99 headless (90 batches + 9 pilot) + 4 interactive = 103; 0 misclassified under current rule | 50 is a pre-concurrency count. |
| 35 | Outline L57 | Category check: Sonnet; confirmed / unconfirmed / contradicted; optional majority of three | CORRECT | `category_check.json` model "sonnet"; verdict values; `category_variance.json` | |
| 36 | Outline L59 | `vawr verify-report`; plugin with slash commands and a session-start hook | CORRECT | `python3 -m vawr --help`; `commands/`, `hooks/hooks.json` | |
| 37 | Outline L59, L92 | Recipient "runs the bill check themselves" | FLAG | `vawr billcheck` reads *local* session files, which a recipient doesn't have | The recipient's path is `vawr check --log <published> --no-coverage` (the provider "Bill" check). The outline uses "bill check" for both. |
| 38 | Outline L64 | 15 tasks, 5 per category; tests fail on stub and pass with reference | CORRECT | `tasks/tasks.json`; all 15 re-run on a scratch copy: stub exit 1, solution exit 0 | |
| 39 | Outline L65 | All Claude Code 2.1.322; dedicated key | CORRECT | `service.version` = 2.1.322 in every entry of all three logs | The key was also used by our own interactive sessions (including the 08:50 test launches). |
| 40 | Outline L66 | Batch 1: 14 key runs (6 off-log), 11 subscription | CORRECT | manifests | 2 of the 11 subscription runs are the prompted claim runs. |
| 41 | Outline L67 | Batch 2: 40 key runs (20 off-log, rotating models, with/without files), 15 subscription | CORRECT | manifests: off-log haiku 7 / sonnet 7 / opus 6; 10 kept session files | All 20 logged batch-2 runs are Sonnet. |
| 42 | Outline L68 | Concurrency: 10 windows × 3 logged runs, 5 s apart, 5 with an off-log run, 35 runs | CORRECT | `concurrency_run_ids.json` + manifests (start gaps ≈5 s) | |
| 43 | Outline L69 | A/B: 8 key runs alternating inherited and clean; bisection 8 runs | CORRECT | `env_ab_run_ids.json`, `env_bisect_run_ids.json`, `env_mode` | Bisection runs (09:47–10:09) fall outside the provider window. |
| 44 | Outline L70 | 4 interactive sessions via expect, clean environment, own config folder; follow-ups, subagent, /compact, Haiku | CORRECT | `work/interactive/sessions.jsonl`, screen logs (`Agent(`, "Compacted", haiku), `claude-config/` | The 08:50 test launch inherited the desktop environment (screen shows CLAUDE_CODE_CHILD_SESSION); the 4 real sessions didn't. |
| 45 | Outline L72 | Developed on batch 1: one prompt revision, one model choice; frozen 4981a32faa4a9d65 | CORRECT | `category_dev/history.json`: v1 haiku (bfd390…), v2 haiku (1338…), v2 sonnet (4981…) | |
| 46 | Outline L72 | Frozen "before scoring batch 2's runs" | FLAG | Held-out 81 = 35 batch 2 + 30 concurrency + 8 A/B + 8 bisection | |
| 47 | Outline L72 | 36 cases by a separate agent, 12 per category, 12 borderline | CORRECT | `category_heldout/cases.json` (8 clear + 4 borderline per category) | Note says the agent didn't see the classifier or tasks; it doesn't say "definitions alone". |
| 48 | Outline L73 | Exact two-sided 95% Clopper–Pearson | CORRECT | `vawr/stats.py`; spot checks match closed form (e.g. 0.025^(1/26) = 0.8677) | |
| 49 | Outline L77 | Pilot: one Haiku request per run, cache-read always 7,010, cache-creation 0 | CORRECT | `work/pilot/provider_minutes.json`: 10 separable minutes, all 7,010/0 | |
| 50 | Outline L77 | `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` didn't stop it [16] | CORRECT | `runner.build_env` sets it on every run; the request was still present in 62/62 | |
| 51 | Outline L77 | "Across all batches … 62 of 62" | CORRECT / FLAG | | "All batches" leaves out the bisection runs (outside the window). |
| 52 | Outline L79 | Window 20:50–09:17 UTC, 747 minutes, no key usage between batches | CORRECT | `false_flags.json` minutes_checked 747; no provider minutes between 21:29 and 05:55 | |
| 53 | Outline L79 | Each hidden run its own gap of 14,463–26,642 tokens; no log excess | CORRECT | `off_log.json`: 26 assigned gaps + 6 unassigned (5 concurrency + 1) = 32; log_excess 0 | |
| 54 | Outline L79; README L143 | Session-file check caught 13 of 13 (75–100%); none missing from files; no token mismatches | CORRECT | `off_log.json`; `false_flags.json` sessions | |
| 55 | Outline L79 | 1 of 5 clean windows flagged, 9 tokens (8 in, 1 out, claude-haiku-4-5) at 08:50 | CORRECT | `concurrency.json` (model id claude-haiku-4-5-20251001) | |
| 56 | Outline L79 | The 9 tokens "came from two interactive test sessions … that minute" | **UNSUPPORTED** | Timing only: screen logs at 08:50:10 and 08:50:46 | No log or record ties them. The test session's log has no api_request; the 4 real sessions made no such request. Write "most likely". |
| 57 | Outline L79 | Bill check from session files found exactly the three batch-1 runs with no local trace | CORRECT | `samples/billcheck_batch1.json`; reproduced with current code | Over the full window, current code finds the 13 no-file runs from batches 1–2, 2 no-file concurrency runs and the 08:50 9 tokens, nothing else (offline recompute, not saved in `work/results`). |
| 58 | Outline L83 | Dev: 3 of 19 flagged, 35 of 38 relabels caught | CORRECT | `category_check.json` dev | |
| 59 | Outline L83 | Held-out 5 of 81 flagged, all "unconfirmed" (LRU cache, n-gram counter), 0 contradicted | CORRECT | 4 c5_ngrams + 1 c4_cache; stubs are `LRUCache` and `count_ngrams` | |
| 60 | Outline L83 | Cases: clear 0/24 and 48/48; borderline 2/12 and 22/24 | CORRECT | `category_heldout.json` | |
| 61 | Outline L83 | Variance: cases 36/36 stable; runs 47/54; majority flags 4/54 vs 6/54 for one call | CORRECT | `category_variance.json` | |
| 62 | Outline L83 | "All wavering items generic code" | FLAG | Wavering: c3_batching, c4_cache ×2, s2_agreement, s3_contamination ×3 | 4 of 7 are safety-labelled eval utilities that flipped to capabilities or other, i.e. contradiction votes, not only "unconfirmed". |
| 63 | Outline L83 | Session rebuild matched manifest files 20 of 20 | CORRECT | `work/category_sessions/extraction_compare.json` (files_same 20/20) | Cite the file. |
| 64 | Outline L85 | 0/9 true blockers flagged; held-out 2/2 and 0/4; denials 0/2 | CORRECT | `claims_summary.json` | Held-out counts are subsets of the 9 and 9. |
| 65 | Outline L85 | 6 honest runs flagged: 3 added-tests extraction errors, 3 truthful denied-shell reports | CORRECT | `claims_real.json` detail; manifests' `permission_denials` confirm the 3 denials | |
| 66 | Outline L85 | Claims "re-run over all runs" | FLAG | 100 logged runs (98 + 2 prompted) | The 31 off-log runs aren't included. |
| 67 | Outline L85 | Extraction prompt frozen, not tuned on these runs | **UNSUPPORTED** | Only a `validate.py` L267–268 comment and pilot v1/v2 files | No prompt hash or freeze record. |
| 68 | Outline L85 | Prompted runs: refused to lie; blocker claim held (package really missing) | CORRECT | manifests 20261113T205549Z / 205601Z; `claims_summary.json` prompted_runs | |
| 69 | Outline L87 | Two fixes: subscription misread; nearest-minute matching | CORRECT | `billcheck.py` L44–52 comment; `auditor.match_minutes` docstring | |
| 70 | Outline L87 | "Batch results were unchanged by both fixes" | **UNSUPPORTED** (partly) | Batch-1 bill check identical pre-fix (`samples/billcheck_batch1.json`) and post-fix | No pre-fix copy of `off_log.json` or `false_flags.json`. |
| 71 | Outline L91 | "Self-reported telemetry missed a billed request on every API-key session" | **WRONG** | 62/62 desktop-environment sessions; 0/4 clean A/B; 0/4 interactive | Dropped qualifier. |
| 72 | Outline L94 | Provider record "~5 minutes to 30 minutes late (4–24 hours on the newer API)" | FLAG | Observed 20–30 min (`results/observations.md`); ~5 min is Anthropic's documented figure; 4–24 h ✓ (prior_art §1.9) | README L104 says 20–30; make them consistent. |
| 73 | Outline L99 | "Caught every hidden run and flagged no logged one" | CORRECT / FLAG | | Mention the one flagged clean window. |
| 74 | Outline L104 | All code written during the Sprint | CORRECT (weak) | No file in the repo is dated before Nov 13 (mtime) | |
| 75 | Outline L105 | Envelope ≈1,000 input and 1,500 output small-model tokens per session | CORRECT | `BACKGROUND_ENVELOPE` (also 7,010 cache-read) | |
| 76 | Outline L109 | [18] title, Help Center, March 16, 2026, URL | CORRECT | Page opened; shows Mar 16, 2026 | |
| 77 | Outline L110 | [19] #3404, July 2025 | CORRECT | Opened Jul 12, 2025 | |
| 78 | Outline L111 | [20] #82274, July–August 2026 | CORRECT | Opened Jul 29; maintainer reply Aug 16; closed Sep 15, 2026 | |
| 79 | Outline L112 | [21] ccusage URL | CORRECT | Page opened | |
| 80 | Outline L113 | [22] #104358, October 2026 | CORRECT | Opened Oct 22, 2026; open | |
| 81 | Outline L114 | [23] #106219, October 2026 | CORRECT | Opened Oct 30, 2026; open | |
| 82 | Outline L115 | [24] #86879, August–November 2026 | CORRECT | Opened Aug 15; closed Nov 9, 2026 | |
| 83 | README L23–35 | 46-min window: billed 238,904; session files 96,605 (40.4%); background 83,546 (35.0%, 11 sessions); unexplained 58,753 (24.6%) at 21:06/16,095, 21:19/16,016, 21:29/26,642; 0 local-only | CORRECT | Recomputed from saved provider minutes with current code; identical to `samples/billcheck_batch1.json` | |
| 84 | README L38–39 | The three minutes are the runs with telemetry and session files off; nothing else flagged | CORRECT | c4_cache, o4_config, s4_redact (off_log_no_files) | |
| 85 | README L41 | "Two things stand out on any API-key account" | FLAG | | Scope drift: one key, one machine, 2.1.322, desktop environment. |
| 86 | README L47 | "About half of each session's billed tokens" | CORRECT / FLAG | Median 48.5%, range 22.7–54.2% | Give the range. |
| 87 | README L47–49 | "The same runs with a clean environment made no such request" | FLAG | A/B alternated different tasks | Not the same runs. |
| 88 | README L58 | "The bill check accounts for all of this, and anything else shows up" | FLAG | `BACKGROUND_ENVELOPE` | Overclaim: Haiku usage inside the per-session allowance (≤1,000 in, 1,500 out, 7,010 cache-read) is absorbed, including in clean sessions that never use it. |
| 89 | README L59–61 | Another machine, a script, a leaked key "all show up" | FLAG | | Only "session files off" was tested; the rest follow from the method (subject to the envelope). |
| 90 | README L135–138 | 131 runs on a dedicated key and a subscription, Nov 13–14, 2.1.322, plus 4 interactive | CORRECT | 105 key + 26 subscription runs | |
| 91 | README L137–138 | "Exact 95% intervals are in work/results/summary.md" | FLAG | | Pooled 26/26, 13/13, 207/207 and 0/36 have no CI in summary.md (only in `paper_numbers.json`). |
| 92 | `work/results/summary.md` category table | "Logged runs, held out (batch 2)" | **WRONG** (label) | 81 = 35 batch 2 + 30 concurrency + 8 A/B + 8 bisection | |
| 93 | `work/results/summary.md` | Background share "0.0%–50.4% over 37 sessions" | FLAG | Different metric (span share, non-shared sessions only, incl. 4 clean at 0%) | Inconsistent with outline's 23–54% over 62; pick one definition. |
| 94 | `work/results/paper_numbers.json` | `provider_logged_flagged_batches_1_2_ab_bisect`, "includes A/B and bisect runs inside the window" | **WRONG** (label/note) | No bisection run is in the window; n = 36 = 28 + 8 A/B | Numbers are right. |
| 95 | `paper_numbers.json` (all other values) | Runs by batch, CIs, interactive, claims, category, variance | CORRECT | Each recomputed from the underlying files | |

## Counts

- WRONG: 5. Three in the outline: rows 28 ([24]), 34 (50 session files) and 71 ("every API-key session"). Two are labels in data files the outline relies on: rows 92 and 94.
- UNSUPPORTED: 3 (rows 56, 67, 70).
- FLAG (number right, wording or scope problem): 23 rows marked FLAG, alone or with CORRECT. Most important: 6, 7, 12, 30, 32, 46, 88.
- Not checked: the private repo link (row 1).
