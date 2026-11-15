"""Does a session run with Claude Code's telemetry off still make the unrecorded
background request? Nov 15, 2026, main key: three headless Haiku sessions, each with
CLAUDE_CODE_ENTRYPOINT=claude-desktop (the trigger for that request; see
work/results/summary.md), each logged by vawr to its own scratch receiver, three
minutes apart: a control, one with DISABLE_TELEMETRY=1, one with
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1. Then, once Anthropic's per-minute usage
has landed, billed minus logged tokens in each session's minutes is its unrecorded
background usage. Matters for the sessions check: if a telemetry-off session makes the
request, an honest team's uncounted sessions need background allowance that
Anthropic's session count doesn't justify. Writes work/results/telemetry_off_desktop_env.json."""
import json, os, subprocess, sys, tempfile, time, urllib.request
from datetime import datetime, timedelta, timezone
sys.path.insert(0, ".")
from vawr.configure import otel_env
from vawr.runner import TELEMETRY_KEYS, load_env, parent_free
from vawr import billcheck, logdata, usage_api

D = "work/telemetry_off_desktop_env"
os.makedirs(D, exist_ok=True)
KEY = "apikey_014nm6SadTU7zy9DoURcd48j"
RUNS = [("control", {}), ("disable_telemetry", {"DISABLE_TELEMETRY": "1"}),
        ("nonessential", {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"})]


def one(name, extra, port):
    d = os.path.join(D, name)
    os.makedirs(d, exist_ok=True)
    log = os.path.join(d, "log.jsonl")
    rx = subprocess.Popen([sys.executable, "-m", "vawr", "serve", "--log", log, "--port", str(port)],
                          stdout=open(os.path.join(d, "receiver.out"), "w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/health" % port, timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        env = parent_free({k: v for k, v in os.environ.items() if k not in TELEMETRY_KEYS})
        env.pop("DISABLE_TELEMETRY", None)
        env.pop("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", None)
        env.update(otel_env(port))
        env.update(ANTHROPIC_API_KEY=load_env()["ANTHROPIC_API_KEY"],
                   CLAUDE_CONFIG_DIR=tempfile.mkdtemp(dir=d, prefix="cfg-"),
                   OTEL_RESOURCE_ATTRIBUTES="category=other,project=telemetry-off-desktop-%s" % name,
                   CLAUDE_CODE_ENTRYPOINT="claude-desktop", **extra)
        started = datetime.now(timezone.utc)
        r = subprocess.run(["claude", "-p", "Reply with the single word OK.", "--model", "haiku"],
                           cwd=tempfile.mkdtemp(dir=d, prefix="cwd-"), env=env, capture_output=True, text=True,
                           timeout=180)
        ended = datetime.now(timezone.utc)
        time.sleep(8)
    finally:
        rx.terminate()
        rx.wait()
    logged = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    for req in logdata.api_requests(log):
        for t in logged:
            logged[t] += req["tokens"][t]
    return {"exit": r.returncode, "reply": r.stdout.strip()[:40], "started": started.isoformat(),
            "ended": ended.isoformat(), "log_sessions": len(logdata.sessions(log)),
            "log_api_requests": len(logdata.api_requests(log)), "logged_tokens": logged}


out = {"runs": {}}
for i, (name, extra) in enumerate(RUNS):
    if i:  # three minutes apart, so each session's minutes are its own in the bill
        time.sleep(180)
    out["runs"][name] = one(name, extra, 4341 + i)
    print(name, json.dumps(out["runs"][name])[:300], flush=True)
json.dump(out, open("work/results/telemetry_off_desktop_env.json", "w"), indent=1)

# Anthropic's per-minute usage lands within minutes; poll for up to 40 minutes
admin, _ = billcheck.admin_and_key()
t0 = min(datetime.fromisoformat(r["started"]) for r in out["runs"].values()).replace(second=0, microsecond=0)
t1 = max(datetime.fromisoformat(r["ended"]) for r in out["runs"].values()).replace(second=0, microsecond=0) \
    + timedelta(minutes=2)
deadline = time.time() + 40 * 60
while True:
    time.sleep(300)
    mins = usage_api.minute_usage(admin, KEY, t0, t1)
    got = {name: {} for name in out["runs"]}
    for name, r in out["runs"].items():
        a = datetime.fromisoformat(r["started"]).replace(second=0, microsecond=0) - timedelta(minutes=1)
        b = datetime.fromisoformat(r["ended"]).replace(second=0, microsecond=0) + timedelta(minutes=1)
        for k, by_model in mins.items():
            if a <= datetime.fromisoformat(k.replace("Z", "+00:00")) <= b:
                for model, tok in by_model.items():
                    g = got[name].setdefault(model, {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0})
                    for t in g:
                        g[t] += tok.get(t, 0)
    billed_total = {n: sum(sum(v.values()) for v in g.values()) for n, g in got.items()}
    logged_total = {n: sum(r["logged_tokens"].values()) for n, r in out["runs"].items()}
    print(datetime.now(timezone.utc).strftime("%H:%M"), billed_total, logged_total, flush=True)
    if all(billed_total[n] >= logged_total[n] > 0 for n in got) or time.time() > deadline:
        break
for n in out["runs"]:
    out["runs"][n]["billed_in_minutes"] = got[n]
    out["runs"][n]["billed_minus_logged"] = billed_total[n] - logged_total[n]
out["checked_at"] = datetime.now(timezone.utc).isoformat()
json.dump(out, open("work/results/telemetry_off_desktop_env.json", "w"), indent=1)
print(json.dumps({n: r["billed_minus_logged"] for n, r in out["runs"].items()}), flush=True)
