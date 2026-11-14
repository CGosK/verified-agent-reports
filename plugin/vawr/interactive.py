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
from datetime import datetime, timezone

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


def _seed_config(worktree):
    """Mark onboarding done and the worktree trusted, as a returning user would have it."""
    os.makedirs(CFG, exist_ok=True)
    path = os.path.join(CFG, ".claude.json")
    cfg = {}
    if os.path.exists(path):
        with open(path) as fh:
            cfg = json.load(fh)
    cfg.update(hasCompletedOnboarding=True, lastOnboardingVersion="2.1.322", theme="dark")
    cfg.setdefault("projects", {})[worktree] = dict(cfg.get("projects", {}).get(worktree, {}),
                                                    hasTrustDialogAccepted=True)
    with open(path, "w") as fh:
        json.dump(cfg, fh, indent=1)


def run_session(task_id, category, model, turns):
    tasks = load_tasks()
    setup_task_repo()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sid = "%s-%s-int" % (stamp, task_id.replace("_", ""))
    wt = os.path.join(paths.RUNS_DIR, sid)
    os.makedirs(paths.RUNS_DIR, exist_ok=True)
    git("worktree", "add", "-q", "--detach", wt, "HEAD", cwd=paths.TASK_REPO)
    _seed_config(wt)
    keys = load_env()
    # a person at a terminal: none of the parent session's variables (with them,
    # Claude Code also turns off transcript saving as a child session)
    env = parent_free({k: v for k, v in os.environ.items() if k not in TELEMETRY_KEYS})
    env.update(otel_env(PORT))
    env.update(ANTHROPIC_API_KEY=keys["ANTHROPIC_API_KEY"], CLAUDE_CONFIG_DIR=CFG,
               OTEL_RESOURCE_ATTRIBUTES="category=%s,project=interactive-%s" % (category, task_id),
               TERM="xterm-256color")
    args = [DRIVER, wt, model]
    for wait, prompt in turns:
        args += [str(wait), (prompt or build_prompt(tasks[task_id], None)).replace("\n", " ")]
    os.makedirs(HOME, exist_ok=True)
    start = datetime.now(timezone.utc).isoformat()
    with open(os.path.join(HOME, sid + ".screen.log"), "w") as out:
        proc = subprocess.run(args, env=env, stdout=out, stderr=subprocess.STDOUT, timeout=1800)
    end = datetime.now(timezone.utc).isoformat()
    test = subprocess.run(["python3", "-m", "unittest", tasks[task_id]["test"]], cwd=wt,
                          capture_output=True, text=True, timeout=300)
    rec = {"session": sid, "task": task_id, "category": category, "model": model,
           "turns": [p or "(task prompt)" for _, p in turns], "start": start, "end": end,
           "driver_exit": proc.returncode, "test_exit": test.returncode, "worktree": wt}
    with open(os.path.join(HOME, "sessions.jsonl"), "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec
