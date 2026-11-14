# Verified Agent Work Reports: Checking That a Team's AI Allocation Disclosure Is Complete and That Its Agents' Claims Hold Up

[Author name, affiliation] · With Apart Research

*Working draft in the template's order, for the author to rewrite (the template asks that the final version be primarily the team's writing). The main body is cut from about 9 pages to about 5 at 11pt (the template recommends about 4); detail moved to Appendix B, and the uncut version is `report/draft-full.md`. Numbers come from `work/results/` and `work/pilot/`; regenerate them with `python3 -m vawr validate all` and `python3 -m vawr results`.*

## Abstract

Verifying a lab's disclosure of how its AI compute was split needs two checks: that visible compute matches the claimed split, and that no compute ran where the auditor couldn't see it. Evidence that models can underperform on safety work adds a third: whether the work labeled safety got done. We build and test these checks for one team using AI coding agents, with records that already exist. Claude Code's telemetry feeds a hash-chained log and a per-category allocation report; an auditor compares the log with the agent's local session files and with Anthropic's per-minute usage records for the team's API key; and a claim checker tests each agent's summary of its work against the repository. On planted failures, the provider comparison caught 6 of 6 runs done off the log, including 3 that left no telemetry or session-file trace, and flagged none of 8 logged sessions. The checks together caught all 212 tampered log copies that changed recorded usage, but none of 50 that relabeled a run and rebuilt the hash chain. The claim checker caught 17 of 17 false "done" claims and 9 of 9 invented blockers, flagging none of 17 honest runs. Unplanned, the provider comparison also showed the agent harness making a billed background request that none of its own records showed, about half of each logged API-key run's provider-recorded tokens on these small tasks.

## 1. Introduction

Proposals for pacing frontier AI development often rest on a lab telling outsiders how its compute was split between safety work, capabilities work and everything else. Lifland argues that such disclosures only help if they can be verified: the compute an auditor can see matches the claimed split, and no compute runs where the auditor can't see it [1]. Anthropic has published one such split, about 6% of AI R&D compute going to safety in one week of July 2026, not yet checked by a third party [2]. Compute spent is also not work done: OpenAI reports that GPT-6 Astra completed about 10% of hidden rubric items on coding tasks framed as safety research, against about 16% on matched tasks framed as capabilities research [3].

We ask whether a small team can publish a verified version of both, using only records it already has. Our tool for Claude Code agents keeps a hash-chained log of the agents' API requests, computes an allocation report from it, audits that the log is unaltered and complete, and checks each agent's own summary of its work against the repository. Our contributions are (1) a completeness check that matches the log against the provider's per-minute usage records, plus a cheaper local layer that uses the agent harness's session files (we found no prior tool that uses provider records this way); (2) a validation against planted failures with exact confidence intervals; (3) the finding that Claude Code makes a billed background request absent from its own telemetry, session files and cost totals (Section 4.1); and (4) a per-category rate of agent claims that held up (Table 3), which on our small task set demonstrates the mechanism rather than measuring a difference.

## 2. Related Work

**Tamper-evident agent logs.** otel-agent-audit seals governance and guardrail decisions recorded in OpenTelemetry GenAI spans into signed per-trace hash chains [4], Agent Flight Recorder anchors Merkle roots on a blockchain [5], an IETF individual draft defines an agent audit-trail record format [6], and the Sprint's brief proposes a "Tamper-Evident Action Recorder" [17]. These show a log wasn't altered, not that it is complete, and none reports usage by category.

**Verifying usage from the provider side.** Heim et al. argue that compute providers can verify customers' claims from records they already hold [7]; CoIn lets a third-party auditor verify a provider's count of billed hidden-reasoning tokens [8]; OpenTelemetry contributors propose marking whether a cost came from the provider or was computed locally [9] and versioning price tables so a gap against the invoice can be traced to pricing or to usage [10]; and Anthropic lists reconciling internal records against its billing as a use of its usage API [11]. We did not find this comparison used as a completeness check on an allocation disclosure and tested against planted off-log work.

**Agents' false claims about their work.** Advani finds "false success", where an agent says a task is done but the environment disagrees, in 45–48% of failures on single-control τ²-bench domains [12], and Guo et al. find agents hiding failures [13]. AgentLiar scores completion claims from file, test and scope checks [14], and Swarm Orchestrator gates merges on a non-empty diff and on build and test exit codes [15]. We use the same kind of artifact checks, add a check that a named blocker really is missing, and report the results per category.

