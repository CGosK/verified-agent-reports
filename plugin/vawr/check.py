"""`vawr check`: the audit a team runs on its own log before sharing a report,
and (`vawr receive`) the audit whoever pays for the API key runs on it.

1. Chain: every entry's hash recomputes, so nothing was edited or reordered.
2. Coverage: every request in this machine's Claude Code session files during
   the window is in the log. A session that ran without sending telemetry (set
   up before `vawr setup`, or with telemetry turned off) shows up here.
3. Bill (needs an Admin key): what Anthropic billed the API key, minute by
   minute, is accounted for by logged requests plus Claude Code's own
   background requests.
4. Sessions (needs an Admin key): Anthropic's daily count of Claude Code
   sessions and tokens on the key equals the log's (see daily.py).
"""
from collections import defaultdict
from datetime import timedelta

from . import auditor, billcheck, chainlog, daily, usage_api
from .logdata import TOKEN_TYPES, api_requests
from .sessions import parse_ts

LEVELS = {
    "provider": "Checked against Anthropic's records",
    "tamper-evident": "Tamper-evident only: not checked against Anthropic's records",
    "failed": "A check failed",
}


def level(res):
    """How far a check result vouches for the log: "provider" (chain intact and the
    bill check passed against Anthropic's records), "tamper-evident" (chain intact,
    no bill check: a Claude subscription, or no Admin key) or "failed"."""
    sess = res.get("sessions")
    if (res["chain"]["ok"] is False or res["coverage"]["ok"] is False
            or (res.get("bill") and res["bill"]["gaps"]) or (sess and sess.get("ok") is False)):
        return "failed"
    return "provider" if res.get("bill") is not None else "tamper-evident"


def provider_checks(reqs, start, end, admin_key=None, key_id=None, api_key=None, provider_minutes=None,
                    shift=2, source="auto", log_paths=None, only_projects=None, sessions=True):
    """(bill, sessions) for requests billed to the key; either is None if it can't run."""
    bill = sess = None
    if provider_minutes is None and admin_key and not key_id and api_key:
        key_id = usage_api.find_key_id(admin_key, api_key)
    if provider_minutes is None and admin_key and key_id:
        raw, source, _ = usage_api.minute_usage_any(admin_key, key_id, start, end, source)
        provider_minutes = {parse_ts(k): v for k, v in raw.items()}
    if provider_minutes is not None:
        # requests billed to an API key: tagged runs ("sprint") or auth=api_key
        key_reqs = [dict(r, mode="api_key") for r in reqs if r.get("mode") in ("api_key", "sprint")]
        bill = auditor.check_provider(key_reqs, start, end, shift=shift, key_mode="api_key",
                                      provider_minutes=provider_minutes)
        bill["key_id"] = key_id
        bill["source"] = source
    if sessions and admin_key and key_id and log_paths:
        try:
            sess = daily.check(admin_key, key_id, start, end, log_paths, only_projects=only_projects)
        except Exception as exc:  # the bill check stands on its own; say why this one didn't run
            sess = {"ok": None, "error": "%s: %s" % (type(exc).__name__, exc)}
    return bill, sess


def run(start, end, log_path, projects, admin_key=None, key_id=None, api_key=None,
        provider_minutes=None, shift=2, match=None, coverage=True, source="auto", only_projects=None,
        sessions=True):
    """`only_projects`: count only requests from these project tags (a report for one
    client or grant); the chain is still checked over the whole log."""
    ok_chain, problems, entries, head = chainlog.verify(log_path)
    in_window = [r for r in api_requests(log_path) if r.get("time") and start <= parse_ts(r["time"]) < end]
    reqs = [r for r in in_window if not only_projects or r.get("project") in only_projects]
    # coverage asks whether every local session reached the log, whatever its project
    logged_ids = {r["request_id"]: r for r in in_window if r.get("request_id")}

    local = billcheck.local_requests(start, end, projects) if coverage else {}
    if match:  # only project folders whose name contains one of these
        local = {k: r for k, r in local.items() if any(m in r["project"] for m in match)}
    missing = defaultdict(lambda: {"requests": 0, "tokens": 0, "auth": None, "first": None})
    mismatched = 0
    for r in local.values():
        lr = logged_ids.get(r["request_id"])
        if lr is None:
            m = missing[(r["project"], r["session_id"])]
            m["requests"] += 1
            m["tokens"] += sum(r["tokens"].values())
            m["auth"] = r["auth"]
            m["first"] = min(filter(None, [m["first"], r["time"]]))
        elif any(lr["tokens"][t] != r["tokens"][t] for t in TOKEN_TYPES):
            mismatched += 1

    bill, sess = provider_checks(reqs, start, end, admin_key, key_id, api_key, provider_minutes, shift, source,
                                 log_paths=[log_path], only_projects=only_projects, sessions=sessions)
    res = {
        "window": [start.isoformat(), end.isoformat()],
        "only_projects": sorted(only_projects) if only_projects else None,
        "chain": {"ok": ok_chain, "entries": entries, "head": head, "problems": problems[:5]},
        "coverage": {"ok": (not missing and not mismatched) if coverage else None, "local_requests": len(local),
                     "logged_requests_in_window": len(reqs), "token_mismatches": mismatched,
                     "unlogged_sessions": [dict(v, project=k[0], session=k[1]) for k, v in
                                           sorted(missing.items(), key=lambda kv: kv[1]["first"] or "")]},
        "bill": bill,
        "sessions": sess,
    }
    res["level"] = level(res)
    return res


