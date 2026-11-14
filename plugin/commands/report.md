---
description: Write a shareable HTML usage report with the checks someone else can rerun
argument-hint: "[how far back: 7d, 30d, ...]"
allowed-tools: Bash
---

!`v="${CLAUDE_PLUGIN_ROOT}/bin/vawr"; d="${VAWR_HOME:-$HOME/.vawr}"; mkdir -p "$d"; "$v" check --since "$ARGUMENTS" --json "$d/last_check.json" >/dev/null 2>&1; "$v" report --since "$ARGUMENTS" --out "$d/last_report.json" --html "$PWD/vawr-report.html" --check "$d/last_check.json" 2>&1 | tail -3 || true`

Tell the user where the HTML report was written (shown above), that it is one self-contained file they can send, and that the recipient can check it against the published log with `vawr verify-report` and, if they hold the account's Admin key, `vawr check --no-coverage`. Keep it to three sentences. Don't run anything else.
