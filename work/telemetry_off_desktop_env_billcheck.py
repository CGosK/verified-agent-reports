"""The bill check (auditor.check_provider, as `vawr check` runs it) on each session of
work/telemetry_off_desktop_env.py: its own log against Anthropic's per-minute usage for
its minute (saved in the result file). Adds "bill_check" to each run there."""
import json, sys
from datetime import datetime, timedelta
sys.path.insert(0, ".")
from vawr import auditor, logdata

P = "work/results/telemetry_off_desktop_env.json"
d = json.load(open(P))
for name, r in d["runs"].items():
    reqs = [dict(q, mode="api_key") for q in logdata.api_requests("work/telemetry_off_desktop_env/%s/log.jsonl" % name)]
    t0 = datetime.fromisoformat(r["started"]).replace(second=0, microsecond=0)
    res = auditor.check_provider(reqs, t0 - timedelta(minutes=2), t0 + timedelta(minutes=3), key_mode="api_key",
                                 provider_minutes={t0: r["billed_in_minutes"]})
    r["bill_check"] = {"ok": res["ok"], "background": res["background_tokens"],
                       "unexplained": [g["tokens"] for g in res["gaps"]]}
    print(name, r["bill_check"])
json.dump(d, open(P, "w"), indent=1)
