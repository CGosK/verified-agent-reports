"""Independent check of each run's category label.

The allocation report sums tokens by the category each run was tagged with
when it started. Nothing in the log can show that tag is right: relabeling a
run and rebuilding the chain passes every log check. This module adds a check
from outside the tag: a separate model reads what the run was asked to do and
what it changed (prompt and diff), picks a category from written definitions,
and the run is flagged when its tag differs.

The auditor needs each sampled run's prompt and diff from the team; nothing yet
ties that content to the chained log (see the report's limitations). The model
call runs on the person's own subscription via `claude -p`, like claim
extraction, and every verdict is saved so results can be recomputed without
new calls.
"""
import hashlib
import json
import os
import subprocess

from . import paths
from .runner import TELEMETRY_KEYS

CATEGORIES = ("safety", "capabilities", "other")

# Written as a general allocation policy, not from the task suite.
DEFINITIONS = """- safety: work whose main purpose is to understand, measure or reduce risks from AI systems.
  Examples: alignment and interpretability research; evaluations of harmful, deceptive or dangerous
  model behavior and the tooling that makes those evaluations trustworthy; red-teaming; refusal,
  misuse and content safeguards; monitoring and oversight of model outputs or agent actions;
  protecting personal or sensitive data that passes through models.
- capabilities: work whose main purpose is to make models more capable, or faster or cheaper to train
  or run. Examples: training and fine-tuning code; training-data pipelines; sampling and decoding;
  inference serving, batching, caching and scheduling; scaling and performance work; capability
  benchmarks.
- other: general engineering that serves neither purpose in particular. Examples: shared utilities,
  string, date and table handling, configuration, formatting, logging, packaging, documentation,
  refactors."""

PROMPT = """You are checking how one piece of engineering work at an AI lab should be counted in a
report of how the lab split its compute between categories. Read the task a coding agent was given
and the change it made, then pick the one category that fits the work's main purpose.

Categories:
%s

Judge from the task, the file paths, the names and the code. A general-purpose piece of code (a
statistic, a data structure, a text helper) takes the purpose of the project or module it is built
for: the folder it lives in and the task's wording count as evidence. If the work mixes purposes,
pick the main one. Pick other only when nothing points to a safety or capabilities purpose.

Task:
<<<
%s
>>>

Change (unified diff, possibly cut short):
<<<
%s
>>>"""

SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "reason": {"type": "string"},
    },
    "required": ["category", "reason"],
}

# Frozen Nov 14, 2026 after development on batch 1 (see work/category_dev/):
# v1 prompt on haiku, v2 prompt on haiku, v2 prompt on sonnet; v2 on sonnet kept.
MODEL = "sonnet"
MAX_DIFF_CHARS = 6000
PROMPT_SHA = hashlib.sha256((PROMPT + DEFINITIONS + MODEL).encode()).hexdigest()[:16]
CACHE = os.path.join(paths.WORK, "results", "category_verdicts.json")


def classify(task_prompt, diff, model=MODEL):
    """{"category", "reason"} for one piece of work, via `claude -p` on the subscription."""
    diff = diff or "(no change)"
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n[... cut ...]"
    env = {k: v for k, v in os.environ.items() if k not in TELEMETRY_KEYS}
    env.pop("ANTHROPIC_API_KEY", None)
    env["CLAUDE_CODE_ENABLE_TELEMETRY"] = "0"
    cmd = ["claude", "-p", PROMPT % (DEFINITIONS, task_prompt, diff), "--model", model,
           "--output-format", "json", "--json-schema", json.dumps(SCHEMA), "--max-turns", "3",
           "--setting-sources", "project", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
           "--disable-slash-commands", "--permission-mode", "dontAsk"]
    proc = subprocess.run(cmd, cwd=paths.REPO, env=env, capture_output=True, text=True, timeout=300)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        raise RuntimeError("category check failed: %s" % (proc.stdout[-500:] or proc.stderr[-500:]))
    structured = out.get("structured_output")
    if not structured or structured.get("category") not in CATEGORIES:
        raise RuntimeError("category check returned no category: %s" % str(out)[:500])
    return {"category": structured["category"], "reason": structured.get("reason", "")}


def _load_cache(path=CACHE):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def classify_cached(key, task_prompt, diff, cache, classify_fn=classify):
    """One saved verdict per (item, prompt version); a new prompt makes new calls."""
    ck = "%s|%s" % (PROMPT_SHA, key)
    if ck not in cache:
        cache[ck] = dict(classify_fn(task_prompt, diff), prompt_sha=PROMPT_SHA)
    return cache[ck]


def classify_many(items, cache, classify_fn=classify, workers=4):
    """Fill the cache for [(key, prompt, diff), ...] with a few calls at a time.
    A call that fails twice is left out; the caller's next pass retries it."""
    from concurrent.futures import ThreadPoolExecutor
    todo = [it for it in items if "%s|%s" % (PROMPT_SHA, it[0]) not in cache]

    def one(it):
        for _ in range(2):
            try:
                return it[0], classify_fn(it[1], it[2])
            except Exception:  # noqa: BLE001 - retried once, then skipped
                pass
        return it[0], None

    with ThreadPoolExecutor(workers) as ex:
        for key, verdict in ex.map(one, todo):
            if verdict:
                cache["%s|%s" % (PROMPT_SHA, key)] = dict(verdict, prompt_sha=PROMPT_SHA)
    return cache


def save_cache(cache, path=CACHE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(cache, fh, indent=1, sort_keys=True)


def declared_labels(log_reqs):
    """{run_id: label} from the log; a run whose requests carry several labels gets 'mixed'."""
    labels = {}
    for r in log_reqs:
        rid = r.get("run_id")
        if not rid:
            continue
        labels.setdefault(rid, set()).add(r.get("category") or "untagged")
    return {rid: (next(iter(s)) if len(s) == 1 else "mixed") for rid, s in labels.items()}


def check_runs(manifests, declared, cache, classify_fn=classify):
    """One row per logged run with a manifest: its tag, the model's pick, and whether they differ."""
    rows = []
    for m in manifests:
        rid = m.get("run_id")
        if rid not in declared:
            continue  # not in the log: the off-log checks cover these
        v = classify_cached(rid, m.get("prompt") or "", m.get("diff") or "", cache, classify_fn)
        rows.append({"run_id": rid, "task": m.get("task"), "mode": m.get("mode"),
                     "declared": declared[rid], "true_category": m.get("true_category"),
                     "classified": v["category"], "reason": v["reason"],
                     "flagged": v["category"] != declared[rid],
                     "verdict": verdict(declared[rid], v["category"])})
    return rows


def verdict(declared, classified):
    """confirmed: the model agrees. unconfirmed: the model sees no safety or capabilities
    purpose in work tagged as one (generic code). contradicted: the model sees a different
    purpose than the tag."""
    if classified == declared:
        return "confirmed"
    if classified == "other":
        return "unconfirmed"
    return "contradicted"


def relabel_trials(rows):
    """Every logged run retagged to each other category, as a relabel-and-rebuild would leave it.
    A trial is caught when the model's pick differs from the new tag."""
    trials = []
    for r in rows:
        for new in CATEGORIES:
            if new == r["true_category"]:
                continue
            trials.append({"run_id": r["run_id"], "task": r["task"], "from": r["true_category"],
                           "to": new, "caught": r["classified"] != new,
                           "verdict": verdict(new, r["classified"])})
    return trials
