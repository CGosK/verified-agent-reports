"""Does vawr's own log still record a session run with DISABLE_TELEMETRY=1? Nov 15, 2026,
main key, one headless Haiku session, OpenTelemetry to a scratch receiver on port 4331
(work/telemetry_off_otel/log.jsonl), scratch config dir. Anthropic doesn't count such a
session (work/results/telemetry_off_bisect.json); if the log does, an honest user with the
setting would show more sessions than Anthropic counted."""
import json, os, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, ".")
from vawr.configure import otel_env
from vawr.runner import TELEMETRY_KEYS, load_env, parent_free
from vawr import logdata
D = "work/telemetry_off_otel"
LOG = os.path.join(D, "log.jsonl")
rx = subprocess.Popen([sys.executable, "-m", "vawr", "serve", "--log", LOG, "--port", "4331"],
                      stdout=open(os.path.join(D, "receiver.out"), "w"), stderr=subprocess.STDOUT)
try:
    for _ in range(50):
        try:
            urllib.request.urlopen("http://127.0.0.1:4331/health", timeout=1); break
        except Exception:
            time.sleep(0.2)
    cfg = tempfile.mkdtemp(dir=D, prefix="cfg-")
    env = parent_free({k: v for k, v in os.environ.items() if k not in TELEMETRY_KEYS})
    env.pop("DISABLE_TELEMETRY", None); env.pop("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", None)
    env.update(otel_env(4331))
    env.update(ANTHROPIC_API_KEY=load_env()["ANTHROPIC_API_KEY"], CLAUDE_CONFIG_DIR=cfg,
               OTEL_RESOURCE_ATTRIBUTES="category=other,project=telemetry-off-otel",
               DISABLE_TELEMETRY="1")
    work = tempfile.mkdtemp(dir=D, prefix="cwd-")
    started = time.time()
    r = subprocess.run(["claude", "-p", "Reply with the single word OK.", "--model", "haiku"],
                       cwd=work, env=env, capture_output=True, text=True, timeout=180)
    time.sleep(8)
finally:
    rx.terminate(); rx.wait()
sess = logdata.sessions(LOG)
out = {"exit": r.returncode, "reply": r.stdout.strip()[:40], "log_entries": sum(1 for _ in open(LOG)) if os.path.exists(LOG) else 0,
       "log_sessions": sess,
       "api_requests": sum(1 for l in open(LOG) if "api_request" in l) if os.path.exists(LOG) else 0,
       "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))}
json.dump(out, open("work/results/telemetry_off_otel_disable_telemetry.json", "w"), indent=1, default=str)
print(json.dumps(out, default=str)[:600])
