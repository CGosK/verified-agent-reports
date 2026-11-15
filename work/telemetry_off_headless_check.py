"""Anthropic's count of the three headless sessions run at 11:22-11:24 UTC Nov 15 on the main
key: one with DISABLE_TELEMETRY=1, one with CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1, one
control with neither (work/results/telemetry_off_otel_*.json; vawr logged all three). No other
headless session ran on that key that day, so the "non-interactive" count is 1 if only the
control is counted. Polls from 12:25 until the row appears or 13:45 UTC."""
import json, sys, time
from datetime import datetime, timezone
sys.path.insert(0, ".")
from vawr import billcheck, usage_api
admin, _ = billcheck.admin_and_key()
KEY = "apikey_014nm6SadTU7zy9DoURcd48j"
name = next(k["name"] for k in usage_api.api_keys(admin) if k["id"] == KEY)
while datetime.now(timezone.utc) < datetime(2026, 11, 15, 12, 25, tzinfo=timezone.utc):
    time.sleep(60)
def counts():
    by = {}
    for r in usage_api.claude_code_day(admin, "2026-11-15"):
        if (r.get("actor") or {}).get("api_key_name") == name:
            t = r.get("terminal_type")
            by[t] = by.get(t, 0) + ((r.get("core_metrics") or {}).get("num_sessions") or 0)
    return by
while True:
    by = counts()
    print(datetime.now(timezone.utc).strftime("%H:%M"), by, flush=True)
    if "non-interactive" in by:
        time.sleep(300); by = counts(); break
    if datetime.now(timezone.utc) >= datetime(2026, 11, 15, 13, 45, tzinfo=timezone.utc):
        break
    time.sleep(300)
mins = usage_api.minute_usage(admin, KEY, datetime(2026, 11, 15, 11, 22, tzinfo=timezone.utc),
                              datetime(2026, 11, 15, 11, 25, tzinfo=timezone.utc))
out = {"checked_at": datetime.now(timezone.utc).isoformat(), "by_terminal": by,
       "non_interactive_counted": by.get("non-interactive", 0), "headless_sessions_run": 3,
       "headless_control_sessions_run": 1, "billed_11_22_to_11_25": mins}
json.dump(out, open("work/results/telemetry_off_headless.json", "w"), indent=1)
print(json.dumps({k: out[k] for k in ("non_interactive_counted", "headless_sessions_run")}), flush=True)
