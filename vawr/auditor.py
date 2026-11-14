"""Auditor view: four checks of the chained log.

1. chain     the hash chain recomputes
2. totals    the allocation report's totals match a fresh recount of the log
3. sessions  every request in Claude Code's session files for runs/ is in the
             log, every logged request is in the files, and token counts agree
4. provider  Anthropic's per-minute usage for the Sprint key is matched by
             logged requests within a small time shift; leftover provider
             tokens are work done off the log

The provider check never reads run manifests: it finds gaps from the two
records alone.
"""

import json
import os
from datetime import datetime, timedelta, timezone

from . import chainlog, paths, report, sessions, usage_api
from .logdata import TOKEN_TYPES, api_requests
from .runner import load_env

# query_source values for requests Claude Code makes for itself (compaction,
# titles); they may have no assistant entry in the session file.
AUXILIARY_SOURCES = {"compact", "auto_compact", "title", "summary", "away_summary"}


def parse_ts(s):
    if not s:
        return None
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def minute_of(dt):
    return dt.replace(second=0, microsecond=0)


def check_chain(log_path):
    ok, problems, count, head = chainlog.verify(log_path)
    return {"ok": ok, "entries": count, "head": head, "problems": problems[:50],
            "problem_count": len(problems)}


def check_totals(log_path, report_path=None):
    fresh = report.build(log_path)
    if not report_path:
        return {"ok": True, "note": "no published report given; recount only",
                "categories": {c["category"]: c["total_tokens"] for c in fresh["categories"]}}
    with open(report_path) as fh:
        published = json.load(fh)
    pub = {c["category"]: c["tokens"] for c in published["categories"]}
    new = {c["category"]: c["tokens"] for c in fresh["categories"]}
    diffs = {}
    for cat in set(pub) | set(new):
        a, b = pub.get(cat, {}), new.get(cat, {})
        d = {t: (a.get(t, 0), b.get(t, 0)) for t in TOKEN_TYPES if a.get(t, 0) != b.get(t, 0)}
        if d:
            diffs[cat] = d
    return {"ok": not diffs, "differences": diffs}


def check_sessions(log_reqs, start, end, runs_dir=paths.RUNS_DIR):
    files = sessions.requests_in_scope(start, end, runs_dir)
    log_in_window = {r["request_id"]: r for r in log_reqs
                     if r["request_id"] and start <= parse_ts(r["time"]) <= end}
    log_ids = {r["request_id"] for r in log_reqs if r["request_id"]}
    missing_from_log = sorted(set(files) - log_ids)
    missing_from_files = sorted(rid for rid, r in log_in_window.items()
                                if rid not in files and r["query_source"] not in AUXILIARY_SOURCES)
    token_mismatch = {}
    for rid in set(files) & set(log_in_window):
        if files[rid]["tokens"] != log_in_window[rid]["tokens"]:
            token_mismatch[rid] = {"log": log_in_window[rid]["tokens"], "files": files[rid]["tokens"]}
    off_log_sessions = sorted({files[r]["session_id"] for r in missing_from_log})
    return {
        "ok": not (missing_from_log or missing_from_files or token_mismatch),
        "requests_in_files": len(files),
        "requests_in_log_window": len(log_in_window),
        "missing_from_log": missing_from_log,
        "off_log_sessions": off_log_sessions,
        "missing_from_files": missing_from_files,
        "token_mismatch": token_mismatch,
    }


def match_minutes(provider, logged, minutes, shift):
    """Greedy earliest-first matching of provider tokens to logged tokens that
    lie within +/- shift minutes. Returns (unmatched_provider, unmatched_log),
    both {minute: tokens}."""
    remaining = dict(logged)
    unmatched = {}
    for m in minutes:
        need = provider.get(m, 0)
        if not need:
            continue
        for j in range(-shift, shift + 1):
            mm = m + timedelta(minutes=j)
            have = remaining.get(mm, 0)
            if have:
                take = min(need, have)
                remaining[mm] = have - take
                need -= take
                if not need:
                    break
        if need:
            unmatched[m] = need
    return unmatched, {m: v for m, v in remaining.items() if v}


