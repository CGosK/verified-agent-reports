"""Which of the three headless sessions (11:22-11:24 UTC Nov 15, main key) did Anthropic count?
The count alone can't say; the counted row's tokens can. Each session's single request has its own
cache-creation size in vawr's log, so compare Anthropic's non-interactive row with each.
Adds the answer to work/results/telemetry_off_headless.json."""
import json, sys
sys.path.insert(0, ".")
from vawr import billcheck, usage_api

RUNS = {"disable_telemetry": "work/telemetry_off_otel/log.jsonl",
        "nonessential": "work/telemetry_off_otel_nonessential/log.jsonl",
        "control": "work/telemetry_off_otel_control/log.jsonl"}
FIELDS = {"input": "input_tokens", "output": "output_tokens",
          "cache_read": "cache_read_tokens", "cache_creation": "cache_creation_tokens"}


def logged_tokens(path):
    tot = dict.fromkeys(FIELDS, 0)
    for line in open(path):
        a = (json.loads(line).get("event") or {}).get("attributes") or {}
        if "cache_creation_tokens" in a:
            for k, f in FIELDS.items():
                tot[k] += int(a.get(f) or 0)
    return tot


admin, _ = billcheck.admin_and_key()
KEY = "apikey_014nm6SadTU7zy9DoURcd48j"
name = next(k["name"] for k in usage_api.api_keys(admin) if k["id"] == KEY)
row = next(r for r in usage_api.claude_code_day(admin, "2026-11-15")
           if (r.get("actor") or {}).get("api_key_name") == name and r.get("terminal_type") == "non-interactive")
counted = {}
for m in row.get("model_breakdown") or []:
    for k in FIELDS:
        counted[k] = counted.get(k, 0) + int((m.get("tokens") or {}).get(k) or 0)
logged = {run: logged_tokens(p) for run, p in RUNS.items()}
match = [run for run, t in logged.items() if t == counted]
p = "work/results/telemetry_off_headless.json"
out = json.load(open(p))
out.update({"counted_row_tokens": counted, "logged_tokens_by_run": logged, "counted_row_matches": match})
json.dump(out, open(p, "w"), indent=1)
print(json.dumps({"counted_row_tokens": counted, "matches": match}))