def render(res):
    mark = {True: "PASS", False: "FAIL", None: "SKIP"}
    c, b = res["coverage"], res["bill"]
    lines = ["vawr check, %s to %s UTC" % (res["window"][0][:16].replace("T", " "), res["window"][1][11:16]), ""]
    lines.append("%s  chain        %d entries, head %s" % (
        mark[res["chain"]["ok"]], res["chain"]["entries"], (res["chain"]["head"] or "")[:16]))
    if c["ok"] is None:
        lines.append("SKIP  coverage     not run (--no-coverage); %d requests in the log" % c["logged_requests_in_window"])
    else:
        lines.append("%s  coverage     %d requests in session files, %d in the log%s" % (
            mark[c["ok"]], c["local_requests"], c["logged_requests_in_window"],
            "; %d token mismatches" % c["token_mismatches"] if c["token_mismatches"] else ""))
    for s in c["unlogged_sessions"][:10]:
        lines.append("        not logged: %s session %s… (%s), %d requests, %s tokens, from %s" % (
            s["project"][-40:], (s["session"] or "?")[:8], s["auth"], s["requests"],
            "{:,}".format(s["tokens"]), (s["first"] or "")[11:16]))
    if len(c["unlogged_sessions"]) > 10:
        lines.append("        ... and %d more sessions" % (len(c["unlogged_sessions"]) - 10))
    if b is None:
        lines.append("SKIP  bill         set ANTHROPIC_ADMIN_KEY and ANTHROPIC_API_KEY to check against Anthropic's records")
    else:
        prov = sum(b["provider_tokens"].values())
        gap = sum(sum(g["tokens"].values()) for g in b["gaps"])
        bg = sum(b["background_tokens"].values())
        lines.append("%s  bill         %s tokens billed: %s logged, %s Claude Code background, %s unexplained" % (
            mark[not b["gaps"]], "{:,}".format(prov), "{:,}".format(prov - bg - gap), "{:,}".format(bg),
            "{:,}".format(gap)))
        for g in b["gaps"]:
            lines.append("        unexplained %s-%s: %s tokens (%s)" % (
                g["start"][11:16], g["end"][11:16], "{:,}".format(sum(g["tokens"].values())),
                ", ".join(sorted(g["by_model"]))))
        if b["log_excess"]:
            lines.append("        the log has %d minute(s) with more than was billed to this key "
                         "(another key, or usage records still arriving)" % len(b["log_excess"]))
    s = res.get("sessions")
    if s is None:
        if b is not None:
            lines.append("SKIP  sessions     needs an Admin key and the key's ID")
    elif s.get("error"):
        lines.append("SKIP  sessions     %s" % s["error"])
    else:
        lines.append("%s  sessions     %s" % (mark[s["ok"]], (
            "Anthropic's daily count of Claude Code sessions and tokens on this key vs the log"
            if s["ok"] is not None else "no whole day the log covers to compare yet")))
        lines += daily.render_lines(s)
    lines += ["", "Level: %s" % LEVELS[res.get("level") or level(res)]]
    return "\n".join(lines)


def verify_report(log_path, report_path):
    """Check a received report against the published log: the report's head hash
    must be an entry of this log (so the log is the one the report was built from,
    possibly with more entries added later), and rebuilding the report from the log
    up to that entry, for the same window, must give the same tokens per category."""
    import json
    import os
    import tempfile
    from datetime import datetime
    from . import report as report_mod
    with open(report_path) as fh:
        pub = json.load(fh)
    head = (pub.get("log") or {}).get("head")
    upto = []
    found = False
    for _, e in chainlog.read_entries(log_path):
        upto.append(e)
        if e.get("hash") == head:
            found = True
            break
    if not found:
        return {"ok": False, "head_found": False, "head": head,
                "note": "the report's head hash is not in this log: it was built from a different log"}
    with tempfile.TemporaryDirectory() as d:
        prefix = os.path.join(d, "prefix.jsonl")
        with open(prefix, "w") as fh:
            for e in upto:
                fh.write(chainlog.canonical(e) + "\n")
        w = pub.get("window") or [None, None]
        parse = lambda s: datetime.fromisoformat(s) if s else None  # noqa: E731
        fresh = report_mod.build(prefix, start=parse(w[0]), end=parse(w[1]), only_projects=pub.get("only_projects"))
    pub_t = {c["category"]: c["tokens"] for c in pub.get("categories", [])}
    new_t = {c["category"]: c["tokens"] for c in fresh["categories"]}
    diffs = {cat: {t: [pub_t.get(cat, {}).get(t, 0), new_t.get(cat, {}).get(t, 0)] for t in TOKEN_TYPES
                   if pub_t.get(cat, {}).get(t, 0) != new_t.get(cat, {}).get(t, 0)}
             for cat in set(pub_t) | set(new_t)}
    diffs = {k: v for k, v in diffs.items() if v}
    return {"ok": not diffs and fresh["log"]["chain_ok"], "head_found": True, "head": head,
            "entries_at_head": len(upto), "chain_ok_to_head": fresh["log"]["chain_ok"],
            "differences": diffs, "report": fresh}