def cluster(flagged, gap_minutes=2):
    """Group flagged minutes into events separated by more than gap_minutes."""
    events = []
    for m in sorted(flagged):
        if events and (m - events[-1]["end"]) <= timedelta(minutes=gap_minutes):
            events[-1]["end"] = m
            events[-1]["minutes"].append(m)
        else:
            events.append({"start": m, "end": m, "minutes": [m]})
    return events


# Claude Code 2.1.322 makes one small-model request per session that the
# provider bills but that appears in none of Claude Code's own records
# (telemetry events, token metrics, session files, per-model cost totals).
# The provider check attributes at most one such request to each logged
# session, within this envelope, measured on the ten pilot runs where the
# request could be separated from the agent's own requests (provider records
# in work/pilot/provider_minutes.json): cache-read was always 7,010 and
# cache-creation always 0; input ran 269-643 and output 160-861. Anything
# beyond it, or with no logged session within the shift window, is a gap.
BACKGROUND_MODEL = "claude-haiku-5-5"
BACKGROUND_ENVELOPE = {"input": 1000, "output": 1500, "cache_read": 7010, "cache_creation": 0}


def _by_model(provider_minutes):
    """Normalize to {minute: {model: tokens}}; a flat token dict becomes model '*'."""
    out = {}
    for mm, v in provider_minutes.items():
        if v and all(k in TOKEN_TYPES for k in v):
            out[mm] = {"*": v}
        else:
            out[mm] = v or {}
    return out


