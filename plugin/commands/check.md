---
description: Audit the vawr log - hash chain intact, every local session logged, bill accounted for
argument-hint: "[how far back: 24h, 7d, ...]"
allowed-tools: Bash
---

!`"${CLAUDE_PLUGIN_ROOT}/bin/vawr" check --since "$ARGUMENTS" 2>&1 || true`

Show the output above to the user unchanged in a code block, then explain any FAIL line in one sentence each (chain: the log was edited; coverage: sessions on this machine that never reached the log; bill: billed usage the log doesn't account for). If everything passed, say so in one line. Don't run anything else.
