"""The sessions check: Anthropic's daily count of Claude Code sessions and tokens
for an API key, compared with the log.

Anthropic's Claude Code Analytics API (part of the Admin API) reports, for each
UTC day and actor (an API key's name, or a Console user's email), how many
Claude Code sessions ran and their tokens by model. Claude Code itself reports
these to Anthropic: in our tests a session run with DISABLE_TELEMETRY=1 or
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 (either one alone) was billed but
never counted (work/results/telemetry_off_test.json, telemetry_off_bisect.json).
So the count catches sessions hidden only from the team's own log (25 of them on
Nov 14, every one counted), but not a team that also switches off Claude Code's
reporting; the bill is the record a team can't switch off.

vawr's own log still records such sessions (work/results/telemetry_off_otel_*.json),
so an honest team with either setting has more in its log than Anthropic counted.
So a day where the log has more sessions and more tokens than Anthropic counted
doesn't fail: it's "uncounted", which the bill check still covers but which keeps
a report from VERIFIED. Extra logged sessions with no tokens of their own fail, and
so does an uncounted day where the bill check needed more background allowance than
Anthropic's own session count justifies (see limit_background): a log padded with
made-up sessions mustn't buy cover for unlogged use of the key. Anthropic's tokens
matched the log exactly for logged sessions; they leave out the one background
request that Claude Code records nowhere (see billcheck), which the log doesn't
have either.

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


def log_days(log_paths, days, only_projects=None, ends=None):
    """The log's side: {day: {"sessions": set, "tokens": {model: n}}} for sessions billed
    to an API key (optionally only these project tags), plus when each log starts.
    Pass a list as `ends` to get when each log's last event is, in the same order."""
    if isinstance(log_paths, str):
        log_paths = [log_paths]
    # items may be (path, only_projects) pairs, for logs from several people
    log_paths = [(p, only_projects) if isinstance(p, str) else tuple(p) for p in log_paths]
    out = {d: {"sessions": set(), "tokens": Counter(), "cells": {}} for d in days}
    first = []

    def cell(d, term):  # Anthropic calls a session without a terminal type "unknown"; so does the log
        return out[d]["cells"].setdefault(term or "unknown", {"sessions": set(), "tokens": Counter()})
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
        # the log's span, from every timed event: a day with logged requests is never "before the log"
        times = [t for t in (_parse(s["first"]) for s in sess.values()) if t]
        times += [t for t in (_parse(r.get("time")) for r in api_requests(path)) if t]
        first.append(min(times).isoformat() if times else None)
        if ends is not None:
            ends.append(max(times).isoformat() if times else None)
    return out, first


def _parse(s):
    """Aware UTC datetime, or None for anything that isn't an ISO time (logs are untrusted)."""
    if not isinstance(s, str) or not s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _day(s):
    t = _parse(s)
    return t.astimezone(timezone.utc).date().isoformat() if t else None


RANK = {"fail": 6, "uncounted": 5, "pending": 4, "partial": 3, "pass_so_far": 2, "pass": 1, "before_log": 0}


def _status(a_sessions, a_tokens, l_sessions, l_tokens, complete, partial_log):
    """Verdict for one comparison of Anthropic's count with the log's."""
    models = sorted(set(a_tokens) | set(l_tokens))
    diff = {m: a_tokens.get(m, 0) - l_tokens.get(m, 0) for m in models if a_tokens.get(m, 0) != l_tokens.get(m, 0)}
    missing = a_sessions - l_sessions
    short = missing > 0 or any(v > 0 for v in diff.values())
    extra = missing < 0 or any(v < 0 for v in diff.values())
    if not short and not extra:
        return ("pass" if complete else "pass_so_far"), diff
    if partial_log and short:  # sessions outside the log; an excess beside them can't be judged either
        return "partial", diff
    if short:
        return "fail", diff
    if missing < 0 and not any(v < 0 for v in diff.values()):
        return "fail", diff  # sessions Anthropic never saw, with no usage of their own: made up
    # the log has more than Anthropic counted: Claude Code doesn't report sessions run with
    # DISABLE_TELEMETRY or CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC, though vawr logs them.
    # The bill check covers their tokens; limit_background stops them buying allowance.
    return ("uncounted" if complete else "pending"), diff


