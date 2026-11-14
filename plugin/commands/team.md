---
description: For an organization admin - check everyone's vawr bundles against the organization's Anthropic records, key by key
argument-hint: "<bundle.zip> [<bundle.zip> ...]"
allowed-tools: Bash
---

!`"${CLAUDE_PLUGIN_ROOT}/bin/vawr" team $ARGUMENTS 2>&1 || true`

Show the output above to the user unchanged in a code block. Then list, in one line each, every key marked NO REPORT (usage nobody reported) and every FAIL (with what failed). If everything passed, say so in one line. Don't run anything else.
