---
description: Label this project's Claude Code sessions as safety, capabilities or other
argument-hint: "safety | capabilities | other"
allowed-tools: Bash
---

!`"${CLAUDE_PLUGIN_ROOT}/bin/vawr" tag $ARGUMENTS --write 2>&1 || true`

Show the output above to the user. If it failed, tell them the category must be one of safety, capabilities or other. Mention that the label applies to sessions started after this. Don't run anything else.
