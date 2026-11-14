<!-- DRAFT, not posted. For Chris to review and post (or not) at release time. -->

# With CLAUDE_CODE_ENTRYPOINT=claude-desktop, each API-key session makes a billed Haiku request that appears in no local record

**Version:** Claude Code 2.1.322, macOS, API-key auth, headless (`claude -p --bare`).

## What happens

When `CLAUDE_CODE_ENTRYPOINT=claude-desktop` is set (the Claude desktop app sets it for the
sessions it starts), every API-key session makes one extra request to the small model
(claude-haiku-5-5). Anthropic bills it to the key (it shows in the Admin Usage API at
1-minute resolution: always 7,010 cache-read tokens, 0 cache-creation, a few hundred
input and output tokens), but it appears in none of Claude Code's own records:

- OpenTelemetry `claude_code.api_request` events
- OpenTelemetry token/cost metrics (no `query_source="auxiliary"` data point either)
- the session's JSONL transcript
- `modelUsage` / `total_cost_usd` and the session's `cost-state`

On short `-p` tasks it was 23–54% of each session's billed tokens.

## Evidence

From 131 runs on a dedicated key (details and data:
github.com/CGosK/verified-agent-reports, `work/results/env_ab.json`,
`work/results/env_bisect.json`):

- Every run with `CLAUDE_CODE_ENTRYPOINT=claude-desktop` had the request: 65 of 65.
- No run without it did: 0 of 9.
- Bisection: a clean environment plus only `CLAUDE_CODE_ENTRYPOINT=claude-desktop`
  brings it back; adding `CLAUDE_CODE_EMIT_TOOL_USE_SUMMARIES`,
  `CLAUDE_PREVIEW_CLASSIFIER_FLOOR`, `CLAUDE_CODE_DESKTOP_MESSAGE_CARD`, or all other
  inherited desktop variables together, does not. Removing
  `CLAUDE_CODE_EMIT_TOOL_USE_SUMMARIES` from the desktop environment doesn't stop it.
- `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` doesn't stop it.

## Reproduce

1. Use an API key with Admin Usage API access for its organization.
2. Run a short task with `CLAUDE_CODE_ENTRYPOINT=claude-desktop claude -p "<task>" --model sonnet --bare
   --permission-mode acceptEdits --output-format json` (the flags our runs used; see
   `vawr/runner.py`) with OpenTelemetry export on, then the same without the variable, a
   few minutes apart. We did not test other flag combinations or interactive desktop
   sessions.
3. Compare the Usage API's 1-minute buckets for the key (grouped by model) with the
   OTel events, the transcript and `cost-state`: the first run has an extra
   claude-haiku-5-5 request (cache-read 7,010) in none of them.

## Ask

Record this request wherever Claude Code records the others (an `api_request` event
with its `query_source`, the auxiliary token metric, and `cost-state`), or document
what it is. Related: #104358 (requests missing from transcripts), #82274 (what
"auxiliary" covers).
