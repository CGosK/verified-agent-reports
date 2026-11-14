"""Real interactive Claude Code sessions on the API key, for checking that the
bill check and the provider check raise no false alarms under normal use.

Unlike the batch runs, nothing is switched off: the terminal-title request and
every other background call Claude Code makes for a person at a terminal stay
on. Each session runs in a fresh worktree with its own Claude config folder,
so the person's own settings, plugins and history are untouched, and logs to
its own receiver and log file so the batch results are unaffected.
"""
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

from . import paths
from .configure import otel_env
from .runner import TELEMETRY_KEYS, build_prompt, git, load_env, load_tasks, parent_free, setup_task_repo

HOME = os.path.join(paths.WORK, "interactive")
CFG = os.path.join(HOME, "claude-config")
LOG = os.path.join(HOME, "log", "events.jsonl")
DRIVER = os.path.join(paths.REPO, "tasks", "interactive", "drive.exp")
PORT = 4319

# (task, category, model, [(wait seconds, prompt), ...]); the first prompt is the task itself
SESSIONS = [
    ("o3_table", "other", "sonnet", [(100, None),
                                    (80, "Add one more test for an edge case you think is missing, then run the tests again.")]),
    ("s5_monitor", "safety", "sonnet", [(100, None),
                                       (120, "Use a subagent to review your change for bugs, then tell me what it found.")]),
    ("c2_schedule", "capabilities", "sonnet", [(100, None), (60, "/compact"),
                                              (80, "Summarize in two sentences what you changed and why.")]),
    ("o1_slugify", "other", "haiku", [(90, None),
                                     (60, "Is there anything risky about this change? One paragraph.")]),
]


def _seed_config(worktree, cfg=None):
    """Mark onboarding done and the worktree trusted, as a returning user would have it."""
    cfg = cfg or CFG
    os.makedirs(cfg, exist_ok=True)
    path = os.path.join(cfg, ".claude.json")
    cfg = {}
    if os.path.exists(path):
        with open(path) as fh:
            cfg = json.load(fh)
    cfg.update(hasCompletedOnboarding=True, lastOnboardingVersion="2.1.322", theme="dark")
    cfg.setdefault("projects", {})[worktree] = dict(cfg.get("projects", {}).get(worktree, {}),
                                                    hasTrustDialogAccepted=True)
    with open(path, "w") as fh:
        json.dump(cfg, fh, indent=1)


def _env(category, project, port, cfg):
    keys = load_env()
    # a person at a terminal: none of the parent session's variables (with them,
    # Claude Code also turns off transcript saving as a child session)
    env = parent_free({k: v for k, v in os.environ.items() if k not in TELEMETRY_KEYS})
    env.update(otel_env(port))
    env.update(ANTHROPIC_API_KEY=keys["ANTHROPIC_API_KEY"], CLAUDE_CONFIG_DIR=cfg,
               OTEL_RESOURCE_ATTRIBUTES="category=%s,project=%s" % (category, project),
               TERM="xterm-256color")
    return env


def _worktree(sid, cfg):
    setup_task_repo()
    wt = os.path.join(paths.RUNS_DIR, sid)
    os.makedirs(paths.RUNS_DIR, exist_ok=True)
    git("worktree", "add", "-q", "--detach", wt, "HEAD", cwd=paths.TASK_REPO)
    _seed_config(wt, cfg)
    return wt


