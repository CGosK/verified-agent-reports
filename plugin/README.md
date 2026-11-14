# vawr plugin for Claude Code

The Claude Code plugin for [vawr](../README.md): slash commands
`/vawr:billcheck`, `/vawr:setup`, `/vawr:tag`, `/vawr:check`, `/vawr:report`,
`/vawr:bundle`, `/vawr:receive`, `/vawr:team`, `/vawr:status`, and a
session-start hook that keeps the receiver running once
telemetry is set up. Needs Python 3.9+ on PATH; data goes to `~/.vawr`.

`plugin/vawr/` is a copy of the repository's `vawr/` package, so the plugin
installs without the research data; `tests/test_plugin_sync.py` checks the two
are identical. Refresh it with `rsync -a --delete --exclude __pycache__ vawr/ plugin/vawr/`.
