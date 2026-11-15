---
description: See what a payer sees, with no keys - three sample bundles checked, Anthropic's records replayed
argument-hint: "[--html <folder>]"
allowed-tools: Bash
---

!`"${CLAUDE_PLUGIN_ROOT}/bin/vawr" demo $ARGUMENTS 2>&1 || true`

Show the user the three verdicts and each one's Why line from the output above, in a short list: an honest day (VERIFIED), batch runs with 25 hidden from the log (FAILED, with the unexplained tokens), and a report edited after the fact (FAILED). Say in one sentence that the checks ran on their machine while Anthropic's records were replayed from saved responses, and that `/vawr:receive` with their own Admin key checks live records. Don't run anything else.
