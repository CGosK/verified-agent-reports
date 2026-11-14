"""Read API-request records out of the chained log."""

from . import chainlog, paths

TOKEN_TYPES = ("input", "output", "cache_read", "cache_creation")


# A received log is untrusted: anything that isn't the expected type is treated as missing.
def _dict(v):
    return v if isinstance(v, dict) else {}


def _event(e):
    return _dict(_dict(e).get("event"))


def _str(v):
    return v if isinstance(v, str) else None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) < 1e15 else 0


METRIC_TYPES = {"input": "input", "output": "output", "cacheRead": "cache_read",
                "cacheCreation": "cache_creation"}


def _auth(a):
    """How a request was billed when the run carries no mode tag: an API key or
    a Claude account. Logs from before the receiver kept auth= still carry the
    plan attribute, which only account sessions send."""
    if a.get("auth"):
        return a["auth"]
    if "anthropic.plan" in a:
        return "account"
    return "api_key" if "anthropic.provider" in a else None


def api_requests(log_path=paths.LOG_PATH):
    """Request records from claude_code.api_request events, plus one pseudo-request
    per auxiliary token-usage metric data point (background requests Claude Code
    counts in metrics but doesn't emit as events). Pseudo-requests have no
    request_id, so the session-file check ignores them."""
    out = []
    aux = {}
    for _, e in chainlog.read_entries(log_path):
        ev = _event(e)
        if ev.get("name") == "metric":
            a = _dict(ev.get("attributes"))
            if ev.get("metric") == "claude_code.token.usage" and a.get("query_source") == "auxiliary":
                r = _dict(ev.get("resource"))
                key = (_str(ev.get("time")), a.get("model"), a.get("session.id"))
                rec = aux.setdefault(key, {
                    "seq": e.get("seq"), "request_id": None, "session_id": a.get("session.id"),
                    "run_id": a.get("run.id") or r.get("run.id") or a.get("session.id"),
                    "category": a.get("category") or r.get("category") or "untagged",
                    "project": a.get("project") or r.get("project"),
                    "mode": a.get("run.mode") or r.get("run.mode") or _auth(a), "time": _str(ev.get("time")),
                    "model": a.get("model"), "query_source": "auxiliary", "cost_usd": 0.0,
                    "tokens": {t: 0 for t in TOKEN_TYPES}})
                t = METRIC_TYPES.get(a.get("type"))
                if t:
                    rec["tokens"][t] += int(_num(ev.get("value")))
            continue
        if ev.get("name") not in ("api_request", "claude_code.api_request"):
            continue
        a = _dict(ev.get("attributes"))
        r = _dict(ev.get("resource"))
        out.append({
            "seq": e.get("seq"),
            "request_id": a.get("request_id"),
            "session_id": a.get("session.id"),
            "run_id": a.get("run.id") or r.get("run.id") or a.get("session.id"),
            "category": a.get("category") or r.get("category") or "untagged",
            "project": a.get("project") or r.get("project"),
            "mode": a.get("run.mode") or r.get("run.mode") or _auth(a),
            "time": _str(a.get("event.timestamp") or ev.get("time")),
            "model": a.get("model"),
            "query_source": a.get("query_source"),
            "cost_usd": _num(a.get("cost_usd")),
            "tokens": {
                "input": int(_num(a.get("input_tokens"))),
                "output": int(_num(a.get("output_tokens"))),
                "cache_read": int(_num(a.get("cache_read_tokens"))),
                "cache_creation": int(_num(a.get("cache_creation_tokens"))),
            },
        })
    # Interactive sessions report auxiliary requests (titles, prompt suggestions,
    # compaction) both as api_request events and in the auxiliary token metric;
    # keep only metric usage beyond those events, so nothing is counted twice.
    # (Headless runs in our batches sent no auxiliary metric points at all.)
    in_events = {}
    for r in out:
        if is_auxiliary_source(r.get("query_source")):
            acc = in_events.setdefault((r.get("session_id"), r.get("model")), {t: 0 for t in TOKEN_TYPES})
            for t in TOKEN_TYPES:
                acc[t] += r["tokens"][t]
    extra = []
    for rec in sorted(aux.values(), key=lambda r: r.get("time") or ""):
        covered = in_events.get((rec.get("session_id"), rec.get("model")))
        if covered:
            for t in TOKEN_TYPES:
                take = min(covered[t], rec["tokens"][t])
                covered[t] -= take
                rec["tokens"][t] -= take
        if any(rec["tokens"].values()):
            extra.append(rec)
    return out + extra


def is_auxiliary_source(query_source):
    """Claude Code's query sources outside the main thread and subagents, which its
    metrics count as "auxiliary": session titles, prompt suggestions, compaction..."""
    qs = query_source or ""
    return bool(qs) and qs not in ("repl_main_thread", "sdk") and not qs.startswith("agent:")


def sessions(log_path=paths.LOG_PATH):
    """{session_id: {"first", "terminal", "mode", "project", "category"}} from every
    event in the log, including sessions that made no API request. "first" is the
    earliest event time (UTC ISO); "mode" is the run.mode tag or how it was billed."""
    out = {}
    for _, e in chainlog.read_entries(log_path):
        ev = _event(e)
        a = _dict(ev.get("attributes"))
        r = _dict(ev.get("resource"))
        sid = a.get("session.id")
        if not isinstance(sid, str) or not sid:
            continue
        t = _str(a.get("event.timestamp") or ev.get("time"))
        s = out.setdefault(sid, {"first": t, "terminal": None, "mode": None, "project": None, "category": None})
        if t and (not s["first"] or t < s["first"]):
            s["first"] = t
        s["terminal"] = s["terminal"] or a.get("terminal.type")
        s["mode"] = s["mode"] or a.get("run.mode") or r.get("run.mode") or _auth(a)
        s["project"] = s["project"] or a.get("project") or r.get("project")
        s["category"] = s["category"] or a.get("category") or r.get("category")
    return out
