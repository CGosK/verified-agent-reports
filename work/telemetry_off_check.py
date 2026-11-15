"""Does Anthropic's Claude Code Analytics count sessions run with Claude Code's own
telemetry off (DISABLE_TELEMETRY=1, CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1)?
Nov 15, 2026 08:44 UTC, main key: 2 control sessions with TERM=vt100 (defaults) and
2 with TERM=vt220 and both variables set; none sent OpenTelemetry to vawr. Polls until
the controls appear, then records both rows and the billed Haiku tokens."""
import json, sys, time
from datetime import datetime, timezone
sys.path.insert(0, ".")
from vawr import billcheck, usage_api
admin, _ = billcheck.admin_and_key()
KEY = "apikey_014nm6SadTU7zy9DoURcd48j"
name = next(k["name"] for k in usage_api.api_keys(admin) if k["id"] == KEY)
for attempt in range(40):
    recs = [r for r in usage_api.claude_code_day(admin, "2026-11-15")
            if (r.get("actor") or {}).get("api_key_name") == name]
    by_term = {}
    for r in recs:
        t = r.get("terminal_type")
        b = by_term.setdefault(t, {"sessions": 0, "tokens": {}})
        b["sessions"] += (r.get("core_metrics") or {}).get("num_sessions") or 0
        for m in r.get("model_breakdown") or []:
            b["tokens"][m["model"]] = b["tokens"].get(m["model"], 0) + sum(m["tokens"].values())
    print(datetime.now(timezone.utc).strftime("%H:%M"), {t: v["sessions"] for t, v in by_term.items()}, flush=True)
    if "vt100" in by_term:
        time.sleep(300)
        recs = [r for r in usage_api.claude_code_day(admin, "2026-11-15")
                if (r.get("actor") or {}).get("api_key_name") == name]
        by_term = {}
        for r in recs:
            t = r.get("terminal_type")
            b = by_term.setdefault(t, {"sessions": 0, "tokens": {}})
            b["sessions"] += (r.get("core_metrics") or {}).get("num_sessions") or 0
            for m in r.get("model_breakdown") or []:
                b["tokens"][m["model"]] = b["tokens"].get(m["model"], 0) + sum(m["tokens"].values())
        mins = usage_api.minute_usage(admin, KEY, datetime(2026, 11, 15, 8, 43, tzinfo=timezone.utc),
                                      datetime(2026, 11, 15, 8, 46, tzinfo=timezone.utc))
        out = {"checked_at": datetime.now(timezone.utc).isoformat(), "key_id": KEY, "by_terminal": by_term,
               "billed_08_43_to_08_46": mins,
               "control_vt100_counted": by_term.get("vt100", {}).get("sessions"),
               "telemetry_off_vt220_counted": by_term.get("vt220", {}).get("sessions", 0)}
        json.dump(out, open("work/results/telemetry_off_test.json", "w"), indent=1)
        print(json.dumps({k: out[k] for k in ("control_vt100_counted", "telemetry_off_vt220_counted")}), flush=True)
        break
    time.sleep(300)