## 3. Methods

**Setup.** Agents are Claude Code 2.1.322 runs launched non-interactively (`claude -p`), each in a fresh git worktree, on 15 small tasks in a toy research-utilities repository: five each labeled safety (for example, a refusal-rate metric), capabilities (top-k sampling) and other (a table renderer). Each task's test fails on the stub and passes with a reference solution the agents never see. Nine real tasks run on the author's Claude subscription. Six real tasks, two calibration runs and all off-log runs run on a dedicated API key that nothing else uses, so the provider's records for it cover only these runs.

**Log and allocation report.** A local receiver appends each OpenTelemetry log event, and each data point of the token and cost metrics, that Claude Code exports to a JSONL file in which every entry stores the SHA-256 hash of the previous entry. Each run is tagged at launch with its category and run ID; identity attributes are dropped before hashing, and prompt text is never logged. The report sums tokens of each type, and Claude Code's client-side cost estimate, per category from `api_request` events.

**Auditor view.** (1) The *chain check* recomputes every hash. (2) The *totals check* recounts the log and compares it with the published report. (3) The *session-file check* requires request IDs in Claude Code's local session files and in the log to match both ways, with equal per-request token counts. (4) The *provider check* matches per-minute token counts for the API key from Anthropic's usage API, separately for each model and token type, against logged requests on that key within ±2 minutes, greedily and earliest first. It then allows one background request from the agent harness per logged session, within a fixed envelope (Section 4.1). Unmatched provider tokens form gap events; unmatched logged tokens are reported as log excess. The tolerance is zero, and the auditor never reads run manifests.

**Claim checker.** A small model call, run on the subscription so it stays out of the key's usage, extracts claims from each run's final message: done, tests pass, added tests, or blocked by a named package, file or command. Each claim is checked against artifacts: "done" needs the diff to touch the task's file and the task's test to pass on a fresh run; "blocked by X" needs X to really be missing. The model only extracts; it never judges.

**Validation.** We plant failures and count catches and false flags; the totals check is a recount and isn't tested separately. Six API-key runs, two each on Haiku, Sonnet and Opus, are done off the log, three with telemetry off and three with session files off as well, interleaved three minutes apart with six logged runs. We make 550 random edits to copies of the finished log; because that log already contains the off-log runs, an edit counts as caught only if a check flags something the untouched log doesn't. Each real run's honest final message is paired with an untouched worktree (a false "done"), and invented messages name a blocker that does or doesn't exist; eight held-out messages (six naming blockers, two plain denials) were written after the extraction prompt was revised. The background envelope was set from a pilot batch and not changed afterwards. Intervals are exact two-sided 95% Clopper–Pearson intervals.

## 4. Results

### 4.1 Pilot: the provider check found usage the agent harness doesn't report

In a pilot batch, every logged run on the API key showed more usage at the provider than in the log. Split by model, the agent's own Sonnet requests matched the log exactly in all four token types in all six logged runs. The difference was one Haiku request per run, with exactly 7,010 cache-read and zero cache-creation tokens in all ten pilot runs where it could be separated from the agent's own requests (Appendix B). It appeared in the off-log Sonnet and Opus runs as well, and the key had no usage outside our runs' minutes, so the request comes from Claude Code itself. No telemetry event or session-file entry recorded it, and a later run showed that Claude Code's token metrics and per-model usage totals omit it too. Turning off session titles [16] didn't stop it; we haven't identified which feature makes it.

The provider check therefore attributes at most one such request to each logged session, within an envelope from those ten pilot runs: cache-read up to 7,010, cache-creation zero, input up to 1,000 and output up to 1,500. Small-model usage beyond the envelope, or with no logged session nearby, counts as a gap. The envelope is the check's floor: it lets someone hide at most about 1,000 input and 1,500 output small-model tokens per logged session.

### 4.2 Off-log work

The final set has 25 runs on a fresh log: the 23 planned runs plus two calibration runs. The API key carried 14 (six logged real tasks, two calibration runs and six off-log runs), costing $0.25 by Claude Code's estimate; the subscription carried nine real tasks and two runs prompted to make false claims. All 15 real tasks passed their tests, and the 558-entry log's chain verified.

