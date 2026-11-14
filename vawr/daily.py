"""The sessions check: Anthropic's own daily count of Claude Code sessions and
tokens for an API key, compared with the log.

Anthropic's Claude Code Analytics API (part of the Admin API) reports, for each
UTC day and actor (an API key's name, or a Console user's email), how many
Claude Code sessions ran and their tokens by model. Anthropic counts these on its
side. In our runs it counted every session on the key, including 25 whose
telemetry never reached the log, and its tokens matched the log exactly for
sessions that were logged. It leaves out the one background request that Claude
Code records nowhere (see billcheck), which the log doesn't have either.

So on a day when everything was logged, the log's sessions and tokens per model
equal Anthropic's. A session that never reached the log shows up as a missing
session with its tokens, even when it overlapped logged work in the same minute,
which the per-minute bill check can't separate. The cost: Anthropic reports whole
UTC days, an hour or more behind, and only for usage on its own API (not a Claude
subscription, Bedrock or Vertex).
"""
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from . import chainlog, usage_api
from .logdata import api_requests, sessions as log_sessions

LAG = timedelta(hours=1)  # Anthropic leaves out data younger than this
API_KEY_MODES = ("api_key", "sprint")


def days_between(start, end):
    """UTC dates ("YYYY-MM-DD") from start's day to end's day, inclusive."""
    d, out = start.astimezone(timezone.utc).date(), []
    last = (end - timedelta(microseconds=1)).astimezone(timezone.utc).date()
    while d <= last:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _actor_matches(actor, want):
    if "api_key_name" in want:
        return actor.get("type") == "api_actor" and actor.get("api_key_name") == want["api_key_name"]
    return actor.get("type") == "user_actor" and (actor.get("email_address") or "").lower() == want["email"].lower()


def anthropic_days(admin_key, days, actor, fetch=None):
    """{day: {"sessions", "tokens": {model: n}, "terminals", "work"}} for one actor
    ({"api_key_name": ...} or {"email": ...}). `fetch(day)` replaces the API call in tests."""
    fetch = fetch or (lambda d: usage_api.claude_code_day(admin_key, d))
    out = {}
    for d in days:
        o = {"sessions": 0, "tokens": Counter(), "terminals": Counter(), "cells": {},
             "work": Counter()}
        for rec in fetch(d):
            if not _actor_matches(rec.get("actor") or {}, actor):
                continue
            core = rec.get("core_metrics") or {}
            n = core.get("num_sessions") or 0
            term = rec.get("terminal_type") or "unknown"
            o["sessions"] += n
            o["terminals"][term] += n
            cell = o["cells"].setdefault(term, {"sessions": 0, "tokens": Counter()})
            cell["sessions"] += n
            loc = core.get("lines_of_code") or {}
            o["work"]["lines_added"] += loc.get("added") or 0
            o["work"]["lines_removed"] += loc.get("removed") or 0
            o["work"]["commits"] += core.get("commits_by_claude_code") or 0
            o["work"]["pull_requests"] += core.get("pull_requests_by_claude_code") or 0
            for m in rec.get("model_breakdown") or []:
                n_tok = sum(v for v in (m.get("tokens") or {}).values() if isinstance(v, (int, float)))
                o["tokens"][m.get("model") or "?"] += n_tok
                cell["tokens"][m.get("model") or "?"] += n_tok
        out[d] = o
    return out


def log_days(log_paths, days, only_projects=None):
    """The log's side: {day: {"sessions": set, "tokens": {model: n}}} for sessions billed
    to an API key (optionally only these project tags), plus when each log starts."""
    if isinstance(log_paths, str):
        log_paths = [log_paths]
    # items may be (path, only_projects) pairs, for logs from several people
    log_paths = [(p, only_projects) if isinstance(p, str) else tuple(p) for p in log_paths]
    out = {d: {"sessions": set(), "tokens": Counter(), "cells": {}} for d in days}
    first = []

    def cell(d, term):
        return out[d]["cells"].setdefault(term, {"sessions": set(), "tokens": Counter()})
    seen = set()  # (log ID, entry seq): two bundles from one log share requests
    for path, only in log_paths:
        keep = lambda mode, project: mode in API_KEY_MODES and (not only or project in only)  # noqa: E731
        sess = log_sessions(path)
        lid = next((e.get("hash") for _, e in chainlog.read_entries(path) if isinstance(e, dict)), path)
        for sid, s in sess.items():
            d = _day(s["first"])
            if keep(s["mode"], s["project"]) and d in out:
                out[d]["sessions"].add(sid)
                cell(d, s["terminal"])["sessions"].add(sid)
        for r in api_requests(path):
            d = _day(r.get("time"))
            if keep(r.get("mode"), r.get("project")) and d in out and (lid, r.get("seq")) not in seen:
                seen.add((lid, r.get("seq")))
                n = sum(r["tokens"].values())
                out[d]["tokens"][r.get("model") or "?"] += n
                cell(d, (sess.get(r.get("session_id")) or {}).get("terminal"))["tokens"][r.get("model") or "?"] += n
        starts = [_parse(s["first"]) for s in sess.values()]
        starts = [t for t in starts if t]
        first.append(min(starts).isoformat() if starts else None)
    return out, first


def _parse(s):
    """Aware UTC datetime, or None for anything that isn't an ISO time (logs are untrusted)."""
    if not isinstance(s, str) or not s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _day(s):
    t = _parse(s)
    return t.astimezone(timezone.utc).date().isoformat() if t else None


RANK = {"fail": 5, "pending": 4, "partial": 3, "pass_so_far": 2, "pass": 1, "before_log": 0}