def compare(anth, logd, now, log_starts=(), log_ends=()):
    """Per-day verdicts, per terminal type where the log records it (Anthropic reports
    each actor's sessions by terminal type: "non-interactive" for `claude -p`, or the
    terminal's name). A day fails when Anthropic counted sessions or tokens the log
    doesn't have. Once the day is over, a log with more than Anthropic counted is
    "uncounted" (see the module docstring). A day the log only partly covers (it
    starts or ends during the day) doesn't fail on a shortfall: Anthropic's count
    for it includes sessions outside the log, which the per-minute bill check covers
    within the window. Such a day is "partial" and can't be confirmed."""
    starts = [_parse(s) for s in log_starts if s]
    ends = [_parse(s) for s in log_ends if s]
    rows = []
    for d in sorted(anth):
        a = anth[d]
        lg = logd.get(d) or {"sessions": set(), "tokens": Counter(), "cells": {}}
        day0 = datetime.combine(date.fromisoformat(d), datetime.min.time(), tzinfo=timezone.utc)
        complete = now >= day0 + timedelta(days=1) + LAG
        before_log = bool(starts) and all(s >= day0 + timedelta(days=1) for s in starts)
        partial_log = not before_log and ((bool(starts) and all(s > day0 for s in starts)) or
                                          (bool(ends) and all(e < day0 + timedelta(days=1) for e in ends)))
        cells = []
        if not before_log:
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


UNCONFIRMED = ("uncounted", "pending", "partial")


def overall(rows):
    """False if any day failed; True if none failed, none is unconfirmed (uncounted,
    pending or partial) and at least one day matched; None otherwise."""
    if any(r["status"] == "fail" for r in rows):
        return False
    if any(r["status"] in UNCONFIRMED for r in rows):
        return None
    return True if any(r["status"] in ("pass", "pass_so_far") for r in rows) else None


def check(admin_key, key_id, start, end, log_paths, only_projects=None, now=None, actor=None,
          key_name=None, fetch=None):
    """The sessions check for the days the window touches. Returns a dict with "ok"
    (False only if some day failed) and per-day rows, or "error" if it couldn't run."""
    now = now or datetime.now(timezone.utc)
    days = days_between(start, end)
    try:  # Anthropic's records: if they can't be read, the check didn't run
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
        anth = anthropic_days(admin_key, days, actor, fetch=fetch)
    except Exception as exc:
        return {"ok": None, "error": "couldn't read Anthropic's count: %s: %s" % (type(exc).__name__, exc)}
    # the log's side: an exception here comes from the log itself and isn't caught
    ends = []
    logd, starts = log_days(log_paths, days, only_projects, ends=ends)
    # a log runs at least to the end of the window it reports on (quiet hours have no
    # events), so a whole-day window is compared whole: a session hidden after the last
    # logged event still fails. A window that ends mid-day leaves that day partial.
    ends = [max(t, end).isoformat() for t in (_parse(e) or end for e in ends)]
    rows = compare(anth, logd, now, starts, ends)
    return summarize({"actor": actor, "key_id": key_id, "days": rows})


def summarize(res):
    """Set "ok", "uncounted_days" and "unconfirmed_days" ({day: status}) from the rows."""
    rows = res.get("days") or []
    res["ok"] = overall(rows)
    res["uncounted_days"] = [r["day"] for r in rows if r["status"] == "uncounted"]
    res["unconfirmed_days"] = {r["day"]: r["status"] for r in rows if r["status"] in UNCONFIRMED}
    return res


