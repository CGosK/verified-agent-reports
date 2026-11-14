<!-- DRAFT, not posted. For Chris to review and post (or not) at release time. -->

# Proposal: reconcile ccusage's numbers with Anthropic's billing records

ccusage reads Claude Code's session files, which leave out some billed requests:
session titles, prompt suggestions and compaction in interactive sessions (see
anthropics/claude-code#104358, #106219), and, in sessions started from the Claude
desktop app, one small-model request per session that no local record shows. In our
measurements session files missed about a third of what four interactive sessions were
billed for.

For API-key users with an Admin key, Anthropic's Usage API reports billed tokens per key
in 1-minute buckets. A `ccusage reconcile` (or `--reconcile`) mode could compare those
buckets with the session files minute by minute and show:

- billed tokens the session files account for,
- billed tokens only the sessions' own cost totals (`cost-state`) account for,
- billed tokens no local record explains (another machine or script using the key, a
  leaked key, sessions with transcripts off).

We built and validated this in vawr (MIT, Python, stdlib only):
github.com/CGosK/verified-agent-reports, `vawr/billcheck.py`. Happy to help port the
logic or contribute a PR if it fits ccusage's design.
