---
description: Turn on Claude Code telemetry to the local vawr receiver (edits ~/.claude/settings.json, with a backup)
allowed-tools: Bash
---

!`"${CLAUDE_PLUGIN_ROOT}/bin/vawr" setup --write 2>&1; "${CLAUDE_PLUGIN_ROOT}/bin/vawr" start 2>&1 || true`

Show the user what changed (above) in a code block. Tell them to restart Claude Code so new sessions send their events to the receiver, and that `/vawr:tag safety` (or capabilities, other) in a project folder labels that project's sessions. Don't run anything else.
