"""Read API-request records out of the chained log."""

from . import chainlog, paths

TOKEN_TYPES = ("input", "output", "cache_read", "cache_creation")


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
        ev = e.get("event") or {}
        if ev.get("name") == "metric":
            a = ev.get("attributes") or {}
            if ev.get("metric") == "claude_code.token.usage" and a.get("query_source") == "auxiliary":
                r = ev.get("resource") or {}
                key = (ev.get("time"), a.get("model"), a.get("session.id"))
                rec = aux.setdefault(key, {
                    "seq": e.get("seq"), "request_id": None, "session_id": a.get("session.id"),
                    "run_id": a.get("run.id") or r.get("run.id") or a.get("session.id"),
                    "category": a.get("category") or r.get("category") or "untagged",
                    "mode": a.get("run.mode") or r.get("run.mode") or _auth(a), "time": ev.get("time"),
                    "model": a.get("model"), "query_source": "auxiliary", "cost_usd": 0.0,
                    "tokens": {t: 0 for t in TOKEN_TYPES}})
                t = METRIC_TYPES.get(a.get("type"))
                if t:
                    rec["tokens"][t] += int(ev.get("value") or 0)
            continue
        if ev.get("name") not in ("api_request", "claude_code.api_request"):
            continue
        a = ev.get("attributes") or {}
        r = ev.get("resource") or {}
        out.append({
            "seq": e.get("seq"),
            "request_id": a.get("request_id"),
            "session_id": a.get("session.id"),
            "run_id": a.get("run.id") or r.get("run.id") or a.get("session.id"),
            "category": a.get("category") or r.get("category") or "untagged",
            "project": a.get("project") or r.get("project"),
            "mode": a.get("run.mode") or r.get("run.mode") or _auth(a),
            "time": a.get("event.timestamp") or ev.get("time"),
            "model": a.get("model"),
            "query_source": a.get("query_source"),
            "cost_usd": a.get("cost_usd") or 0.0,
            "tokens": {
                "input": a.get("input_tokens") or 0,
                "output": a.get("output_tokens") or 0,
                "cache_read": a.get("cache_read_tokens") or 0,
                "cache_creation": a.get("cache_creation_tokens") or 0,
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
