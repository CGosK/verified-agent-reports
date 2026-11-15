"""Which variable hides a session from Anthropic's Claude Code Analytics? Nov 15, 2026
09:50 UTC, main key: 2 sessions with only DISABLE_TELEMETRY=1 (TERM=vt52) and 2 with only
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 (TERM=vt320). The earlier test (both set,
TERM=vt220) counted 0 of 2, the control (TERM=vt100) 2 of 2. Waits until 10:55 UTC (the
control took about an hour to appear), then polls until 12:30."""
import json, sys, time
from datetime import datetime, timezone
sys.path.insert(0, ".")
from vawr import billcheck, usage_api
admin, _ = billcheck.admin_and_key()
KEY = "apikey_014nm6SadTU7zy9DoURcd48j"
name = next(k["name"] for k in usage_api.api_keys(admin) if k["id"] == KEY)
start = datetime(2026, 11, 15, 10, 55, tzinfo=timezone.utc)
while datetime.now(timezone.utc) < start:
    time.sleep(60)
def counts():
    by = {}
    for r in usage_api.claude_code_day(admin, "2026-11-15"):
        if (r.get("actor") or {}).get("api_key_name") == name:
            t = r.get("terminal_type")
            by[t] = by.get(t, 0) + ((r.get("core_metrics") or {}).get("num_sessions") or 0)
    return by
while datetime.now(timezone.utc) < datetime(2026, 11, 15, 12, 30, tzinfo=timezone.utc):
    by = counts()
    print(datetime.now(timezone.utc).strftime("%H:%M"), by, flush=True)
    if datetime.now(timezone.utc) >= datetime(2026, 11, 15, 11, 20, tzinfo=timezone.utc) or ("vt52" in by and "vt320" in by):
        break
    time.sleep(300)
mins = usage_api.minute_usage(admin, KEY, datetime(2026, 11, 15, 9, 49, tzinfo=timezone.utc),
                              datetime(2026, 11, 15, 9, 52, tzinfo=timezone.utc))
out = {"checked_at": datetime.now(timezone.utc).isoformat(), "by_terminal": by,
       "only_DISABLE_TELEMETRY_vt52_counted": by.get("vt52", 0),
       "only_CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC_vt320_counted": by.get("vt320", 0),
       "billed_09_49_to_09_52": mins}
json.dump(out, open("work/results/telemetry_off_bisect.json", "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k.startswith("only")}), flush=True)