def eligible_sessions(log_paths, only_projects=None):
    """Session IDs that earn a background allowance in the bill check: the ones this
    check counts (billed to an API key, in the report's projects)."""
    if isinstance(log_paths, str):
        log_paths = [log_paths]
    out = set()
    for p in log_paths:
        path, only = (p, only_projects) if isinstance(p, str) else tuple(p)
        out |= {sid for sid, s in log_sessions(path).items()
                if s["mode"] in API_KEY_MODES and (not only or s["project"] in only)}
    return out


def limit_background(sess, bill, envelope=None, now=None):
    """A day fails if the bill check credited more background allowance that day than
    the sessions both Anthropic and the log counted justify (one allowance each): each
    logged session earns an allowance, so made-up sessions, counted or not, could
    otherwise pass unlogged use of the key as background. Minutes younger than the
    count's lag are left out, since Anthropic may not have counted their sessions yet."""
    if not isinstance(sess, dict) or not sess.get("days") or not isinstance(bill, dict):
        return sess
    from .auditor import BACKGROUND_ENVELOPE
    per_session = sum((envelope or BACKGROUND_ENVELOPE).values())
    cutoff = (now or datetime.now(timezone.utc)) - LAG
    used = Counter()
    for mm, v in (bill.get("per_minute") or {}).items():
        t = _parse(str(mm))
        if t and t < cutoff and isinstance(v, dict):
            used[t.date().isoformat()] += v.get("background", 0) or 0
    changed = False
    for r in sess["days"]:
        justified = min(r["anthropic_sessions"], r["log_sessions"]) * per_session
        if r["status"] != "fail" and used[r["day"]] > justified:
            r["status"] = "fail"
            r["background_over_count"] = {"credited": used[r["day"]], "justified": justified}
            changed = True
    return summarize(sess) if changed else sess


UNCOUNTED = ("Anthropic counted fewer Claude Code sessions and tokens than the log has on %s, so its count "
             "can't confirm the log. The likeliest cause is sessions run with DISABLE_TELEMETRY or "
             "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC, which Claude Code doesn't report to Anthropic but vawr "
             "logs; the bill check covers their tokens.")
PARTIAL = ("The log starts or ends partway through %s, so Anthropic's whole-day count can't confirm it; the bill "
           "check covers the window minute by minute. Report whole UTC days to get VERIFIED.")


def _days_text(days):
    days = list(days)
    return ", ".join(days) if len(days) <= 3 else "%s and %d more days" % (", ".join(days[:3]), len(days) - 3)


def uncounted_text(res):
    days = (res or {}).get("uncounted_days") or []
    return UNCOUNTED % _days_text(days) if days else ""


def unconfirmed_text(res):
    """NOTE text for the days the count can't confirm (not the pending ones, which a
    later run settles)."""
    un = (res or {}).get("unconfirmed_days") or {}
    parts = [uncounted_text(res)] if (res or {}).get("uncounted_days") else []
    partial = [d for d, st in sorted(un.items()) if st == "partial"]
    if partial:
        parts.append(PARTIAL % _days_text(partial))
    return " ".join(parts)


NOTES = {"pass": "", "pass_so_far": " (day not over)", "partial": " (the log starts or ends during this day)",
         "before_log": " (before the log started; not checked)",
         "pending": " (day not over; Anthropic's count lags up to an hour)", "fail": "",
         "uncounted": " (Anthropic counted fewer than the log has)"}


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
        bo = r.get("background_over_count")
        if bo:
            out.append("          the bill check credited %s tokens of background allowance this day; Anthropic's "
                       "count and the log's (%d and %d sessions) justify at most %s, so sessions the count doesn't "
                       "see can't explain the usage" % ("{:,}".format(bo["credited"]), r["anthropic_sessions"],
                                                        r["log_sessions"], "{:,}".format(bo["justified"])))
        if len(r.get("by_terminal") or []) > 1:
            for c in r["by_terminal"]:
                out.append("          %-16s %-11s Anthropic %d, log %d%s" % (
                    c["terminal"] or "unknown", c["status"].replace("_", " "), c["anthropic_sessions"],
                    c["log_sessions"], _diff_text(c["token_difference"])))
    return out
