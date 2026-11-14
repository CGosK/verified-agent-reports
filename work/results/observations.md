# Observations recorded during the runs (UTC, Nov 13, 2026)

- Console Usage page, read by the author at about 21:00: "Data as of Nov 13, 8:40 PM UTC" (about 20 minutes behind).
- Usage API at 21:17: latest minute with usage for the Sprint key was 20:46, although runs had happened at 20:51, 20:53, 20:54, 20:57, 21:00, 21:03, 21:06, 21:09, 21:13 and 21:16 (at least 30 minutes behind).
- Usage API watcher (polling every 2 minutes): the minute 21:29 first appeared at the poll just before 22:01 (it then waited 5 minutes and reported at 22:06), so about 30 minutes behind.
- Anthropic's documentation says usage "typically appears within 5 minutes".
