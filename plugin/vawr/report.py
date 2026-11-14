"""Allocation report: tokens and estimated cost by category, built from the
chained log alone. The auditor recomputes the same numbers independently."""

import json
import os

from . import chainlog, paths
from .logdata import TOKEN_TYPES, api_requests


def _in_window(r, start, end):
    if not (start or end):
        return True
    from datetime import datetime
    t = r.get("time")
    if not isinstance(t, str) or not t:
        return False
    try:
        t = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return False
    from datetime import timezone
    t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    start = start and (start if start.tzinfo else start.replace(tzinfo=timezone.utc))
    end = end and (end if end.tzinfo else end.replace(tzinfo=timezone.utc))
    return (not start or t >= start) and (not end or t < end)


API_KEY_MODES = ("api_key", "sprint")
SUBSCRIPTION_MODES = ("account", "subscription")


def build(log_path=paths.LOG_PATH, claims_path=None, start=None, end=None, only_projects=None):
    """start/end (UTC datetimes) limit the report to requests in that window,
    e.g. one month of a grant, and `only_projects` to those project tags (one client's
    or grant's work); the chain is still verified over the whole log."""
    reqs = [r for r in api_requests(log_path) if _in_window(r, start, end)
            and (not only_projects or r.get("project") in only_projects)]
    billing = {"api_key": 0, "subscription": 0, "unknown": 0}
    for r in reqs:
        kind = ("api_key" if r.get("mode") in API_KEY_MODES else
                "subscription" if r.get("mode") in SUBSCRIPTION_MODES else "unknown")
        billing[kind] += sum(r["tokens"].values())
    runs = {}
    for r in reqs:
        key = r["run_id"] or "untagged"
        run = runs.setdefault(key, {"run_id": key, "category": r["category"], "mode": r["mode"],
                                    "project": r.get("project"),
                                    "requests": 0, "cost_usd": 0.0,
                                    "tokens": {t: 0 for t in TOKEN_TYPES}})
        run["requests"] += 1
        run["cost_usd"] += r["cost_usd"]
        for t in TOKEN_TYPES:
            run["tokens"][t] += r["tokens"][t]

    claims = {}
    if claims_path and os.path.exists(claims_path):
        with open(claims_path) as fh:
            claims = json.load(fh).get("runs", {})

    cats = {}
    for run in runs.values():
        c = cats.setdefault(run["category"], {"category": run["category"], "runs": 0, "requests": 0,
                                              "cost_usd": 0.0, "tokens": {t: 0 for t in TOKEN_TYPES},
                                              "claims": 0, "claims_held": 0,
                                              "outcomes": 0, "outcomes_passed": 0})
        c["runs"] += 1
        c["requests"] += run["requests"]
        c["cost_usd"] += run["cost_usd"]
        for t in TOKEN_TYPES:
            c["tokens"][t] += run["tokens"][t]
        rc = claims.get(run["run_id"])
        if rc:
            c["claims"] += rc.get("claims", 0)
            c["claims_held"] += rc.get("held", 0)
            if rc.get("outcome_pass") is not None:
                c["outcomes"] += 1
                c["outcomes_passed"] += 1 if rc["outcome_pass"] else 0

    grand = sum(sum(c["tokens"].values()) for c in cats.values()) or 1
    for c in cats.values():
        c["total_tokens"] = sum(c["tokens"].values())
        c["token_share"] = c["total_tokens"] / grand
        c["claims_held_rate"] = (c["claims_held"] / c["claims"]) if c["claims"] else None
        c["cost_usd"] = round(c["cost_usd"], 6)

    projects = {}
    for run in runs.values():
        if not run.get("project"):
            continue
        pr = projects.setdefault(run["project"], {"project": run["project"], "category": run["category"],
                                                  "runs": 0, "total_tokens": 0, "cost_usd": 0.0})
        pr["runs"] += 1
        pr["total_tokens"] += sum(run["tokens"].values())
        pr["cost_usd"] = round(pr["cost_usd"] + run["cost_usd"], 6)

    ok, _, count, head = chainlog.verify(log_path)
    return {
        "log": {"path": log_path, "entries": count, "head": head, "chain_ok": ok},
        "window": [start.isoformat() if start else None, end.isoformat() if end else None],
        "only_projects": sorted(only_projects) if only_projects else None,
        "billing": billing,
        "categories": sorted(cats.values(), key=lambda c: c["category"]),
        "projects": sorted(projects.values(), key=lambda p: -p["total_tokens"]),
        "runs": sorted(runs.values(), key=lambda r: r["run_id"]),
        "note": "Cost is Claude Code's client-side estimate, not a bill. Tokens are the primary measure.",
    }


def render(rep):
    lines = ["| Category | Runs | Requests | Total tokens | Share | Est. cost (USD) | Claims held up | Work passing its tests |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for c in rep["categories"]:
        held = ("%d of %d" % (c["claims_held"], c["claims"])) if c["claims"] else "n/a"
        outc = ("%d of %d" % (c.get("outcomes_passed", 0), c["outcomes"])) if c.get("outcomes") else "n/a"
        lines.append("| %s | %d | %d | %s | %.1f%% | %.4f | %s | %s |" % (
            c["category"], c["runs"], c["requests"], format(c["total_tokens"], ","),
            100 * c["token_share"], c["cost_usd"], held, outc))
    if rep.get("projects"):
        lines += ["", "| Project | Category | Sessions | Total tokens | Est. cost (USD) |", "| --- | --- | --- | --- | --- |"]
        for pr in rep["projects"]:
            lines.append("| %s | %s | %d | %s | %.4f |" % (pr["project"], pr["category"], pr["runs"],
                                                         format(pr["total_tokens"], ","), pr["cost_usd"]))
    lines.append("")
    lines.append("Log: %d entries, chain %s, head %s" % (
        rep["log"]["entries"], "intact" if rep["log"]["chain_ok"] else "BROKEN", (rep["log"]["head"] or "")[:16]))
    lines.append(rep["note"])
    return "\n".join(lines)
