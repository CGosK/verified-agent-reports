---
description: What Anthropic billed your API key vs what Claude Code recorded on this machine
argument-hint: "[how far back: 24h, 7d, ...]"
allowed-tools: Bash
---

!`"${CLAUDE_PLUGIN_ROOT}/bin/vawr" billcheck --since "$ARGUMENTS" 2>&1 || true`

Show the output above to the user unchanged in a code block. Then, in two or three plain sentences, say what it means for them: "background requests" are billed requests Claude Code makes but doesn't record locally; "unexplained" minutes are billed usage no session file on this machine accounts for (another machine or script using the key, a run with session files off, or a leaked key). If it failed because keys are missing, say it needs ANTHROPIC_ADMIN_KEY (an Admin key for the organization) and ANTHROPIC_API_KEY in the environment or a .env file. Don't run anything else.
