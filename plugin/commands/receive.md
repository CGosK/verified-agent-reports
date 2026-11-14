---
description: Check a vawr bundle you received - with your own Admin key if you own the API key's account
argument-hint: "<bundle.zip> [--html report.html]"
allowed-tools: Bash
---

!`"${CLAUDE_PLUGIN_ROOT}/bin/vawr" receive $ARGUMENTS 2>&1 || true`

Show the output above to the user unchanged in a code block. Then give the verdict in one sentence: VERIFIED means the figures match the user's own Anthropic records for that key; CONSISTENT means nothing was edited after the fact but nothing was checked against a bill (add ANTHROPIC_ADMIN_KEY to check it); FAILED means a check failed, and name which one in a sentence each. Don't run anything else.