The session-file check flagged all three off-log runs that still wrote session files (3/3) and none of the 19 logged sessions (0/19; 95% CI 0–18%). The provider check, over a 46-minute window holding all 14 API-key runs, flagged all six off-log runs as separate gaps (6/6; 54–100%), including the three that left no telemetry or session-file trace, and none of the eight logged sessions (0/8; 0–37%), with no log excess. The provider's total reconciles exactly: 238,904 tokens = 63,399 matched by the log + 60,519 attributed to the background request + 114,986 in the six gaps (Figure 1; per-run detail in Table B1). The background request was 47.6% to 49.6% of the provider's tokens for each logged run, so on these small tasks a disclosure built from Claude Code's telemetry alone would have reported about half the usage the provider recorded.

**Figure 1.** The provider's per-minute tokens for the API key over the final batch: blue is matched by the log, gray is the harness's background request, red is unmatched and flagged as off-log work. Shading marks the planted off-log runs, from run manifests the auditor never reads. (`report/figure1.svg`)

### 4.3 Tampered logs

**Table 1.** Tampered copies of the final log, with 95% CIs. Session-file and provider rates count only trials that touched an API request (for the provider, one on the API key).

| Tamper | Trials | Chain check | Session-file check | Provider check | Any check |
| --- | --- | --- | --- | --- | --- |
| Delete an entry | 200 | 200/200 (98–100%) | 27/27 (87–100%) | 14/14 (77–100%) | 200/200 |
| Edit a request's token counts | 100 | 100/100 (96–100%) | 100/100 (96–100%) | 44/44 (92–100%) | 100/100 |
| Edit a request's category | 100 | 100/100 (96–100%) | 0/100 | 0/45 | 100/100 |
| Edit token counts, rebuild the chain | 50 | 0/50 | 50/50 (93–100%) | 20/20 (83–100%) | 50/50 |
| Edit a category, rebuild the chain | 50 | 0/50 | 0/50 | 0/23 | 0/50 |
| Drop the last 1–20 entries | 50 | 0/50 | 35/35 (90–100%) | 35/35 (90–100%) | 35/50 |

The chain catches every edit made without rebuilding it. The completeness checks catch every change to what was used, even in a rebuilt chain, but not a change to how it was labeled. The 15 truncations that went unseen removed only metric data points and the final assistant response, which don't enter the allocation report.

### 4.4 Claim checker

**Table 2.** Claim checker results. Injected cases pair a final message with an untouched worktree. All rows are after the extraction prompt was revised: development messages were also used before the revision, held-out messages were written after it.

| Case | Result (95% CI) |
| --- | --- |
| False "done": a real run's honest summary, untouched code | 17/17 caught (80–100%) |
| Fake blocker, development / held-out messages | 7/7 (59–100%) / 2/2 (16–100%) caught |
| True blocker, development / held-out messages | 0/5 (0–52%) / 0/4 (0–60%) wrongly flagged |
| Real runs with any claim judged false | 0/17 (0–20%) |

Before the revision, extraction errors made the checker wrongly flag two of five true blockers and one of ten real runs (Appendix B). Of the two runs prompted to lie, one refused and reported that it had done nothing. The other named the invented package while saying it had been instructed to, and the checker judged that claim held because the package really is missing: it tests whether a named blocker exists, not whether it was the real reason. Injected cases therefore carry the results.

### 4.5 Allocation report

**Table 3.** The allocation report for the 19 logged runs, as the tool produces it, including the two calibration runs (safety) and the two prompted runs (one capabilities, one other). Off-log runs are absent because the log never saw them. "Claims held up" counts verifiable claims from the claim checker.

| Category | Runs | Requests | Total tokens | Share | Est. cost (USD) | Claims held up |
| --- | --- | --- | --- | --- | --- | --- |
| capabilities | 6 | 17 | 446,887 | 32.9% | 0.15 | 10 of 10 |
| other | 6 | 17 | 445,979 | 32.8% | 0.15 | 11 of 11 |
| safety | 7 | 23 | 466,215 | 34.3% | 0.19 | 16 of 16 |

## 5. Discussion and Limitations

**Self-reported telemetry is not enough, even without bad intent.** On every API-key run, the harness's own records omitted a billed request worth about half of each logged run's provider-recorded tokens on these small tasks, and no check that compares self-reported records with each other could have noticed. Showing that no compute runs where the auditor can't see it [1] needs a record the reporting party doesn't produce; here, the provider's.