def _status(a_sessions, a_tokens, l_sessions, l_tokens, complete, partial_log):
    """Verdict for one comparison of Anthropic's count with the log's."""
    models = sorted(set(a_tokens) | set(l_tokens))
    diff = {m: a_tokens.get(m, 0) - l_tokens.get(m, 0) for m in models if a_tokens.get(m, 0) != l_tokens.get(m, 0)}
    missing = a_sessions - l_sessions
    short = missing > 0 or any(v > 0 for v in diff.values())
    extra = missing < 0 or any(v < 0 for v in diff.values())
    if not short and not extra:
        return ("pass" if complete else "pass_so_far"), diff
    if partial_log and not extra:
        return "partial", diff
    if short:
        return "fail", diff
    return ("fail" if complete else "pending"), diff  # the log has more than Anthropic counted


def compare(anth, logd, now, log_starts=()):
    """Per-day verdicts, per terminal type where the log records it (Anthropic reports
    each actor's sessions by terminal type: "non-interactive" for `claude -p`, or the
    terminal's name). A day fails when Anthropic counted sessions or tokens the log
    doesn't have, or (once the day is over) the log has more than Anthropic counted.
    A day the log only partly covers (it started that day) doesn't fail on a shortfall."""
    starts = [_parse(s) for s in log_starts if s]
    rows = []
    for d in sorted(anth):
        a = anth[d]
        lg = logd.get(d) or {"sessions": set(), "tokens": Counter(), "cells": {}}
        day0 = datetime.combine(date.fromisoformat(d), datetime.min.time(), tzinfo=timezone.utc)
        complete = now >= day0 + timedelta(days=1) + LAG
        before_log = bool(starts) and all(s >= day0 + timedelta(days=1) for s in starts)
        partial_log = bool(starts) and all(s > day0 for s in starts) and not before_log
        cells = []
        if not before_log and None not in lg.get("cells", {}):  # every logged session has its terminal type
            for term in sorted(set(a.get("cells", {})) | set(lg.get("cells", {}))):
                ac = a["cells"].get(term) or {"sessions": 0, "tokens": Counter()}
                lc = lg["cells"].get(term) or {"sessions": set(), "tokens": Counter()}
                st, diff = _status(ac["sessions"], ac["tokens"], len(lc["sessions"]), lc["tokens"],
                                   complete, partial_log)
                cells.append({"terminal": term, "status": st, "anthropic_sessions": ac["sessions"],
                              "log_sessions": len(lc["sessions"]), "token_difference": diff})
        if before_log:
            status, diff = "before_log", {}
        else:
            status, diff = _status(a["sessions"], a["tokens"], len(lg["sessions"]), lg["tokens"],
                                   complete, partial_log)
            if cells:
                status = max([status] + [c["status"] for c in cells], key=RANK.get)
        rows.append({"day": d, "status": status, "complete": complete,
                     "anthropic_sessions": a["sessions"], "log_sessions": len(lg["sessions"]),
                     "anthropic_tokens": dict(a["tokens"]), "log_tokens": dict(lg["tokens"]),
                     "token_difference": diff, "by_terminal": cells, "work": dict(a["work"])})
    return rows


def overall(rows):
    """False if any day failed; True if none failed and at least one day matched; None
    if no day could be checked (before or partly before the log, or not over yet)."""
    if any(r["status"] == "fail" for r in rows):
        return False
    return True if any(r["status"] in ("pass", "pass_so_far") for r in rows) else None


def check(admin_key, key_id, start, end, log_paths, only_projects=None, now=None, actor=None,
          key_name=None, fetch=None):
    """The sessions check for the days the window touches. Returns a dict with "ok"
    (False only if some day failed) and per-day rows, or "error" if it couldn't run."""
    now = now or datetime.now(timezone.utc)
    if actor is None:
        if key_name is None:
            keys = [k for k in usage_api.api_keys(admin_key)]
            match = [k for k in keys if k.get("id") == key_id]
            if not match:
                return {"ok": None, "error": "key %s isn't in this Admin key's organization" % key_id}
            key_name = match[0].get("name")
            if sum(1 for k in keys if k.get("name") == key_name) > 1:
                return {"ok": None, "error": "more than one key in the organization is named %r; Anthropic's "
                        "Claude Code analytics names keys, not IDs, so it can't tell them apart" % key_name}
        actor = {"api_key_name": key_name}
    days = days_between(start, end)
    anth = anthropic_days(admin_key, days, actor, fetch=fetch)
    logd, starts = log_days(log_paths, days, only_projects)
    rows = compare(anth, logd, now, starts)
    return {"ok": overall(rows), "actor": actor, "key_id": key_id, "days": rows}


NOTES = {"pass": "", "pass_so_far": " (day not over)", "partial": " (the log started this day)",
         "before_log": " (before the log started; not checked)",
         "pending": " (day not over; Anthropic's count lags up to an hour)", "fail": ""}


def _diff_text(diff):
    return "; tokens Anthropic minus log: %s" % ", ".join(
        "%s %+d" % (m, v) for m, v in sorted(diff.items())) if diff else ""


def render_lines(res):
    """Indented detail lines for `vawr check` and `vawr receive`."""
    out = []
    for r in res.get("days", []):
        out.append("        %s  Anthropic counted %d Claude Code session%s, the log has %d%s%s" % (
            r["day"], r["anthropic_sessions"], "" if r["anthropic_sessions"] == 1 else "s", r["log_sessions"],
            NOTES[r["status"]], _diff_text(r["token_difference"])))
        if len(r.get("by_terminal") or []) > 1:
            for c in r["by_terminal"]:
                out.append("          %-16s %-11s Anthropic %d, log %d%s" % (
                    c["terminal"] or "unknown", c["status"].replace("_", " "), c["anthropic_sessions"],
                    c["log_sessions"], _diff_text(c["token_difference"])))
    return out