def run_session(task_id, category, model, turns, home=None, cfg=None, port=None, project=None):
    home, cfg, port = home or HOME, cfg or CFG, port or PORT
    tasks = load_tasks()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sid = "%s-%s-int" % (stamp, task_id.replace("_", ""))
    wt = _worktree(sid, cfg)
    env = _env(category, project or "interactive-%s" % task_id, port, cfg)
    HOME_ = home
    args = [DRIVER, wt, model]
    for wait, prompt in turns:
        args += [str(wait), (prompt or build_prompt(tasks[task_id], None)).replace("\n", " ")]
    os.makedirs(HOME_, exist_ok=True)
    start = datetime.now(timezone.utc).isoformat()
    with open(os.path.join(HOME_, sid + ".screen.log"), "w") as out:
        proc = subprocess.run(args, env=env, stdout=out, stderr=subprocess.STDOUT, timeout=1800)
    end = datetime.now(timezone.utc).isoformat()
    test = subprocess.run(["python3", "-m", "unittest", tasks[task_id]["test"]], cwd=wt,
                          capture_output=True, text=True, timeout=300)
    rec = {"session": sid, "task": task_id, "category": category, "model": model,
           "turns": [p or "(task prompt)" for _, p in turns], "start": start, "end": end,
           "driver_exit": proc.returncode, "test_exit": test.returncode, "worktree": wt}
    with open(os.path.join(HOME_, "sessions.jsonl"), "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def run_headless(task_id, category, model, home, cfg, port, project):
    """One `claude -p` run on the API key, in the same clean environment."""
    from .runner import build_cmd
    tasks = load_tasks()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sid = "%s-%s-hl" % (stamp, task_id.replace("_", ""))
    wt = _worktree(sid, cfg)
    env = _env(category, project, port, cfg)
    start = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(build_cmd("sprint", build_prompt(tasks[task_id], None), model, 1.0), cwd=wt, env=env,
                          capture_output=True, text=True, timeout=1200)
    end = datetime.now(timezone.utc).isoformat()
    rec = {"session": sid, "task": task_id, "category": category, "model": model, "headless": True,
           "start": start, "end": end, "exit": proc.returncode, "worktree": wt}
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "sessions.jsonl"), "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


DEMO = os.path.join(paths.WORK, "demo-20261115")


def demo_day(at=None, report_at=None, port=4320):
    """A whole UTC day on the API key with every session logged: three interactive
    sessions and two headless runs, all on project "grant-demo", then (after
    Anthropic's records catch up) a bundle, the payer's receive, and a team check.
    Nothing else may use the key that day, or the sessions check rightly fails."""
    import sys
    import time
    def wait_until(t):
        while t and datetime.now(timezone.utc) < t:
            time.sleep(min(300, max(1, (t - datetime.now(timezone.utc)).total_seconds())))
    home, cfg = os.path.join(DEMO, "sessions"), os.path.join(DEMO, "claude-config")
    log = os.path.join(DEMO, "log", "events.jsonl")
    wait_until(at)
    os.makedirs(os.path.dirname(log), exist_ok=True)
    rlog = open(os.path.join(DEMO, "receiver.out"), "a")
    recv = subprocess.Popen([sys.executable, "-u", "-m", "vawr", "serve", "--log", log, "--port", str(port)],
                            cwd=paths.REPO, stdout=rlog, stderr=rlog)
    time.sleep(3)
    try:
        for task, cat, model, turns in SESSIONS[:3]:
            print(json.dumps(run_session(task, cat, model, turns, home=home, cfg=cfg, port=port,
                                         project="grant-demo")), flush=True)
        for task, cat, model in (("o1_slugify", "other", "haiku"), ("s1_refusals", "safety", "sonnet")):
            print(json.dumps(run_headless(task, cat, model, home, cfg, port, "grant-demo")), flush=True)
        time.sleep(60)  # last metric exports
    finally:
        recv.terminate()
    wait_until(report_at)
    env = dict(os.environ, VAWR_HOME=os.path.join(DEMO, "home"))
    day = (at or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    out = os.path.join(DEMO, "grant-demo.zip")
    steps = [["bundle", "--log", log, "--since", day + "T00:00", "--until", (datetime.now(timezone.utc) -
              timedelta(minutes=40)).strftime("%Y-%m-%dT%H:%M"), "--project", "grant-demo", "--title",
              "Grant demo, " + day, "--projects", os.path.join(cfg, "projects"), "--out", out],
             ["receive", out, "--html", os.path.join(DEMO, "received.html"), "--json",
              os.path.join(DEMO, "received.json")],
             ["team", out, "--no-record", "--json", os.path.join(DEMO, "team.json")]]
    for st in steps:
        r = subprocess.run([sys.executable, "-m", "vawr"] + st, cwd=paths.REPO, env=env, capture_output=True,
                           text=True)
        with open(os.path.join(DEMO, st[0] + ".txt"), "w") as fh:
            fh.write(r.stdout + r.stderr)
        print(st[0], "exit", r.returncode, flush=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", default=None)
    ap.add_argument("--report-at", default=None)
    a = ap.parse_args()
    p = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None  # noqa: E731
    demo_day(p(a.at), p(a.report_at))
