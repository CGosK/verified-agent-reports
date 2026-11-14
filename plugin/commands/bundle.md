---
description: Write one file to send whoever pays for your API key - usage report, checks and log
argument-hint: "--since 30d [--project NAME] [--title TEXT]"
allowed-tools: Bash
---

!`"${CLAUDE_PLUGIN_ROOT}/bin/vawr" bundle $ARGUMENTS 2>&1 || true`

Show the output above to the user unchanged in a code block. Then say in two or three sentences where the file is, what the recipient runs (`vawr receive <file>`), and anything the output flags: a failed check, other projects' sessions in the log, or no API key ID recorded. If it says "Not written", explain the reason in one sentence. Don't run anything else.
