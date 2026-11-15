---
description: Check a vawr bundle you received - with your own Admin key if you own the API key's account
argument-hint: "<bundle.zip> [--html report.html]"
allowed-tools: Bash
---

!`"${CLAUDE_PLUGIN_ROOT}/bin/vawr" receive $ARGUMENTS 2>&1 || true`

Show the output above to the user unchanged in a code block. Then give the verdict in one sentence: VERIFIED means the figures match the user's own Anthropic records for that key; CONSISTENT means the log and report hold together but something couldn't be checked against the user's Anthropic records (the output's Why line says what: no Admin key, a day the session count couldn't confirm, subscription usage, or a period that hasn't ended); FAILED means a check failed: say which, from the Why line. Then show the output's Summary line. Don't run anything else.