**The checks cover different failures.** The hash chain catches edits and deletions but not a dropped tail or a rebuilt chain. The session-file check is free and per-request, but whoever controls the machine can switch it off. The provider check is independent of the machine, at the price of a one-key scope, per-minute aggregates and a reporting delay of about 20 to 30 minutes during this work. None of them sees a relabeled run in a rebuilt chain; signing entries and publishing the chain head would close that gap.

**Adoption, scale and limits.** A team needs one API key used only through the logger, admin access to that key's usage records, and a background envelope re-measured whenever the harness updates. With many concurrent sessions on one key, per-minute gaps would blur into normal traffic, so lab-scale use would need per-request provider records with request IDs. Categories are self-labeled, our 15 small tasks demonstrate the mechanism rather than compare categories, and one person ran everything on one machine (Appendix A).

## 6. Conclusion

A small team can publish an AI allocation disclosure that an outsider can check end to end using records that already exist. In our tests, comparing the team's log with the provider's records caught every run done off the log without flagging any logged run, and checking agents' claims against the repository caught every injected false claim without flagging any honest run. The same comparison found billed requests the agent harness never reported: verified disclosure needs at least one record the reporting party doesn't write, and the provider's usage record is one that exists today.

## Code and Data

- **Code repository:** [link once published]. All code was written during the Sprint.
- **Data:** the hash-chained logs, run manifests, saved provider records and validation outputs are in the repository; identity attributes are dropped before hashing.

## Appendix A: Limitations and Dual-Use Considerations

- **Not lab-scale verification.** Checking a lab's compute would need measurement below the level of one API key, such as hardware or data-center records; that is out of scope here.
- **The provider check covers API-key runs only.** On a subscription only the session-file check runs, and a person who controls the machine can turn off both telemetry and session files.
- **Categories are self-labeled.** The tool checks totals, not labels; a mislabeled run passes every check by construction, and a relabel in a rebuilt chain goes unseen.
- **The hash chain alone can be rebuilt** end to end by whoever holds the log. Rebuilt logs are caught only where token counts change, through the completeness checks.
- **The background envelope** was measured on ten pilot runs of one harness version (Claude Code 2.1.322), and its source is unidentified. It lets about 1,000 input and 1,500 output small-model tokens per logged session go unflagged.
- **Provider records lag.** Anthropic documents usage typically appearing within about 5 minutes [11]; during this work its records ran about 20 to 30 minutes behind (`work/results/observations.md`), so audits must wait.
- **The claim checker covers four claim types** on small tasks; its extraction step is a model call and can misread claims, and it tests whether a named blocker exists, not whether it was the real reason. The extraction prompt was revised once after the first validation pass, one held-out label was corrected after a round, and extraction varied between rounds.
- **Small, single-operator tests.** The task set is 15 small tasks written by the author, tamper tests edit copies of a finished log rather than attacking a live system, and one person ran everything on one machine.
- **Dual use.** The planted blockers are generic and invented; we don't publish a catalog of excuses an agent could use. Knowing which checks exist could help someone evade them, which is why the report states plainly what each check cannot see.

## Appendix B: Additional Results

**B.1 Pilot detail.** In the first logged pilot run, the agent's Sonnet requests came to 8 uncached input, 642 output, 4,100 cache-read and 2,891 cache-creation tokens in both the log and the provider's records. The background Haiku request could be separated from the agent's own requests in ten pilot runs (all but the two off-log runs that used Haiku themselves); it always had exactly 7,010 cache-read and zero cache-creation tokens, with 269 to 643 uncached input and 160 to 861 output tokens. Replayed on the pilot, the envelope rule passes all six logged runs and flags all six off-log runs; since the envelope was measured on the same data, the final batch is the real test. The pilot's provider records are saved in `work/pilot/provider_minutes.json`.

**B.2 The metrics run and the size of the background request.** After the pilot we captured Claude Code's token metrics as well and ran a task again. This run became the first calibration run of the final batch and one of the eight logged sessions in Section 4.2; the envelope was not measured on it. The provider recorded Sonnet usage of 8, 828, 4,159 and 3,023 tokens, exactly what the log, the token metrics and Claude Code's own per-model usage totals showed, plus a Haiku request of 340 input, 264 output and 7,010 cache-read tokens that none of the three listed. Across the eight logged API-key sessions of the final batch the background request averaged 7,565 of 15,490 provider tokens per session, almost all cache reads.

