# Prior art for the vawr bill check

Research date: 14 Nov 2026 (web only). Every link below was opened during this research. Quotes are kept to short phrases; everything else is paraphrase.

Labels used:
- **Confirmed**: stated on the linked page.
- **Inference**: our reading, not stated on the page.

Version context: our finding is on Claude Code 2.1.322. Many reports below are on 2.1.2xx–2.1.31x, and Claude Code changes cost reporting often (e.g. the changelog for 2.1.325 changes `/cost` and the cost metrics to count mod model calls).

---

## 1. Tools and Anthropic surfaces that report Claude Code / Anthropic API usage and cost

### 1.1 ccusage
- Link: https://github.com/ryoppippi/ccusage (opened 14 Nov 2026; ~19.4k stars)
- What it does: reads local usage data written by coding-agent CLIs (Claude Code, Codex, Gemini CLI, etc.) and reports daily/weekly/monthly/session token use, with USD cost computed from a LiteLLM price table. The README describes no use of Anthropic's Usage/Cost API or any provider billing data.
- Related accuracy history: ccusage issue #888 (opened 11 Mar 2026, closed 17 May 2026, https://github.com/ryoppippi/ccusage/issues/888) found deduplication kept an intermediate usage snapshot, under-counting output tokens. The fix keeps the more complete entry. That was detected by re-parsing the JSONL files, not by comparing against Anthropic.
- Reconciles against provider billing? No. Granularity: per day/session from local files.
- Overlap with the bill check: same local data source as our "local side"; no provider-side comparison, so it cannot see billed requests that never reach the transcript.

### 1.2 Other local-file / local-telemetry readers
- **Claude-Code-Usage-Monitor**: https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor (~8.8k stars). Reads Claude data directories, prices tokens locally, and labels figures such as `local_estimate`. It has an opt-in `--api` mode for the Claude *OAuth usage* (plan-limit) endpoint, not the Admin Usage/Cost API. No provider-billing comparison described.
  - Overlap with the bill check: none on reconciliation.
- **SoHoT `soh ledger`**: issue #1160, opened 23 Oct 2026, closed 24 Oct 2026, https://github.com/unxmaal/SoHoT/issues/1160. It found transcripts under-record output tokens by about 3x because final usage records are often not written. `soh ledger --compare DAY` lines up OTel, ccusage and transcript figures, and it now prefers OTel.
  - Overlap with the bill check: compares several *local* sources against each other per day. None of them is Anthropic's record.
- **runway-ai-usage-tracker**: issue #1073, opened 29 Oct 2026, https://github.com/s3ntin3l8/runway-ai-usage-tracker/issues/1073, and issue #1283, opened 9 Nov 2026, https://github.com/s3ntin3l8/runway-ai-usage-tracker/issues/1283. #1073 says transcripts record only main-loop messages and miss the client's own small-model (Haiku) side calls. #1283 plans to match transcripts to OTel `api_request` events by request ID. It reports that an interactive session logged Haiku `generate_session_title` calls in OTel that no transcript contained.
  - Overlap with the bill check: closest in spirit, a completeness check on local records, but it compares transcripts to OTel and does not use Anthropic's usage API. Both issues are open and plans as of 14 Nov 2026.
- **firekeeper**: issue #15, opened 27 Oct 2026, https://github.com/DanBradbury/firekeeper/issues/15. Transcript event sums came in below `/cost`. The author lists Haiku calls as billed but absent from the transcript, with the `ai-title` record carrying no token counts. The proposed fix is to read Claude Code's `cost-state` record.
  - Overlap with the bill check: compares the transcript against Claude Code's own `/cost`, not against provider records.