def check_provider(log_reqs, start, end, shift=2, tolerance=None, key_mode="sprint",
                   provider_minutes=None, background_model=BACKGROUND_MODEL,
                   background_envelope=BACKGROUND_ENVELOPE, recorded_totals=None):
    """recorded_totals: optional [(first_time, last_time, model, {type: tokens}), ...],
    usage a record shows only as a total over a time span (Claude Code's per-session
    cost totals include requests its session files don't list one by one: session
    titles, prompt suggestions, compaction). After per-minute matching, each total
    covers unmatched billed tokens of its model inside its span, up to its amount."""
    tolerance = tolerance or {t: 0 for t in TOKEN_TYPES}
    if provider_minutes is None:
        env = load_env()
        admin, api_key = env.get("ANTHROPIC_ADMIN_KEY"), env.get("ANTHROPIC_API_KEY")
        if not (admin and api_key):
            return {"ok": None, "skipped": "keys missing from .env"}
        key_id = usage_api.find_key_id(admin, api_key)
        if not key_id:
            return {"ok": None, "skipped": "Sprint key not found in the organization"}
        raw = usage_api.minute_usage(admin, key_id, start, end)
        provider_minutes = {parse_ts(k): v for k, v in raw.items()}
    pm = _by_model({mm: v for mm, v in provider_minutes.items() if start <= mm < end})
    flat = bool(pm) and all(set(v) <= {"*"} for v in pm.values())
    minutes = []
    m = minute_of(start)
    while m < end:
        minutes.append(m)
        m += timedelta(minutes=1)

    logged = {}      # model -> type -> minute -> tokens
    sessions = {}    # session id -> [first minute, last minute]
    logged_by_session = {}  # session id -> type -> tokens
    for r in log_reqs:
        if r["mode"] != key_mode:
            continue
        ts = parse_ts(r["time"])
        if not ts or not (start <= ts < end):
            continue
        mm = minute_of(ts)
        model = "*" if flat else (r.get("model") or "*")
        for t in TOKEN_TYPES:
            slot = logged.setdefault(model, {}).setdefault(t, {})
            slot[mm] = slot.get(mm, 0) + r["tokens"][t]
        sid = r.get("session_id") or r.get("run_id") or r.get("request_id")
        span = sessions.setdefault(sid, [mm, mm])
        span[0], span[1] = min(span[0], mm), max(span[1], mm)
        sess_tokens = logged_by_session.setdefault(sid, {t: 0 for t in TOKEN_TYPES})
        for t in TOKEN_TYPES:
            sess_tokens[t] += r["tokens"][t]

    models = set(logged) | {mod for v in pm.values() for mod in v}
    unmatched_p = {mod: {} for mod in models}
    unmatched_l = {mod: {} for mod in models}
    for mod in models:
        for t in TOKEN_TYPES:
            prov = {mm: v[mod][t] for mm, v in pm.items() if mod in v and v[mod].get(t)}
            up, ul = match_minutes(prov, logged.get(mod, {}).get(t, {}), minutes, shift)
            unmatched_p[mod][t], unmatched_l[mod][t] = up, ul

    # usage known only as per-span totals covers unmatched billed tokens in its span
    totals_used = {t: 0 for t in TOKEN_TYPES}
    for first, last, model, amounts in recorded_totals or ():
        if model not in unmatched_p:
            continue
        a0 = minute_of(parse_ts(first)) - timedelta(minutes=shift)
        a1 = minute_of(parse_ts(last)) + timedelta(minutes=shift)
        left = dict(amounts)
        up = unmatched_p[model]
        for t in TOKEN_TYPES:
            for mm in sorted(mm for mm in up[t] if a0 <= mm <= a1):
                take = min(up[t][mm], left.get(t, 0))
                if take:
                    up[t][mm] -= take
                    left[t] -= take
                    totals_used[t] += take
                    if not up[t][mm]:
                        up[t].pop(mm)

    # attribute background requests to logged sessions, one envelope each
    background = {t: 0 for t in TOKEN_TYPES}
    background_by_minute = {}
    budgets = {}
    if background_model in unmatched_p and background_envelope:
        budgets = {sid: dict(background_envelope) for sid in sessions}
        spans = {sid: (a - timedelta(minutes=shift), b + timedelta(minutes=shift)) for sid, (a, b) in sessions.items()}
        bg = unmatched_p[background_model]
        for mm in sorted({mm for t in TOKEN_TYPES for mm in bg[t]}):
            eligible = [sid for sid, (a, b) in spans.items() if a <= mm <= b]
            for t in TOKEN_TYPES:
                need = bg[t].get(mm, 0)
                for sid in eligible:
                    take = min(need, budgets[sid][t])
                    budgets[sid][t] -= take
                    background[t] += take
                    background_by_minute[mm] = background_by_minute.get(mm, 0) + take
                    need -= take
                    if not need:
                        break
                if need:
                    bg[t][mm] = need
                else:
                    bg[t].pop(mm, None)

    flagged_p, flagged_l = set(), set()
    for mod in models:
        for t in TOKEN_TYPES:
            flagged_p |= {mm for mm, v in unmatched_p[mod][t].items() if v > tolerance[t]}
            flagged_l |= {mm for mm, v in unmatched_l[mod][t].items() if v > tolerance[t]}

    def describe(events, source):
        out = []
        for ev in events:
            by_model = {}
            for mod in models:
                toks = {t: sum(source[mod][t].get(mm, 0) for mm in ev["minutes"]) for t in TOKEN_TYPES}
                if any(toks.values()):
                    by_model[mod] = toks
            total = {t: sum(v[t] for v in by_model.values()) for t in TOKEN_TYPES}
            out.append({"start": ev["start"].isoformat(), "end": ev["end"].isoformat(),
                        "tokens": total, "by_model": by_model})
        return out

    gaps = describe(cluster(flagged_p), unmatched_p)
    excess = describe(cluster(flagged_l), unmatched_l)
    per_minute = {}
    for mm in minutes:
        provided = sum(v[t] for v in pm.get(mm, {}).values() for t in TOKEN_TYPES)
        gap = sum(unmatched_p[mod][t].get(mm, 0) for mod in models for t in TOKEN_TYPES)
        bgm = background_by_minute.get(mm, 0)
        if provided or gap or bgm:
            per_minute[mm.isoformat()] = {"provider": provided, "background": bgm, "gap": gap,
                                          "matched": max(0, provided - bgm - gap)}
    # each logged session's share of provider tokens in the minutes it spans;
    # exact only when no other session or gap shares those minutes (flagged below)
    per_session = {}
    for sid, (a, b) in sorted(sessions.items(), key=lambda kv: kv[1][0]):
        span = [mm for mm in minutes if a <= mm <= b]
        prov = sum(per_minute.get(mm.isoformat(), {}).get("provider", 0) for mm in span)
        bg = sum(background_by_minute.get(mm, 0) for mm in span)
        shared = any(o != sid and oa <= b and a <= ob for o, (oa, ob) in sessions.items()) or \
            any(per_minute.get(mm.isoformat(), {}).get("gap") for mm in span)
        per_session[sid] = {"first_minute": a.isoformat(), "last_minute": b.isoformat(),
                            "logged_tokens": logged_by_session[sid], "provider_tokens_in_span": prov,
                            "background_in_span": bg, "background_share": bg / prov if prov else None,
                            "span_shared": shared}
    prov_total = {t: sum(v[t] for mv in pm.values() for v in mv.values()) for t in TOKEN_TYPES}
    log_total = {t: sum(sum(logged[mod].get(t, {}).values()) for mod in logged) for t in TOKEN_TYPES}
    return {
        "ok": not gaps and not excess,
        "window": [start.isoformat(), end.isoformat()],
        "shift_minutes": shift,
        "tolerance": tolerance,
        "provider_tokens": prov_total,
        "logged_tokens": log_total,
        "background_tokens": background,
        "recorded_totals_tokens": totals_used,
        "background_model": background_model,
        "logged_sessions": len(sessions),
        "per_session": per_session,
        # background tokens credited to each logged session (its envelope minus what's left);
        # between sessions minutes apart this is that session's own request
        "background_by_session": {sid: {t: background_envelope[t] - b[t] for t in TOKEN_TYPES}
                                  for sid, b in (budgets or {}).items()},
        "gaps": gaps,
        "log_excess": excess,
        "per_minute": per_minute,
        "minutes_checked": len(minutes),
        "clean_minutes": len([mm for mm in minutes if mm not in flagged_p and mm not in flagged_l]),
    }