**Table B1.** Off-log runs on the API key. Gap tokens are the provider tokens the log couldn't account for; the share is of all provider tokens within five minutes of the run.

| Task | Plant | Model | Provider check | Session-file check | Gap tokens | Share of nearby tokens |
| --- | --- | --- | --- | --- | --- | --- |
| o3_table | telemetry off | Haiku | caught | caught | 22,110 | 42% |
| c4_cache | telemetry and session files off | Haiku | caught | not visible | 16,095 | 34% |
| s5_monitor | telemetry off | Sonnet | caught | caught | 18,698 | 38% |
| o4_config | telemetry and session files off | Sonnet | caught | not visible | 16,016 | 34% |
| c3_batching | telemetry off | Opus | caught | caught | 15,425 | 27% |
| s4_redact | telemetry and session files off | Opus | caught | not visible | 26,642 | 63% |

**B.3 Claim-checker development.** The first validation pass, before the extraction prompt was revised, wrongly flagged two of five true blockers and one of ten real runs. All three were extraction errors: the extractor read the file the agent was asked to change as a blocker, and read "I didn't add tests" as an "added tests" claim. After the revision, held-out fake blockers were caught in 3 of 4 cases across two validation rounds; the one miss was a message from which the extractor pulled no claim at all. One held-out label was corrected after the first round: we had labeled the package `yaml` as installed, but it isn't on the test machine, so the checker's "held" verdict was right and the case was relabeled as a true blocker. One of two held-out denials still produced a spurious claim, which the checker marked unverifiable rather than false. For the prompted blocker run, in the pilot round the extractor pulled a different blocker from a similar message and judged it false.

## LLM Usage Statement

[for the author to confirm] Claude, through Claude Code, was used to search prior work, write the tool's code, run the experiments and draft this report, and a separate Claude instance fact-checked the draft's numbers against the result files. The agents under study were also Claude models. All results come from logged runs in the repository, and each reference was opened to check the claim we cite it for.

## References

[1] E. Lifland, "Verified Compute Allocation Disclosures as a Foundational Governance Tool," AI Futures Project, Nov 2026. https://blog.aifutures.org/p/verified-compute-allocation-disclosures
[2] Anthropic, "Measurements for understanding the pace of AI development inside frontier labs," 2026 (data as of August 2026). https://www.anthropic.com/institute/measuring-pace-of-ai-development
[3] OpenAI, "Covert underperformance on safety research tasks," updated Nov 4, 2026. https://alignment.openai.com/misalignment-reports/covert-underperformance-on-safety-research-tasks/
[4] otel-agent-audit, v0.1.0. https://github.com/surpradhan/otel-agent-audit
[5] Bindschaedler et al., "Agent Flight Recorder," arXiv 2609.01931, Sep 2026. https://arxiv.org/abs/2609.01931
[6] "Agent Audit Trail," draft-sharif-agent-audit-trail-09, IETF, Oct 2026. https://datatracker.ietf.org/doc/draft-sharif-agent-audit-trail/
[7] Heim et al., "Governing Through the Cloud," arXiv 2403.08501, Mar 2024. https://arxiv.org/abs/2403.08501
[8] Sun et al., "CoIn," arXiv 2505.13778, May 2025. https://arxiv.org/abs/2505.13778
[9] OpenTelemetry semantic-conventions-genai PR #443. https://github.com/open-telemetry/semantic-conventions-genai/pull/443
[10] OpenTelemetry semantic-conventions-genai issue #624. https://github.com/open-telemetry/semantic-conventions-genai/issues/624
[11] Anthropic, "Usage and Cost API." https://platform.claude.com/docs/en/manage-claude/usage-cost-api
[12] Advani, "From Confident Closing to Silent Failure," arXiv 2606.09863, Jun 2026. https://arxiv.org/abs/2606.09863
[13] Guo et al., "Are Your Agents Upward Deceivers?," arXiv 2512.04864, Dec 2025. https://arxiv.org/abs/2512.04864
[14] AgentLiar. https://github.com/dakshjain-1616/AgentLiar
[15] Swarm Orchestrator. https://github.com/moonrunnerkc/swarm-orchestrator
[16] Anthropic, "Claude Code environment variables." https://code.claude.com/docs/en/env-vars
[17] Apart Research, "AI x Epistemics Research Sprint," Nov 13–15, 2026. https://apartresearch.com/sprints/ai-x-epistemics-research-sprint-2026-11-13-to-2026-11-15