### 1.3 claude-code-sessions #148: a proposed reconciliation against the Admin API (never run)
- Link: https://github.com/frederick-douglas-pearce/claude-code-sessions/issues/148 (opened 19 Jul 2026, open, `priority:low`, `research`)
- What it does: proposes pricing every session in a window from local logs and comparing the total with the Admin API cost report for the same workspace and window. It says outright that this is aggregate, not per-session. A 21 Jul comment says the check is blocked because Admin keys need a Console organization, and the check was never run.
- Overlap with the bill check: **the closest prior art we found**. It is the same idea at much coarser granularity (workspace/day cost), proposed but not built or run.

### 1.4 techymara/token-usage PR #1 (access barrier example)
- Link: https://github.com/techymara/token-usage/pull/1 (merged 20 Sep 2026)
- What it does: a cost report that called `/v1/organizations/cost_report` and `usage_report/messages` got `permission_error`, so the project switched to ccusage.
- Overlap with the bill check: none. It shows the practical barrier: the Admin API is not available to individual Console accounts until they set up an organization (Confirmed on Anthropic's Usage and Cost API page).

### 1.5 Claude Code's own `/usage` (formerly `/cost`) and OpenTelemetry
- Links: https://code.claude.com/docs/en/costs and https://code.claude.com/docs/en/monitoring-usage (opened 14 Nov 2026)
- What it does: `/usage` shows session tokens and a dollar figure computed locally at list price (or at `modelPricing` rates). The docs call it an estimate and point to the Console for authoritative billing. OTel exports `claude_code.cost.usage` / `token.usage` metrics with `query_source` in {main, subagent, auxiliary, plugin_*}, plus an `api_request` event documented as logged for each API request. The monitoring page says "Cost metrics are approximations."
- Reconciles against provider billing? No. Granularity: per request (events), metric export interval (metrics).
- Overlap with the bill check: these are two of our "local side" sources. Anthropic itself says they are estimates, so we should not present "local figures are estimates" as a finding.

### 1.6 Claude Agent SDK cost fields (`usage`, `modelUsage`, `total_cost_usd`)
- Link: https://code.claude.com/docs/en/agent-sdk/cost-tracking (opened 14 Nov 2026)
- What it does: documents that `total_cost_usd`/`costUSD` are client-side estimates from a bundled price table and should not drive billing. The top-level `usage` field counts only the main loop, while `modelUsage`/`total_cost_usd` include subagents.
- Overlap with the bill check: local self-report only; no provider comparison.

### 1.7 Claude Console Usage and Cost pages
- Link: https://support.claude.com/en/articles/9534590-cost-and-usage-reporting-in-console (opened 14 Nov 2026; page says "Updated over 3 weeks ago")
- What it does: the Usage page shows usage by model, API key and workspace, daily by default, with hour and minute detail when you click into a bar, plus CSV export. The Cost page shows daily cost by model and workspace and says it cannot break cost down by individual user.
- Reconciles against local records? No. Granularity: down to minute (Usage page), daily (Cost page).
- Overlap with the bill check: this is the same provider-side data, viewable by hand. Nothing on the page compares it with client records.

### 1.8 Usage and Cost Admin API (now labelled legacy), which vawr uses
- Link: https://platform.claude.com/docs/en/manage-claude/usage-cost-api (opened 14 Nov 2026)
- What it does: `/v1/organizations/usage_report/messages` reports token counts in `1m`/`1h`/`1d` buckets (1m: default 60, max 1,440 buckets per request). It can be filtered and grouped by API key, workspace, model, service tier, context window, inference geo and speed. Data typically appears within 5 minutes. `/cost_report` is daily only. The page lists "Cost reconciliation" (matching internal records with Anthropic billing) as an intended use. It notes the API is "a legacy API and remains supported" and points new integrations to the Usage and Cost Analytics API. It is not available to individual Console accounts or claude.ai Team orgs.
- Reconciles? It is the data source. Anthropic documents reconciliation as a use but ships no reconciliation tool.
- Overlap with the bill check: this is our provider side. **We cannot claim the reconciliation idea is new**, because Anthropic's own docs name it as a use case. What we add is a tool that does it automatically, per minute, against Claude Code's local records.

### 1.9 Usage and Cost Analytics API (new, beta)
- Link: https://platform.claude.com/docs/en/manage-claude/usage-cost-analytics-api (opened 14 Nov 2026; beta header `analytics-usage-cost-2026-08-24`)
- What it does: `/v1/organizations/analytics/usage` and `/analytics/cost` with `1m`/`1h`/`1d` buckets (at most 24 h per request with `1m`). It adds a **`requests` count**, `product` (e.g. `products[]=claude_code`), `actor` and `api_key_id` dimensions, and a cost endpoint that also accepts 1m/1h. Freshness is typically within 4 hours, up to 24 hours, and values can be revised until about 7 days after month end. `session_id` is a Managed Agents dimension, not a Claude Code session.
- Reconciles? No.
- Overlap with the bill check: a richer provider-side source. Per-minute request counts and a Claude Code product filter could tighten the check. Its 4–24 h latency is worse than the legacy endpoint's ~5 min.

### 1.10 Claude Code Analytics API (per-user Claude Code reporting)
- Link: https://platform.claude.com/docs/en/manage-claude/claude-code-analytics-api (opened 14 Nov 2026)
- What it does: `/v1/organizations/usage_report/claude_code` returns **daily** records per actor (user email or API key name). Records cover sessions, lines of code, commits, PRs, tool accept/reject counts, and per-model tokens with `estimated_cost`. Data is up to 1 hour delayed, and there are no real-time metrics.
- Reconciles? No. It reports estimated cost, not billed cost.
- Inference: the productivity fields (lines, accept/reject) can only come from the client. The costs page also says Claude Code "does not send metrics from your cloud back to Anthropic", so cloud-provider usage is missing from this API. Together these suggest the data is client-reported telemetry. If so, it would share the client's blind spots. Not confirmed.
- Overlap with the bill check: per-user Claude Code view, daily and estimated. Not a check against billing.

### 1.11 Console Claude Code dashboard
- Link: https://code.claude.com/docs/en/analytics (opened 14 Nov 2026)
- What it does: `platform.claude.com/claude-code` shows daily spend, lines accepted, active users and sessions, plus a per-member spend table. The page notes the spend figures are estimates and points to the Cost page for actual costs.
- Overlap with the bill check: none (estimates, daily, no comparison).

### 1.12 Anthropic cookbook and partner integrations
- Cookbook, https://platform.claude.com/cookbook/observability-usage-cost-api (18 Aug 2025): queries and exports usage and cost data. It has no step that compares against client logs.
- Honeycomb, https://docs.honeycomb.io/integrations/anthropic-usage-monitoring/: pulls Admin API usage at `1m` and cost at `1d` into Honeycomb. No Claude Code telemetry comparison is described.
- Datadog Agent Console setup, https://docs.datadoghq.com/ai_agents_console/setup/: offers both the Anthropic Usage and Costs integration (daily spend per Claude product) and Claude Code OTel. It maps identities across tools but describes no reconciliation between the two sources.
- Overlap with the bill check: Datadog is the only product we found that ingests both a provider-side source and Claude Code OTel. We found no documented comparison between them.

---

## 2. Proxy/gateway-based tracking with Claude Code (ANTHROPIC_BASE_URL)

### 2.1 Anthropic's gateway documentation
- Links: https://code.claude.com/docs/en/llm-gateway and https://code.claude.com/docs/en/llm-gateway-protocol (opened 14 Nov 2026)
- What it does: says a gateway at `ANTHROPIC_BASE_URL` can log every model request. Claude Code sends the gateway the same headers and body it sends to `api.anthropic.com`, apart from a small set of direct-connection diagnostics and defaults. It documents an `x-claude-code-request-class` header (`main`, `subagent`, `workflow`, `compaction`, `auxiliary`) that is "Sent on every request". `auxiliary` covers side requests such as session titles, classifiers and summaries. It also documents `x-claude-code-session-id`. Admins can force all traffic to the gateway with `allowedProviders: ["customEndpoint"]` (v2.1.285+).
- Overlap with the bill check: by design, a gateway at `ANTHROPIC_BASE_URL` should see Claude Code's background requests too, and can label them. **We found no documentation or report of a Claude Code Messages API request that bypasses `ANTHROPIC_BASE_URL`.** The real difference: a proxy sees only traffic routed through it, such as a session started without the base URL, or another client using the same key. Provider records cover the key whatever the route.

### 2.2 LiteLLM proxy
- Links: https://docs.litellm.ai/docs/tutorials/claude_code_customer_tracking and https://docs.litellm.ai/docs/harness/claude_code (opened 14 Nov 2026)
- What it does: route Claude Code via `ANTHROPIC_BASE_URL` and attribute spend by customer/tag headers. The harness page says Claude Code makes small background calls (titles, summaries) and that they are billed and tagged like the main model's calls. Anthropic's costs page names LiteLLM as a way to track spend per key.
- Overlap with the bill check: captures background calls that pass through it, but its spend comes from its own price table, not Anthropic's records. No reconciliation against Anthropic is described.

### 2.3 Helicone
- Link: https://docs.helicone.ai/integrations/anthropic/claude-code (opened 14 Nov 2026)
- What it does: set `ANTHROPIC_BASE_URL` to Helicone's Anthropic proxy. The page says the method is "maintained but no longer actively developed" and doesn't address background requests.
- Overlap with the bill check: proxy-side capture only.

### 2.4 Portkey
- Link: https://portkey.ai/docs/integrations/libraries/claude-code-anthropic (opened 14 Nov 2026)
- What it does: `ANTHROPIC_BASE_URL=https://api.portkey.ai` plus Portkey headers. Logs record cost, tokens and latency per request. The example config sets `ANTHROPIC_DEFAULT_HAIKU_MODEL` but doesn't say whether background requests are covered.
- Overlap with the bill check: proxy-side capture only.

### 2.5 OpenRouter
- Link: https://openrouter.ai/docs/guides/guides/claude-code-integration (opened 14 Nov 2026)
- What it does: Claude Code talks to OpenRouter directly. Usage is billed to OpenRouter credits and shown on its Activity page. The page lists `ANTHROPIC_DEFAULT_HAIKU_MODEL` for "Haiku-class tasks" but doesn't say background calls are covered.
- Overlap with the bill check: here the proxy is also the biller, so its activity log is the billing record. That is a different setup from a developer billed directly by Anthropic.

### 2.6 Langfuse
- Link: https://langfuse.com/integrations/developer-tools/claude-code (opened 14 Nov 2026)
- What it does: the documented Claude Code integration is a Stop hook that **reads Claude Code's transcripts** and converts them to traces. It is not a proxy. The page also offers the Langfuse AI Gateway as a proxy alternative.
- Overlap with the bill check (Inference): the hook-based integration inherits the transcript's gaps, so it cannot see requests the transcript omits.

### 2.7 Wire-capture tools: claude-trace, claude-tap, mitmproxy
- claude-trace: https://github.com/badlogic/lemmy/tree/main/apps/claude-trace. It patches `fetch()` inside Claude Code. **By default it logs only `/v1/messages` requests with more than 2 messages.** `--include-all-requests` logs everything, including single-message requests.
  - Overlap with the bill check (Inference): the default setting would hide single-message side requests (title, quota probe), so "not seen in claude-trace" is not evidence of absence.
- claude-tap: https://github.com/liaohch3/claude-tap. A local reverse/forward proxy that records each request/response pair with a token breakdown. It doesn't say whether background requests are covered.
- Kir Shatrov, "Reverse engineering Claude Code", April 2025, https://kirshatrov.com/posts/claude-code-internals. Uses a mitmproxy reverse proxy via `ANTHROPIC_BASE_URL`. Notes `claude-3-5-haiku` is used for simpler calls (Bash command parsing) and shows the new-topic prompt.
- Overlap with the bill check: all of these see the wire, not the bill. Most of the reports in section 3 used exactly this proxy method.

### 2.8 Claude apps gateway (Anthropic, self-hosted)
- Link: https://code.claude.com/docs/en/claude-apps-gateway (opened 14 Nov 2026)
- What it does: an Anthropic-built self-hosted gateway, aimed mainly at Bedrock/Vertex/Foundry/AWS but also supporting an Anthropic API upstream. It adds SSO, per-user attribution, OTLP metrics with token counts, and per-user spend limits.
- Overlap with the bill check: a gateway-side view of usage. No reconciliation against provider billing is described.

---

## 3. Public reports that Claude Code under-counts billed usage or makes unshown background requests

### 3a. Background (often Haiku) requests are known and partly documented
- **anthropics/claude-code #3404**, opened 12 Jul 2025, https://github.com/anthropics/claude-code/issues/3404. Asks why `/cost` listed Haiku when Sonnet was selected. A contributor (rboyce-ant, 13 Jul 2025) replied: "We do use Haiku for some small queries", e.g. checking Bash commands.
- **Yuyz0112/claude-code-reverse**, README "New Version (July 2025)", https://github.com/Yuyz0112/claude-code-reverse. Captured requests by monkey-patching the SDK. Reports a startup request with the text "quota" (likely a quota check) and a new-topic check, both on Haiku 3.5.
- **George Sung, "Tracing Claude Code's LLM Traffic"**, 26 Jan 2026, https://georgesung.substack.com/i/185830843/appendix. Logged requests through a patched Ollama. Shows lightweight-model calls for the title and an `isNewTopic` check, plus Bash-output path extraction and next-prompt suggestion.
- **#47003**, opened 12 Apr 2026, https://github.com/anthropics/claude-code/issues/47003 (v2.1.104). Describes a startup quota probe, a real API call with content "quota", `max_tokens: 1`, `source: quota_check`. The model is not named on the page.
- **#49563**, opened 16 Apr 2026, https://github.com/anthropics/claude-code/issues/49563 (v2.1.112). Debug log shows a startup `/v1/messages` request tagged `source=quota_check`. The root cause turned out to be a hook.
- **#97074**, opened 25 Sep 2026, open, https://github.com/anthropics/claude-code/issues/97074 (v2.1.282). A proxy A/B found interactive sessions send more requests than `claude -p`: "a max_tokens: 1 quota check and a title request". The models aren't named.
- **#82274**, opened 29 Jul 2026, https://github.com/anthropics/claude-code/issues/82274. Maintainer bcherny (16 Aug 2026) defined OTel `query_source="auxiliary"` as "everything else Claude Code calls the model for on your behalf". Examples: compaction, session titles, memory extraction, prompt suggestions, permission/auto-mode classifiers, web-fetch summarization. He said a docs update would follow. Closed as stale 15 Sep 2026.
- **#85922**, opened 11 Aug 2026, https://github.com/anthropics/claude-code/issues/85922 (v2.1.227, behind a gateway). `generate_session_title` ran on the configured Haiku model, while the idle `away_summary` recap ran on Opus. The data came from "request-level telemetry", source unspecified.
- **Mervin Praison, "Claude Code Secretly Calls Haiku to Title Every Session"**, 2 Sep 2026, https://mer.vin/news/claude-code-secretly-calls-haiku-to-title-every-session/ (CLI 2.1.258, 20 `claude -p` runs).
  - Each fresh session makes a billed `claude-haiku-4-5` title call.
  - It appears in `modelUsage` and `total_cost_usd` but not in top-level `usage`. The transcript gets only an `ai-title` line.
  - Passing `-n <name>` suppressed it in 5/5 runs.

### 3b. Billed requests missing from Claude Code's own records

**Missing from transcripts:**
- **#104358**, opened 22 Oct 2026, open, https://github.com/anthropics/claude-code/issues/104358.
  - Background requests are billed but write no usage row to the transcript: `agent_summary`, `auto_mode`, `compact`, `away_summary`, `generate_session_title`, `extract_memories`, `prompt_suggestion`, "and others".
  - Transcript sums run 1.35–2.13x below Claude Code's own `cost-state`.
  - Asks for a usage row for every billed request.
- **#106219**, opened 30 Oct 2026, open, https://github.com/anthropics/claude-code/issues/106219 (v2.1.309). OTel recorded 25 `prompt_suggestion` requests absent from the transcript, costing $1.52 against $3.54 for the main requests.
- **#86879**, opened 15 Aug 2026, closed 9 Nov 2026, https://github.com/anthropics/claude-code/issues/86879. `agent_summary` spinner requests use `skipTranscript: true`, so they appear in no transcript. They were measured at roughly 18–32% of spend in some sessions. Closed after `CLAUDE_CODE_DISABLE_AGENT_PROGRESS_SUMMARIES` was added.

**Missing from `/cost` / `/usage`:**
- **#90952**, opened 31 Aug 2026, closed as stale 2 Nov 2026, https://github.com/anthropics/claude-code/issues/90952 (v2.1.251).
  - A read-only reverse proxy found extra short requests tied to gated tool calls, on the full Sonnet model, not Haiku.
  - The reporter says these requests appear nowhere in `/cost` or `/usage`.
  - Measured at 8.8% of cost across 64 sessions.
- **#33887**, opened 13 Mar 2026, closed as stale, https://github.com/anthropics/claude-code/issues/33887. The statusline cost appeared to exclude the "Haiku (background agents)" line that `/cost` showed.

**Missing from `modelUsage` / `total_cost_usd`:**
- **#101954**, opened 14 Oct 2026, open, https://github.com/anthropics/claude-code/issues/101954 (v2.1.299).
  - A stream-json `set_model` switch sends one non-streaming "Hi" request to the new model (a Haiku model in the repro).
  - It appears in no `modelUsage`, `total_cost_usd`, stream frame or transcript. OTel was not checked.
  - Found with a local API stub at `ANTHROPIC_BASE_URL`.

**Missing from OTel:**
- **#86375**, opened 13 Aug 2026, closed as stale 19 Oct 2026, https://github.com/anthropics/claude-code/issues/86375 (v2.1.229, `claude -p`).
  - In auto mode, 6 of 15 proxy-observed billed requests (about 39% of tokens) had no `api_request` event and no `token.usage` point. The model isn't named.
  - A commenter: classifier costs missing from telemetry.
- **#98193**, opened 29 Sep 2026, open, https://github.com/anthropics/claude-code/issues/98193 (v2.1.251–2.1.284). In joined OTel data, `api_request` was missing for most text-bearing responses. Side queries (`auto_mode`, `agent_classifier`, `agent_summary`) logged neither event.
  - Counter-evidence: a community comment (3 Nov 2026) could not reproduce on 2.1.311/2.1.317. It reports `generate_session_title`, `prompt_suggestion`, `compact` and `web_fetch_apply` all got `api_request` events.
- **#59942**, opened 17 May 2026, https://github.com/anthropics/claude-code/issues/59942 (2.1.128–2.1.144). `query_source` was empty on all OTel events and metrics, so spend could not be attributed to main, subagent or auxiliary.

**Double billing and older mismatches:**
- **#87763**, opened 18 Aug 2026, closed as stale, https://github.com/anthropics/claude-code/issues/87763. A session-start `claude-haiku-4-5` sidecar request was sent twice concurrently and both copies were billed, matched by upstream request ID from a forward proxy.
- **#1835**, opened 9 Jun 2025, https://github.com/anthropics/claude-code/issues/1835 (v1.0.17). `/cost` and the Console usage/logs pages disagreed on the Haiku/Sonnet split. It could not be reproduced and was closed.

Note: most of these issues have no maintainer reply and were closed by the stale bot. Only #3404, #82274 and #86879 have Anthropic-side responses.

### 3c. Closest match to our finding
- We found **no public report** of the exact combination we observe on 2.1.322: one billed Haiku request per session absent from all of OTel events, OTel metrics, session files and cost totals, and not stopped by `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1`.
- **The session-title request is probably not it** (Inference from public reports, not our data):
  - The title request shows up in `modelUsage`/`total_cost_usd` (Praison).
  - It shows up in `/cost` (firekeeper #15).
  - It gets OTel `api_request` events on 2.1.311/2.1.317 (#98193 comment; runway #1283).
- **The interactive startup `quota_check` probe is the best public candidate** (Inference):
  - It is reported only in interactive sessions (#97074), uses `max_tokens: 1` with the content "quota" (#47003), and was on Haiku in 2025 (Yuyz0112).
  - We found no report of whether it reaches OTel, `/cost` or transcripts.
  - If our unexplained minute buckets show about 1 output token and a handful of input tokens on the Haiku model, that would fit this shape.
- **Nearest published "absent everywhere" reports**:
  - #101954: absent from `modelUsage`, `total_cost_usd` and the transcript; OTel not checked.
  - #86375: absent from OTel; model not named.

---

## 4. Reconciling an agent's own logs against provider billing as a completeness/audit check

Beyond the items we already cite (otel-agent-audit, Agent Flight Recorder, draft-sharif-agent-audit-trail, Heim et al., CoIn, OTel GenAI PR #443 / issue #624, Microsoft Agent Governance Toolkit, AgentLiar):

- **Anthropic Usage and Cost API docs, "Cost reconciliation" use case**: https://platform.claude.com/docs/en/manage-claude/usage-cost-api. Anthropic lists matching internal records with Anthropic billing as a purpose of the API, without a tool or method.
  - Overlap with the bill check: the concept is endorsed by the provider; our contribution is an implementation aimed at an agent's own records.
- **claude-code-sessions #148** (19 Jul 2026), see 1.3: a proposed aggregate reconciliation of log-derived Claude Code cost against the Admin cost report. Never run.
  - Overlap with the bill check: same direction (agent logs vs provider records), at workspace/day granularity, unbuilt.
- **FinOps LLM, "Invoice reconciliation for AI spend"**, 21 May 2026, https://finopsllm.com/research/invoice-reconciliation: a monthly close process that diffs the provider invoice/export against gateway or SDK telemetry per model and token type, with a ~1–2% tolerance. It does not single out "billed but not logged" as a check.
  - Overlap with the bill check: same family of practice (finance reconciliation), monthly, not per-minute or per-agent.
- **"AI Usage Cost Reconciler" skill (agensi)**, https://www.agensi.io/skills/llm-usage-cost-attribution-reconciler (no author/date shown): deterministic record-level reconciliation of user-supplied, normalized bills, usage events and prices into READY/REVIEW/BLOCK findings. It does not query providers.
  - Overlap with the bill check: a generic reconciler; no Claude Code or Anthropic usage-API integration.
- **Proxy-vs-self-report comparisons** (#86375, #90952, #101954, #87763 above): investigators compared Claude Code's self-reports against a wire capture.
  - Overlap with the bill check: same completeness logic, but the reference record is a proxy log, not the provider's billing record.
- **Provider-honesty auditing papers** (the opposite trust direction; they audit the provider's bill, not the client's logs):
  - Sun et al., "Invisible Tokens, Visible Bills", arXiv:2505.18471, 24 May 2025, https://arxiv.org/abs/2505.18471
  - Velasco et al., "Auditing Pay-Per-Token in Large Language Models", arXiv:2510.05181, 5 Oct 2025 (rev. 23 Mar 2026), https://arxiv.org/abs/2510.05181
  - Hoque et al., "Token Inflation", arXiv:2605.30040, 28 May 2026 (rev. 7 Nov 2026), https://arxiv.org/abs/2605.30040
  - Overlap with the bill check: related framing (billing records as audit evidence). They treat provider records as untrusted, while we treat them as the reference for checking the client. Worth one sentence acknowledging the trust assumption.
- **Agent auditability papers** (conceptual support):
  - Zhao et al., "Auditable Claims about AI Agents", arXiv:2610.07459, 5 Oct 2026, https://arxiv.org/abs/2610.07459: argues claims need "coverage by an independent record".
  - Nian et al., "Auditable Agents", arXiv:2604.05485, v1 7 Apr 2026 (v4 27 Sep 2026), https://arxiv.org/abs/2604.05485.
  - Overlap with the bill check: neither, from the abstracts, uses provider billing or usage records as that independent record. The bill check is a concrete instance of their "independent record" idea.

We found no paper that reconciles an agent's logs against a provider's billing or usage records as a completeness check.

---

## What we can and can't claim

**Can claim (conservatively, as of 14 Nov 2026, based on a web search):**
- "We found no released tool that automatically reconciles Claude Code's local records (session files, OTel, cost totals) against Anthropic's own usage records." The only reconciliation against the Admin API we found is a proposal, claude-code-sessions #148, which is aggregate (workspace/day) and was never run.
- "We found no tool that does this per minute per API key." Anthropic's Console Usage page and Usage API expose minute-level data, but nothing we found compares them with client records.
- "Because the check reads Anthropic's records for the key, it does not depend on Claude Code's traffic being routed through a proxy, and it also covers usage on the key from other clients." State this as a property of the method, not as a proxy failure.
- "On Claude Code 2.1.322 we observed one billed Haiku request per session that we could not find in OTel events, OTel metrics, session files or cost totals; we found no public report of that exact combination." The nearest are #101954 and #86375.

**Can't claim:**
- That we discovered Claude Code makes background Haiku requests. This has been public since 2025 (Kir Shatrov, Apr 2025; #3404, Jul 2025, with a contributor confirming it; Yuyz0112, Jul 2025), and a maintainer listed the auxiliary request types in #82274 (Aug 2026).
- That we discovered billed requests missing from Claude Code's own records. That is reported many times for transcripts (#104358, #106219, #86879), `/cost` (#90952), `modelUsage`/`total_cost_usd` (#101954) and OTel (#86375, #98193).
- That reconciling internal records against Anthropic billing is a new idea. Anthropic's docs list "Cost reconciliation" as a use of the Usage and Cost API, and FinOps guides describe monthly invoice reconciliation.
- That proxies miss Claude Code's background requests. Anthropic documents an `x-claude-code-request-class` header "Sent on every request", including `auxiliary`, and most published discoveries of hidden requests used a proxy. We found no evidence of a Claude Code Messages API call that bypasses `ANTHROPIC_BASE_URL`. Hook/transcript-based "integrations" (e.g. Langfuse's) and default-filtered tracers (claude-trace) can miss side requests, but true proxies should not.
- That the unexplained request is the session-title call. Public reports put title calls in `modelUsage`/`total_cost_usd`, `/cost` and (on 2.1.31x) OTel `api_request`. Identify it before naming it. The startup `quota_check` probe is a plausible but unconfirmed candidate.
- That "local cost figures are estimates" is a finding. Anthropic says so in the `/usage`, OTel and Agent SDK docs.

**Caveats to state in the README:**
- The Admin API needs a Console organization: individual Console accounts must create one, and claude.ai Team orgs can't use it.
- The endpoint vawr uses is now labelled legacy, though still supported. Its successor (beta) adds per-minute `requests` counts and a `claude_code` product filter but has 4–24 h freshness.
- Minute buckets are per key, not per session or request. Concurrent sessions or other clients on the same key fall into the same bucket.
- Results are version-specific: Claude Code's cost reporting changed in 2.1.325, after our 2.1.322 tests.