def audit(start=None, end=None, log_path=paths.LOG_PATH, report_path=None, shift=2, provider=True):
    now = datetime.now(timezone.utc)
    log_reqs = api_requests(log_path)
    times = [parse_ts(r["time"]) for r in log_reqs if r["time"]]
    start = start or ((min(times) - timedelta(minutes=1)) if times else now - timedelta(hours=1))
    end = end or (now - timedelta(minutes=10))
    result = {
        "audited_at": now.isoformat(),
        "window": [start.isoformat(), end.isoformat()],
        "chain": check_chain(log_path),
        "totals": check_totals(log_path, report_path),
        "sessions": check_sessions(log_reqs, start, end),
    }
    result["provider"] = check_provider(log_reqs, start, end, shift=shift) if provider else {"ok": None, "skipped": "disabled"}
    result["ok"] = all(result[k]["ok"] is not False for k in ("chain", "totals", "sessions", "provider"))
    return result


def summarize(res):
    def mark(v):
        return {True: "PASS", False: "FAIL", None: "SKIP"}[v]
    s = res["sessions"]
    p = res["provider"]
    lines = [
        "Audit window %s to %s" % tuple(res["window"]),
        "%s  chain: %d entries%s" % (mark(res["chain"]["ok"]), res["chain"]["entries"],
                                     "" if res["chain"]["ok"] else "; " + "; ".join(res["chain"]["problems"][:3])),
        "%s  totals: %s" % (mark(res["totals"]["ok"]), res["totals"].get("note") or res["totals"].get("differences")),
        "%s  session files: %d requests in files, %d in log window; %d missing from log, %d missing from files, %d token mismatches"
        % (mark(s["ok"]), s["requests_in_files"], s["requests_in_log_window"], len(s["missing_from_log"]),
           len(s["missing_from_files"]), len(s["token_mismatch"])),
    ]
    if p.get("skipped"):
        lines.append("SKIP  provider: %s" % p["skipped"])
    else:
        lines.append("%s  provider: %d minutes, %d gaps, %d log-excess events; provider %s vs log %s"
                     % (mark(p["ok"]), p["minutes_checked"], len(p["gaps"]), len(p["log_excess"]),
                        sum(p["provider_tokens"].values()), sum(p["logged_tokens"].values())))
        for g in p["gaps"]:
            lines.append("      gap %s to %s: %s" % (g["start"], g["end"], g["tokens"]))
    return "\n".join(lines)
