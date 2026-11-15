"""One self-contained HTML page a team can hand to a funder: where the agents'
usage went, which independent checks passed, and what the funder needs to
re-run the checks on the published log.

    render(report, check=None, billcheck=None, categories=None, claims=None, title=None) -> str

Inputs are the dicts the other commands write: the allocation report
(`vawr report --out`), `vawr check --json`, `vawr billcheck --json`, the
category check (its "summary" and "rows") and the claim checker's summary.
Only `report` is required; a section whose input is missing is left out.

The page has inline CSS and no scripts, fonts or images, so it works offline;
it follows the reader's light or dark setting and prints on Letter or A4.
Every figure comes from the inputs (at most summed, subtracted or divided),
and every string from the inputs is escaped: some of it is model-written.
"""

import html
import shlex
from datetime import datetime, timezone

from . import __version__
from .daily import unconfirmed_text

CATEGORY_ORDER = ("safety", "capabilities", "other")
TOKEN_TYPES = (("input", "Input"), ("output", "Output"), ("cache_read", "Cache read"),
               ("cache_creation", "Cache write"))
API_KEY_MODES = ("sprint", "api_key")  # run modes billed to an API key (see check.run)
AUTH_NAMES = {"api_key": "API key", "account": "Claude account"}
MODE_NAMES = {"sprint": "API key", "api_key": "API key", "subscription": "Claude subscription"}
CHECK_ORDER = ("chain", "coverage", "bill", "sessions", "continuity", "category", "claims")
CHECK_TITLES = {"chain": "Chain", "coverage": "Coverage", "bill": "Bill", "sessions": "Sessions",
                "continuity": "Continuity", "category": "Category", "claims": "Claims"}
LEVEL_TEXT = {
    "provider": ("Checked against Anthropic's records",
                 "The usage figures match Anthropic's own billing records for the API key."),
    "provider-unconfirmed": ("Bill checked against Anthropic's records",
                             "Usage billed to the API key matches Anthropic's billing records, but Anthropic's "
                             "daily session count could not confirm every day (see the Sessions check)."),
    "tamper-evident": ("Tamper-evident only",
                       "The log has not been edited since it was written, but it was not checked against "
                       "Anthropic's records (no Admin key, or usage on a Claude subscription, for which "
                       "Anthropic offers no records)."),
    "failed": ("A check failed", "See the checks below before relying on these figures."),
}
STATUS_TEXT = {"pass": "Pass", "fail": "Fail", "skip": "Skipped"}


# ---------- formatting ----------

def _e(value):
    return html.escape("" if value is None else str(value), quote=True)


def _num(value):
    try:
        return "{:,}".format(int(value))
    except (TypeError, ValueError):
        return _e(value)


def _pct(part, whole):
    try:
        return "%.1f%%" % (100.0 * part / whole) if whole else "n/a"
    except TypeError:
        return "n/a"


def _usd(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _e(value)
    return "$" + ("{:,.2f}".format(v) if v >= 100 else "{:.4f}".format(v))


def _count(n, word, plural=None):
    return "%s %s" % (_num(n), word if n == 1 else (plural or word + "s"))


def _tokens(d):
    """Total of a {token type: count} dict."""
    if not isinstance(d, dict):
        return 0
    return sum(v for v in d.values() if isinstance(v, (int, float)) and not isinstance(v, bool))


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _ts(s):
    """'2026-11-13 20:50' from an ISO time, escaped."""
    s = "" if s is None else str(s)
    return _e(s[:16].replace("T", " ") if len(s) >= 16 else s)


def _hhmm(s):
    s = "" if s is None else str(s)
    return _e(s[11:16] if len(s) >= 16 else s)


def _window_text(window):
    if not (isinstance(window, (list, tuple)) and len(window) == 2 and all(window)):
        return None
    a, b = str(window[0]), str(window[1])
    if a[:10] == b[:10] and len(b) >= 16:
        return "%s to %s UTC" % (_ts(a), _hhmm(b))
    return "%s to %s UTC" % (_ts(a), _ts(b))


def _rate(r, noun=""):
    """'55 of 55 (100%; 95% interval 94–100%)' from a {k, n, ci95} dict, or None;
    `noun` (safe HTML) goes after the counts."""
    if not isinstance(r, dict) or not _int(r.get("n")):
        return None
    k, n = _int(r.get("k")), r["n"]
    out = "%s of %s%s (%.0f%%" % (_num(k), _num(n), " " + noun if noun else "", 100.0 * k / n)
    ci = r.get("ci95")
    try:
        out += "; 95%% interval %.0f–%.0f%%" % (100 * float(ci[0]), 100 * float(ci[1]))
    except (TypeError, ValueError, IndexError, KeyError):
        pass
    return out + ")"


def _cap(s):
    return s[:1].upper() + s[1:] if s else s


def _bar(share):
    """Share bar as inline SVG: it prints without background graphics and is
    decorative (the percentage is written next to it)."""
    try:
        w = max(0.0, min(100.0, 100.0 * float(share)))
    except (TypeError, ValueError):
        w = 0.0
    return ('<svg class="bar" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true" '
            'focusable="false"><rect class="track" width="100" height="8"/>'
            '<rect class="fill" width="%.2f" height="8"/></svg>' % w)


def _table(head, rows, cls="", num_cols=()):
    """head: column titles (already safe); rows: lists of safe cell HTML."""
    th = "".join('<th scope="col"%s>%s</th>' % (' class="num"' if i in num_cols else "", h)
                 for i, h in enumerate(head))
    body = "".join("<tr>%s</tr>" % "".join(
        '<td%s>%s</td>' % (' class="num"' if i in num_cols else "", c) for i, c in enumerate(r))
        for r in rows)
    return ('<div class="table-wrap"><table%s><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
            % (' class="%s"' % cls if cls else "", th, body))


# ---------- inputs ----------

def _categories(report):
    cats = [c for c in report.get("categories") or [] if isinstance(c, dict)]
    rank = {name: i for i, name in enumerate(CATEGORY_ORDER)}
    return sorted(cats, key=lambda c: (rank.get(c.get("category"), len(rank)), str(c.get("category"))))


def _cat_tokens(c):
    if isinstance(c.get("total_tokens"), (int, float)):
        return c["total_tokens"]
    return _tokens(c.get("tokens"))


def _runs(report):
    return [r for r in report.get("runs") or [] if isinstance(r, dict)]


def _run_tokens(report):
    return {r.get("run_id"): _tokens(r.get("tokens")) for r in _runs(report)}


def _modes(report):
    """(runs billed to an API key, runs on a subscription, all runs) from the report."""
    runs = _runs(report)
    key = sum(1 for r in runs if r.get("mode") in API_KEY_MODES)
    sub = sum(1 for r in runs if r.get("mode") == "subscription")
    return key, sub, len(runs)


# ---------- checks ----------
# Each builder returns None when its input is missing, else a dict:
#   status: pass | fail | skip; short: phrase for the verdict line;
#   result, means, limits: one sentence each; details: HTML or "".
# Every value is already safe HTML.

def _chain(report, check):
    log = report.get("log") or {}
    ch = check.get("chain") if isinstance(check, dict) and isinstance(check.get("chain"), dict) else None
    rep_ok = log.get("chain_ok")
    chk_ok = ch.get("ok") if ch else None
    if rep_ok is None and chk_ok is None:
        return None
    ok = rep_ok is not False and chk_ok is not False
    problems = [p for p in (ch or {}).get("problems") or []]
    entries = ch.get("entries") if ch and ch.get("entries") is not None else log.get("entries")
    if ok:
        status = "pass"
        result = "All %s entries' hashes recompute%s." % (
            _num(entries), "" if ch else ", as checked when the report was built")
        short = "every entry's hash recomputes"
    else:
        status = "fail"
        when = " when the report was built" if rep_ok is False and chk_ok is not False else ""
        result = "The log's hash chain did not recompute%s%s." % (
            when, ": " + _e(problems[0]) if problems else "")
        short = "the log's hash chain does not recompute"
    details = ""
    if problems:
        details = "<p>Problems found (first %s):</p><ul>%s</ul>" % (
            _num(len(problems)), "".join("<li><code>%s</code></li>" % _e(p) for p in problems))
    return {
        "key": "chain", "status": status, "short": short, "result": result,
        "means": "No entry was edited, deleted or reordered after it was written.",
        "limits": "Whoever holds the log can rebuild the whole chain after an edit, so this check only "
                  "ties the figures to the head hash given below: compare that hash with any copy of the "
                  "log you receive.",
        "details": details,
    }


def _coverage(check):
    cov = check.get("coverage") if isinstance(check, dict) else None
    if not isinstance(cov, dict):
        return None
    unlogged = [s for s in cov.get("unlogged_sessions") or [] if isinstance(s, dict)]
    mism = _int(cov.get("token_mismatches"))
    local = cov.get("local_requests")
    logged = cov.get("logged_requests_in_window")
    ok = cov.get("ok")
    if ok is None:
        ok = not unlogged and not mism
    reqs = sum(_int(s.get("requests")) for s in unlogged)
    toks = sum(_int(s.get("tokens")) for s in unlogged)
    if ok:
        status, short = "pass", "every local request is in the log"
        if local:
            result = ("All %s requests in the team's Claude Code session files for the window are in the "
                      "log, with matching token counts." % _num(local))
        else:
            result = ("The team's machine had no Claude Code session files with requests in the window, "
                      "so there was nothing to compare.")
    else:
        status = "fail"
        parts = []
        if unlogged:
            parts.append("%s on the team's machine (%s, %s tokens) %s missing from the log" % (
                _count(len(unlogged), "session"), _count(reqs, "request"), _num(toks),
                "is" if len(unlogged) == 1 else "are"))
        if mism:
            parts.append("%s in the log %s token counts that differ from the session files" % (
                _count(mism, "request"), "has" if mism == 1 else "have"))
        if not parts:
            parts.append("the check reported a problem but listed no sessions or mismatches")
        result = _cap("; ".join(parts)) + "."
        short = "; ".join(parts)
    details = ""
    if local is not None or unlogged:
        details = "<p>%s in the session files, %s in the log for the window, %s.</p>" % (
            _count(_int(local), "request"), _num(logged), _count(mism, "token mismatch", "token mismatches"))
    if unlogged:
        rows = []
        for s in unlogged:
            project = str(s.get("project") or "")
            if len(project) > 40:  # the tail names the run; the head is the user's home folder
                project = "…" + project[-40:]
            session = str(s.get("session") or "?")
            rows.append([_ts(s.get("first")), "<code>%s</code>" % _e(project),
                         "<code>%s</code>" % _e(session[:8] + ("…" if len(session) > 8 else "")),
                         _e(AUTH_NAMES.get(s.get("auth"), s.get("auth"))),
                         _num(s.get("requests")), _num(s.get("tokens"))])
        details += "<p>Sessions in the team's session files but not in the log:</p>" + _table(
            ["First request (UTC)", "Project folder (end)", "Session", "Signed in with", "Requests", "Tokens"],
            rows, cls="wide", num_cols=(4, 5))
    return {
        "key": "coverage", "status": status, "short": short, "result": result,
        "means": "Compares the log with the Claude Code session files on the team's machine for the same "
                 "window, so a session that ran without sending its telemetry to the log shows up.",
        "limits": "It relies on session files on the team's own machine: it cannot see work on other "
                  "machines or sessions run with session files turned off, and only the team can re-run it.",
        "details": details,
    }


def _bill_totals(res):
    """Billed, background, unexplained and matched tokens, computed as `vawr check` prints them."""
    billed = _tokens(res.get("provider_tokens"))
    background = _tokens(res.get("background_tokens"))
    gaps = [g for g in res.get("gaps") or [] if isinstance(g, dict)]
    gap = sum(_tokens(g.get("tokens")) for g in gaps)
    return {"billed": billed, "background": background, "gaps": gaps, "gap": gap,
            "matched": billed - background - gap,
            "excess": [g for g in res.get("log_excess") or [] if isinstance(g, dict)]}


def _gap_span(gaps):
    if all(g.get("start") == g.get("end") for g in gaps):
        return _count(len(gaps), "minute")
    return _count(len(gaps), "stretch", "stretches") + " of time"


BILL_SOURCES = {
    "log": {"title": "Against the published log", "matched": "Matched by logged requests",
            "missing": "not accounted for by the log"},
    "files": {"title": "Against the session files on the team's machine",
              "matched": "Matched by the session files",
              "missing": "not accounted for by any session file on the team's machine"},
}


def _bill_detail(kind, res):
    t = _bill_totals(res)
    src = BILL_SOURCES[kind]
    rows = [["Billed by Anthropic", _num(t["billed"]), ""],
            [src["matched"], _num(t["matched"]), _pct(t["matched"], t["billed"])],
            ["Claude Code background requests%s" % (
                " (%s)" % _count(_int(res.get("logged_sessions")), "session")
                if res.get("logged_sessions") is not None else ""),
             _num(t["background"]), _pct(t["background"], t["billed"])],
            ["Unexplained", _num(t["gap"]), _pct(t["gap"], t["billed"])]]
    out = "<h4>%s</h4>" % src["title"] + _table(["", "Tokens", "Share of billed"], rows, cls="compact",
                                                  num_cols=(1, 2))
    facts = []
    if res.get("minutes_checked") is not None:
        facts.append("%s checked, %s with no difference either way" % (
            _count(_int(res.get("minutes_checked")), "minute"), _num(res.get("clean_minutes"))))
    facts.append("API key: %s" % ("<code>%s</code>" % _e(res["key_id"]) if res.get("key_id") else "ID not recorded"))
    if kind == "files" and res.get("local_api_key_requests") is not None:
        facts.append("%s from %s signed in with an API key compared; %s from Claude-account sessions "
                     "left out, since those never bill an API key" % (
                         _count(_int(res.get("local_api_key_requests")), "request"),
                         _count(_int(res.get("local_api_key_sessions")), "session"),
                         _count(_int(res.get("local_account_requests")), "request")))
    out += "<p>%s.</p>" % "; ".join(facts)
    if t["gaps"]:
        rows = []
        for g in t["gaps"]:
            span = _hhmm(g.get("start")) + ("" if g.get("start") == g.get("end") else "–" + _hhmm(g.get("end")))
            models = ", ".join(_e(m) for m in sorted(g.get("by_model") or {}))
            rows.append([span, _num(_tokens(g.get("tokens"))), models])
        date = _e(str(t["gaps"][0].get("start") or "")[:10])
        out += "<p>Unexplained billed usage by minute (%s, UTC):</p>" % date + _table(
            ["Minute", "Tokens", "Models billed"], rows, num_cols=(1,))
    if t["excess"]:
        out += ("<p>%s more in the %s than was billed to this key (another key, or usage records "
                "still arriving).</p>" % (
                    _cap(_count(len(t["excess"]), "stretch", "stretches") + " of time had"),
                    "log" if kind == "log" else "session files"))
    return out


def _bill(report, check, billcheck):
    cb = check.get("bill") if isinstance(check, dict) else None
    sources = []
    if isinstance(cb, dict) and "provider_tokens" in cb:
        sources.append(("log", cb))
    if isinstance(billcheck, dict) and "provider_tokens" in billcheck:
        sources.append(("files", billcheck))
    if not sources:
        if check is None and billcheck is None:
            return None
        why = cb.get("skipped") if isinstance(cb, dict) else None
        return {
            "key": "bill", "status": "skip", "short": "needs the organization's Admin key",
            "result": "Not run%s: it needs the organization's Admin key to read Anthropic's usage records."
                      % (" (%s)" % _e(why) if why else ""),
            "means": "Would compare Anthropic's per-minute billing records for one API key with the log.",
            "limits": "Without it, nothing here shows whether usage was billed that the log does not record.",
            "details": "",
        }
    kind, res = sources[0]
    t = _bill_totals(res)
    who = "API key <code>%s</code>" % _e(res["key_id"]) if res.get("key_id") else "the API key"
    if t["gaps"]:
        result = "Anthropic billed %s %s tokens in the window; %s of them (%s), in %s, are %s." % (
            who, _num(t["billed"]), _num(t["gap"]), _pct(t["gap"], t["billed"]), _gap_span(t["gaps"]),
            BILL_SOURCES[kind]["missing"])
        short = "%s billed tokens in %s are %s" % (_num(t["gap"]), _gap_span(t["gaps"]),
                                                   BILL_SOURCES[kind]["missing"])
    else:
        result = ("Anthropic billed %s %s tokens in the window, and every one is accounted for by the %s "
                  "plus Claude Code's background requests." % (
                      who, _num(t["billed"]), "log" if kind == "log" else "team's session files"))
        short = "every billed token is accounted for"
    if len(sources) > 1:
        t2 = _bill_totals(sources[1][1])
        if t2["gaps"]:
            result += (" Against the team's session files instead, %s tokens in %s are still unaccounted "
                       "for: usage no session file on that machine recorded." % (
                           _num(t2["gap"]), _gap_span(t2["gaps"])))
        else:
            result += " Against the team's session files instead, every billed token is accounted for."
    status = "fail" if any(_bill_totals(r)["gaps"] for _, r in sources) else "pass"
    if status == "fail" and not t["gaps"]:
        short = "billed tokens no session file on the team's machine accounts for"
    key_runs, sub_runs, all_runs = _modes(report)
    scope = ""
    if sub_runs:
        scope = (": %s of the %s in this report ran on a Claude subscription, which is not billed to "
                 "an API key, so this check cannot see %s" % (
                     _num(sub_runs), _count(all_runs, "run"), "it" if sub_runs == 1 else "them"))
    return {
        "key": "bill", "status": status, "short": short, "result": result,
        "means": "Compares Anthropic's per-minute billing records for one API key with what was recorded, "
                 "minute by minute. In our tests, headless Claude Code runs that inherit the Claude desktop "
                 "app's environment made one small background request that Claude Code records nowhere; the "
                 "check allows one such request per session.",
        "limits": "It covers only that one API key%s. Re-running it needs the organization's Admin key." % scope,
        "details": "".join(_bill_detail(k, r) for k, r in sources),
    }


def _sessions(check):
    ss = check.get("sessions") if isinstance(check, dict) else None
    if not isinstance(ss, dict):
        return None
    means = ("Anthropic's daily count of each API key's Claude Code sessions and their tokens by model. On a "
             "day the log fully covers, the two counts should be equal; a session kept out of the log shows up "
             "here even if it ran at the same time as logged work.")
    limits = ("Claude Code reports this count itself, so a session run with Claude Code's own telemetry "
              "switched off isn't counted; the bill check still sees it. Whole UTC days only, an hour or more "
              "behind, and only usage on Anthropic's API (not a Claude subscription, Bedrock or Vertex).")
    if ss.get("error") or not ss.get("days"):
        return {"key": "sessions", "status": "skip", "short": "could not run",
                "result": "Not run: %s." % _e(ss.get("error") or "no days in the window"),
                "means": means, "limits": limits, "details": ""}
    rows = ss["days"]
    failed = [r for r in rows if r.get("status") == "fail"]
    matched = [r for r in rows if r.get("status") in ("pass", "pass_so_far")]
    unconfirmed = unconfirmed_text(ss)
    if unconfirmed and not failed:
        status = "skip"
        result = _e(unconfirmed)
        short = ("Anthropic counted fewer sessions than the log has" if ss.get("uncounted_days") else
                 "the log covers only part of a day")
    elif failed:
        status = "fail"
        missing = sum(max(0, _int(r.get("anthropic_sessions")) - _int(r.get("log_sessions"))) for r in failed)
        result = ("On %s, Anthropic counted Claude Code sessions or tokens on this key that the log does not "
                  "have%s." % (", ".join(_e(r["day"]) for r in failed),
                               " (%s missing)" % _count(missing, "session") if missing else ""))
        short = "Anthropic counted sessions the log does not have" if missing else \
            "Anthropic's token count differs from the log's"
    elif matched:
        status = "pass"
        result = "On %s, the log's sessions and tokens equal Anthropic's count%s." % (
            ", ".join(_e(r["day"]) + (" (so far)" if r["status"] == "pass_so_far" else "") for r in matched),
            "" if len(matched) == len(rows) else "; the other days could not be compared (see details)")
        short = "the log's sessions equal Anthropic's count"
    else:
        status = "skip"
        result = "No whole day the log covers could be compared yet (see details)."
        short = "no whole day to compare yet"
    trs = []
    for r in rows:
        trs.append([_e(r["day"]), _e(r["status"].replace("_", " ")), _num(r.get("anthropic_sessions")),
                    _num(r.get("log_sessions")),
                    _e(", ".join("%s %+d" % (m, v) for m, v in sorted((r.get("token_difference") or {}).items()))
                       or "none")])
    details = _table(["Day", "Result", "Anthropic's sessions", "Log's sessions", "Tokens, Anthropic minus log"],
                     trs, num_cols=(2, 3))
    work = {}
    for r in rows:
        for k, v in (r.get("work") or {}).items():
            work[k] = work.get(k, 0) + _int(v)
    if any(work.values()):
        details += ("<p>Anthropic's records also count, for these days: %s lines added, %s removed, %s and %s "
                    "made through Claude Code.</p>" % (
                        _num(work.get("lines_added")), _num(work.get("lines_removed")),
                        _count(work.get("commits", 0), "commit"), _count(work.get("pull_requests", 0),
                                                                          "pull request")))
    return {"key": "sessions", "status": status, "short": short, "result": result, "means": means,
            "limits": limits, "details": details, "ran": True}


def _continuity(check):
    c = check.get("continuity") if isinstance(check, dict) else None
    if not isinstance(c, dict):
        return None
    means = ("Each report you receive commits to the log as it stood then. This one's log must contain "
             "every earlier report's head hash from the same log, so history can't be rewritten between reports.")
    limits = "It compares only with reports you received before; the first report from a log has nothing to compare."
    status = {True: "pass", False: "fail", None: "skip"}[c.get("ok")]
    return {"key": "continuity", "status": status, "short": _e(c.get("short") or ""),
            "result": _e(c.get("note") or ""), "means": means, "limits": limits, "details": ""}


VERDICT_TEXT = {
    "contradicted": "the model sees a different purpose",
    "unconfirmed": "the model sees generic work with no safety or capabilities purpose",
}


def _category(report, categories):
    if not isinstance(categories, dict):
        return None
    rows = [r for r in categories.get("rows") or [] if isinstance(r, dict)]
    summary = categories.get("summary") if isinstance(categories.get("summary"), dict) else {}
    model = summary.get("model")
    run_tok = _run_tokens(report)
    if run_tok:
        checked = [r for r in rows if r.get("run_id") in run_tok]
    else:
        checked = rows
    outside = len(rows) - len(checked)
    means = ("A separate model%s read each run's task and code change, without seeing its label, and "
             "picked a category from written definitions; a run is flagged when its pick differs from "
             "the label." % (" (%s)" % _e(model) if model else ""))
    limits = ("A flag is a disagreement, not proof the label is wrong: the model can misread generic code, "
              "and the check uses each run's task and change as the team supplied them, which nothing "
              "ties to the log.")
    if not checked:
        return {"key": "category", "status": "skip", "short": "no runs from this report were checked",
                "result": "Not run on this report: the category check results have no runs from this "
                          "report's log%s." % (" (%s for other runs)" % _count(outside, "row") if outside else ""),
                "means": means, "limits": limits, "details": ""}
    flagged = [r for r in checked if r.get("flagged", r.get("classified") != r.get("declared"))]
    contradicted = sum(1 for r in flagged if r.get("verdict") == "contradicted")
    unconfirmed = sum(1 for r in flagged if r.get("verdict") == "unconfirmed")
    total_tokens = sum(_cat_tokens(c) for c in _categories(report))
    if not flagged:
        status, short = "pass", "every label confirmed"
        result = "The reviewing model agreed with all %s." % _count(len(checked), "run label")
    else:
        status = "fail"
        short = "the reviewing model disagreed with %s of %s" % (_num(len(flagged)),
                                                                 _count(len(checked), "run label"))
        result = "The reviewing model disagreed with %s of %s" % (_num(len(flagged)),
                                                                _count(len(checked), "run label"))
        ftok = sum(run_tok.get(r.get("run_id"), 0) for r in flagged)
        if run_tok and total_tokens:
            result += " (runs holding %s tokens, %s of the total)" % (_num(ftok), _pct(ftok, total_tokens))
        how = []
        if contradicted:
            how.append("%s as a different category" % _num(contradicted))
        if unconfirmed:
            how.append("%s as generic work with no safety or capabilities purpose" % _num(unconfirmed))
        result += (": it read " + " and ".join(how) + ".") if how else "."
    details = ""
    if flagged:
        items = []
        for r in flagged:
            v = r.get("verdict")
            items.append(
                '<li><p><strong>%s</strong> <code class="id">%s</code><br>Label <strong>%s</strong>; model picked '
                '<strong>%s</strong> (%s%s)</p><blockquote>%s</blockquote></li>' % (
                    _e(r.get("task") or "run"), _e(r.get("run_id")), _e(r.get("declared")),
                    _e(r.get("classified")), _e(v), ": " + VERDICT_TEXT[v] if v in VERDICT_TEXT else "",
                    _e(r.get("reason") or "(no reason given)")))
        details += "<p>Flagged runs, with the model's reason in its own words:</p><ul class=\"flags\">%s</ul>" % "".join(items)
    # Token shares with the model's picks in place of the labels, when every run was checked.
    if flagged and run_tok and len(checked) == len(run_tok) and total_tokens:
        picked = {}
        for r in checked:
            picked[r.get("classified")] = picked.get(r.get("classified"), 0) + run_tok.get(r.get("run_id"), 0)
        labelled = {c.get("category"): _cat_tokens(c) for c in _categories(report)}
        names = list(labelled) + sorted(str(n) for n in picked if n not in labelled)
        parts = ["%s %s (labels: %s)" % (_e(n), _pct(picked.get(n, 0), total_tokens),
                                         _pct(labelled.get(n, 0), total_tokens)) for n in names]
        details += "<p>Token shares if the model's picks replaced the labels: %s.</p>" % "; ".join(parts)
    notes = []
    if run_tok and len(checked) < len(run_tok):
        notes.append("%s of the %s in this report %s no category check." % (
            _num(len(run_tok) - len(checked)), _count(len(run_tok), "run"),
            "has" if len(run_tok) - len(checked) == 1 else "have"))
    if outside:
        notes.append("The category check results also hold %s for runs not in this report; they are "
                     "left out here." % _count(outside, "row"))
    # The validation scores need every run's correct category; prefer the runs
    # held out while the prompt was written.
    known = rows and all(r.get("true_category") is not None and r.get("true_category") == r.get("declared")
                         for r in rows)
    for key, which in (("held_out_runs", "runs not used while writing its prompt"),
                       ("all", "runs whose correct categories were known")):
        part = summary.get(key) if isinstance(summary.get(key), dict) else {}
        false_flags = _rate(part.get("true_tags_flagged"), "correctly labelled runs")
        relabels = _rate(part.get("relabels_caught"), "deliberate relabels")
        if known and false_flags and relabels:
            notes.append("How far to trust a flag: in the tool's own validation on %s %s, the model wrongly "
                         "flagged %s and caught %s%s." % (
                             _num(part.get("runs")), which, false_flags, relabels,
                             "; prompt version <code>%s</code>" % _e(summary["prompt_sha"])
                             if summary.get("prompt_sha") else ""))
            break
    details += "".join("<p>%s</p>" % n for n in notes)
    return {"key": "category", "status": status, "short": short, "result": result,
            "means": means, "limits": limits, "details": details}


CLAIM_VALIDATION = (
    ("false_done_caught", "False “done” claims planted in real summaries (code untouched), caught"),
    ("fake_blocker_caught", "Made-up blockers (the named thing exists), caught"),
    ("true_blocker_wrongly_flagged", "Real blockers (the named thing is missing), wrongly flagged"),
    ("negations_with_spurious_claims", "Denials (“I didn't run the tests”) read as claims"),
)


def _claims(report, claims):
    cats = _categories(report)
    rep_claims = sum(_int(c.get("claims")) for c in cats)
    rep_held = sum(_int(c.get("claims_held")) for c in cats)
    real = claims.get("real_runs_flagged") if isinstance(claims, dict) else None
    if not rep_claims and not isinstance(claims, dict):
        return None
    _, _, all_runs = _modes(report)
    means = ("Pulls “done”, “tests pass”, “added tests” and “blocked by X” "
             "claims from each run's final message and checks them against the code change, a fresh run of "
             "the task's test, and whether the named blocker is really missing.")
    limits = ("It checks only those four kinds of claim, and a passing test shows the task's own test "
              "passes, not that the work is good.")
    details = ""
    if rep_claims:
        failed = rep_claims - rep_held
        status = "fail" if failed else "pass"
        result = "%s of %s made by the agents held up when checked." % (_num(rep_held), _count(rep_claims, "claim"))
        short = ("%s of %s did not hold up" % (_num(failed), _count(rep_claims, "claim"))
                 if failed else "every claim held up")
        rows = [[_e(c.get("category")), _num(c.get("claims_held")), _num(c.get("claims"))]
                for c in cats if _int(c.get("claims"))]
        details += "<p>Claims by category:</p>" + _table(["Category", "Held up", "Checked"], rows,
                                                         num_cols=(1, 2))
    elif isinstance(real, dict) and _int(real.get("n")):
        k, n = _int(real.get("k")), real["n"]
        status = "fail" if k else "pass"
        if k:
            result = "%s of %s checked made a claim about its own work that did not hold up." % (
                _num(k), _count(n, "agent run"))
            short = "%s of %s made a claim that did not hold up" % (_num(k), _count(n, "run"))
        else:
            result = "Every claim held up in the %s checked." % _count(n, "agent run")
            short = "every claim held up"
        if all_runs and n != all_runs:
            limits += (" The claims results do not say which runs they cover (%s; this report has %s), "
                       "so they may include runs outside this report." % (_num(n), _num(all_runs)))
    else:
        return {"key": "claims", "status": "skip", "short": "no results for real runs",
                "result": "Not run on real runs: the claims results hold only the checker's own validation.",
                "means": means, "limits": limits, "details": _claim_validation(claims)}
    details += _claim_validation(claims)
    return {"key": "claims", "status": status, "short": short, "result": result,
            "means": means, "limits": limits, "details": details}


def _claim_validation(claims):
    if not isinstance(claims, dict):
        return ""
    rows = [[label, _rate(claims.get(key))] for key, label in CLAIM_VALIDATION if _rate(claims.get(key))]
    if not rows:
        return ""
    out = ("<p>How far to trust it: the tool's own validation, on planted cases.</p>"
           + _table(["Case", "Result"], rows))
    if claims.get("extraction_missed") is not None:
        out += "<p>Planted cases where no relevant claim was extracted at all: %s.</p>" % _num(
            claims.get("extraction_missed"))
    return out


# ---------- sections ----------

def _level_line(check, report):
    lv = check.get("level") if isinstance(check, dict) else None
    if lv not in LEVEL_TEXT:
        return ""
    head, text = LEVEL_TEXT[lv]
    b = report.get("billing") if isinstance(report.get("billing"), dict) else None
    split = ""
    if b and sum(_int(v) for v in b.values()):
        total = sum(_int(v) for v in b.values())
        parts = []
        if _int(b.get("api_key")):
            parts.append("%s on an API key" % _pct(_int(b["api_key"]), total))
        if _int(b.get("subscription")):
            parts.append("%s on a Claude subscription (Anthropic offers no records to check it against)"
                         % _pct(_int(b["subscription"]), total))
        if _int(b.get("unknown")):
            parts.append("%s billed in a way the log does not show" % _pct(_int(b["unknown"]), total))
        split = " Of the tokens in this report: %s." % "; ".join(parts)
    who = check.get("checked_by") if isinstance(check, dict) else None
    by = " Checks run by %s." % _e(who) if who else ""
    return '<p class="level"><strong>Level: %s.</strong> %s%s%s</p>' % (_e(head), _e(text), split, by)


def _verdict(checks, warnings, level=""):
    failed = [c for c in checks if c["status"] == "fail"]
    passed = [c for c in checks if c["status"] == "pass"]
    skipped = [c for c in checks if c["status"] == "skip"]
    missing = [CHECK_TITLES[k].lower() for k in CHECK_ORDER  # continuity exists only for a recipient
               if k not in {c["key"] for c in checks} and k != "continuity"]
    ran = len(failed) + len(passed)

    def names(cs):
        ns = [CHECK_TITLES[c["key"]].lower() for c in cs]
        return ns[0] if len(ns) == 1 else ", ".join(ns[:-1]) + " and " + ns[-1]

    if not checks:
        head, cls = "No checks were included with this report", "attention"
    elif failed:
        head = "%s of %s %s attention: %s" % (
            _num(len(failed)), _count(ran, "check"), "needs" if len(failed) == 1 else "need", names(failed))
        cls = "attention"
    elif not skipped and len(passed) == 1:
        head, cls = "The %s check passed" % names(passed), "ok"
    elif not skipped:
        head, cls = "All %s checks passed" % _num(len(passed)), "ok"
    else:
        head = ("All checks that ran passed (%s)" % names(passed)) if passed else "No check could be run"
        cls = "ok" if passed else "attention"
    if warnings:
        cls = "attention"
    items = "".join('<li><strong>%s:</strong> %s.</li>' % (CHECK_TITLES[c["key"]], c["short"]) for c in failed)
    items += "".join('<li><strong>Warning:</strong> %s</li>' % w for w in warnings)
    tail = []
    if failed and passed:
        tail.append("Passed: %s." % names(passed))
    not_run = [c for c in skipped if not c.get("ran")]
    unconfirmed = [c for c in skipped if c.get("ran")]
    if not_run:
        tail.append("Not run: %s." % "; ".join(
            "%s (%s)" % (CHECK_TITLES[c["key"]].lower(), c["short"]) for c in not_run))
    if unconfirmed:
        tail.append("Ran but could not confirm: %s." % "; ".join(
            "%s (%s)" % (CHECK_TITLES[c["key"]].lower(), c["short"]) for c in unconfirmed))
    if missing:
        tail.append("Not included in this report: %s." % ", ".join(missing))
    return ('<section class="verdict %s" aria-labelledby="verdict-head"><p class="headline" id="verdict-head">'
            '%s</p>%s%s%s</section>' % (cls, head, level, "<ul>%s</ul>" % items if items else "",
                                        '<p class="tail">%s</p>' % " ".join(tail) if tail else ""))


def _usage(report):
    cats = _categories(report)
    if not cats:
        return ('<section aria-labelledby="usage"><h2 id="usage">Usage by category</h2>'
                '<p>The report lists no usage.</p></section>')
    total_tok = sum(_cat_tokens(c) for c in cats)
    total_cost = sum(_float(c.get("cost_usd")) for c in cats)
    total_runs = sum(_int(c.get("runs")) for c in cats)
    total_reqs = sum(_int(c.get("requests")) for c in cats)
    with_claims = any(_int(c.get("claims")) for c in cats)
    with_outcomes = any(_int(c.get("outcomes")) for c in cats)
    head = ["Category", "Share of tokens", "Tokens", "Est. cost", "Runs", "Requests"]
    if with_claims:
        head.append("Claims held up")
    if with_outcomes:
        head.append("Work passing its tests")
    th = "".join('<th scope="col"%s>%s</th>' % (' class="num"' if i >= 2 else "", h) for i, h in enumerate(head))
    body = []
    for c in cats:
        tok = _cat_tokens(c)
        share = c.get("token_share")
        if not isinstance(share, (int, float)):
            share = tok / total_tok if total_tok else 0
        cells = ['<th scope="row">%s</th>' % _e(c.get("category")),
                 '<td class="share"><span class="pct">%.1f%%</span>%s</td>' % (100.0 * share, _bar(share)),
                 '<td class="num">%s</td>' % _num(tok), '<td class="num">%s</td>' % _usd(c.get("cost_usd")),
                 '<td class="num">%s</td>' % _num(c.get("runs")), '<td class="num">%s</td>' % _num(c.get("requests"))]
        if with_claims:
            cells.append('<td class="num">%s</td>' % (
                "%s of %s" % (_num(c.get("claims_held")), _num(c.get("claims"))) if _int(c.get("claims")) else "none"))
        if with_outcomes:
            cells.append('<td class="num">%s</td>' % (
                "%s of %s" % (_num(c.get("outcomes_passed")), _num(c.get("outcomes"))) if _int(c.get("outcomes"))
                else "none"))
        body.append("<tr>%s</tr>" % "".join(cells))
    foot = ['<th scope="row">Total</th>', "<td></td>", '<td class="num">%s</td>' % _num(total_tok),
            '<td class="num">%s</td>' % _usd(total_cost), '<td class="num">%s</td>' % _num(total_runs),
            '<td class="num">%s</td>' % _num(total_reqs)]
    if with_claims:
        foot.append("<td></td>")
    if with_outcomes:
        foot.append("<td></td>")
    table = ('<div class="table-wrap"><table class="usage wide"><caption class="sr">Tokens, estimated cost, runs '
             'and requests by category</caption><thead><tr>%s</tr></thead><tbody>%s</tbody>'
             '<tfoot><tr>%s</tr></tfoot></table></div>' % (th, "".join(body), "".join(foot)))
    lead = "<p>%s tokens across %s and %s, by the category each run was labelled with when it started.</p>" % (
        _num(total_tok), _count(total_runs, "run"), _count(total_reqs, "request"))
    note = '<p class="note">%s</p>' % _e(report["note"]) if report.get("note") else ""
    by_type = [[_e(c.get("category"))] + [_num((c.get("tokens") or {}).get(k)) for k, _ in TOKEN_TYPES]
               for c in cats if isinstance(c.get("tokens"), dict)]
    extra = ""
    if by_type:
        extra += ("<details><summary>Tokens by type</summary><p>Cache reads re-use earlier context and are "
                  "billed at a lower rate than input tokens.</p>%s</details>" % _table(
                      ["Category"] + [label for _, label in TOKEN_TYPES], by_type, num_cols=(1, 2, 3, 4)))
    runs = _runs(report)
    if runs:
        rows = [["<code class=\"id\">%s</code>" % _e(r.get("run_id")), _e(r.get("category")),
                 _e(MODE_NAMES.get(r.get("mode"), r.get("mode"))),
                 _num(_tokens(r.get("tokens"))), _usd(r.get("cost_usd")), _num(r.get("requests"))]
                for r in runs]
        extra += "<details><summary>All %s</summary>%s</details>" % (_count(len(runs), "run"), _table(
            ["Run", "Category", "Billed to", "Tokens", "Est. cost", "Requests"], rows, cls="runs wide",
            num_cols=(3, 4, 5)))
    projects = [p for p in report.get("projects") or [] if isinstance(p, dict)]
    proj = ""
    if projects:
        rows = [[_e(p.get("project")), _e(p.get("category")), _num(p.get("runs")),
                 _num(p.get("total_tokens")), _usd(p.get("cost_usd"))] for p in projects]
        proj = "<h3>By project</h3>%s" % _table(["Project", "Category", "Sessions", "Tokens", "Est. cost"],
                                                 rows, num_cols=(2, 3, 4))
    return ('<section aria-labelledby="usage"><h2 id="usage">Usage by category</h2>%s%s%s%s%s</section>'
            % (lead, table, proj, note, extra))


def _checks_section(checks):
    if not checks:
        return ""
    items = []
    for c in checks:
        details = ("<details><summary>Details</summary>%s</details>" % c["details"]) if c["details"] else ""
        items.append(
            '<li class="check" id="check-%s"><h3><span class="badge %s">%s</span> %s</h3>'
            '<p class="result">%s</p><p class="means"><strong>What it shows:</strong> %s</p>'
            '<p class="limits"><strong>What it does not show:</strong> %s</p>%s</li>' % (
                c["key"], c["status"], STATUS_TEXT[c["status"]], CHECK_TITLES[c["key"]],
                c["result"], c["means"], c["limits"], details))
    return ('<section aria-labelledby="checks"><h2 id="checks">Checks</h2><ul class="checks">%s</ul></section>'
            % "".join(items))


def _verify(report, check, billcheck):
    log = report.get("log") or {}
    path = log.get("path") or "events.jsonl"
    window = None
    for src in (check, billcheck):
        if isinstance(src, dict) and isinstance(src.get("window"), (list, tuple)) and len(src["window"]) == 2:
            window = src["window"]
            break
    q = shlex.quote(str(path))
    if window and all(window):
        since, until = shlex.quote(str(window[0])), shlex.quote(str(window[1]))
    else:
        since, until = "<start>", "<end>"
    commands = "\n".join([  # continuation lines keep each line short enough for a phone or paper
        "vawr status --log %s" % q,
        "vawr verify-report report.json --log %s" % q,
        "vawr check --no-coverage --since %s \\\n    --until %s \\\n    --log %s" % (since, until, q),
    ])
    head = log.get("head")
    facts = [("Log file", "<code>%s</code>" % _e(path)),
             ("Head hash", '<code class="hash">%s</code>' % _e(head) if head else "none (empty log)"),
             ("Entries", _num(log.get("entries")))]
    wt = _window_text(window)
    facts.append(("Window", wt if wt else "not given (no check results included)"))
    dl = "".join("<dt>%s</dt><dd>%s</dd>" % f for f in facts)
    steps = ["<li><code>vawr status</code> should show %s and the chain intact. The last line of the log "
             "carries the head hash above in its <code>hash</code> field.</li>" % _count(
                 _int(log.get("entries")), "entry", "entries"),
             "<li><code>vawr verify-report</code> takes the report's data file (<code>report.json</code>, "
             "from <code>vawr report --out</code>), checks that its head hash%s is an entry of the log, and "
             "recounts its totals from the log; any edited figure fails.</li>" % (
                 " (<code>%s</code>)" % _e(str(head)[:16]) if head else ""),
             "<li><code>vawr check --no-coverage</code> re-runs the chain check, and with the account's "
             "Admin key the bill check, on any machine. If you hold the account (for example, you issued "
             "the API key), nothing here rests on the team's word. Coverage reads the team's own session "
             "files, so only the team can re-run it.</li>"]
    if since == "<start>":
        steps.append("<li>Replace <code>&lt;start&gt;</code> and <code>&lt;end&gt;</code> with the UTC "
                     "times the report covers.</li>")
    return ('<section class="verify" aria-labelledby="verify"><h2 id="verify">How to verify this report</h2>'
            '<dl>%s</dl><p>If this came as a vawr bundle (a <code>.zip</code>), one command checks everything '
            'below, and with your own Admin key also checks it against Anthropic\'s records for the key: '
            '<code>vawr receive &lt;file&gt;.zip</code>. It keeps the head hash, so the next report from the '
            'same log must extend this one.</p><p>Or, step by step, with the published log file and the tool '
            'installed (or <code>python3 -m vawr</code> from a copy of it):</p><pre><code>%s</code></pre>'
            '<ul>%s</ul></section>' % (dl, _e(commands), "".join(steps)))


def _warnings(report, check):
    """Disagreements between inputs that a reader should see before the figures."""
    out = []
    log = report.get("log") or {}
    ch = check.get("chain") if isinstance(check, dict) else None
    if isinstance(ch, dict) and log.get("head") and ch.get("head") and (
            ch["head"] != log["head"] or ch.get("entries") != log.get("entries")):
        out.append("the checks ran on a different version of the log (%s, head <code>%s</code>) than the "
                   "usage figures (%s, head <code>%s</code>)." % (
                       _count(_int(ch.get("entries")), "entry", "entries"), _e(str(ch["head"])[:16]),
                       _count(_int(log.get("entries")), "entry", "entries"), _e(str(log["head"])[:16])))
    return out


CSS = """
:root{color-scheme:light dark;
--bg:#fcfcfb;--fg:#1c1e22;--muted:#565c68;--rule:#d9dce2;--panel:#f3f4f6;--code:#eceef1;
--bar:#36628e;--track:#dde2e8;
--pass:#1b6a3d;--pass-bg:#e2f1e7;--fail:#a2341d;--fail-bg:#f9e6e1;--skip:#565c68;--skip-bg:#e9ebee}
@media (prefers-color-scheme:dark){:root{
--bg:#15171b;--fg:#e5e7ea;--muted:#a1a7b2;--rule:#31353c;--panel:#1e2126;--code:#272b31;
--bar:#82abd8;--track:#30353d;
--pass:#86d3a5;--pass-bg:#173424;--fail:#f1a491;--fail-bg:#3c1e17;--skip:#a1a7b2;--skip-bg:#2a2e35}}
@media print{:root{
--bg:#fff;--fg:#000;--muted:#3d424b;--rule:#c4c8cf;--panel:#fff;--code:#f2f3f5;
--bar:#36628e;--track:#dde2e8;
--pass:#1b6a3d;--pass-bg:#fff;--fail:#a2341d;--fail-bg:#fff;--skip:#3d424b;--skip-bg:#fff}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
main{max-width:50rem;margin:0 auto;padding:2rem 1rem 3rem}
h1{font-size:1.6rem;line-height:1.25;margin:0 0 .4rem;letter-spacing:-.01em}
h2{font-size:1.15rem;margin:2.25rem 0 .8rem;padding-bottom:.35rem;border-bottom:1px solid var(--rule)}
h3{font-size:1rem;margin:0 0 .3rem;display:flex;align-items:center;gap:.6rem}
h4{font-size:.92rem;margin:1rem 0 .4rem}
p{margin:.45rem 0}
.meta{color:var(--muted);font-size:.9rem;margin:0 0 1.4rem}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;font-size:.85em}
code.hash,code.id{word-break:break-all}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.verdict{background:var(--panel);border:1px solid var(--rule);border-left:6px solid var(--pass);
border-radius:6px;padding:.9rem 1.1rem}
.verdict.attention{border-left-color:var(--fail)}
.verdict .headline{font-size:1.15rem;font-weight:650;margin:0}
.verdict ul{margin:.5rem 0 0;padding-left:1.2rem}
.verdict li{margin:.2rem 0}
.verdict .tail{color:var(--muted);font-size:.9rem;margin:.5rem 0 0}
.verdict .level{margin:.5rem 0 0;font-size:.92rem}
.table-wrap{overflow-x:auto;margin:.5rem 0}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{padding:.4rem .5rem;border-bottom:1px solid var(--rule);text-align:left;vertical-align:top}
thead th{font-size:.8rem;color:var(--muted);font-weight:600;border-bottom-color:var(--fg)}
tfoot th,tfoot td{font-weight:600;border-bottom:none;border-top:1px solid var(--fg)}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
table.compact{width:auto;min-width:60%}
table.usage td.share{width:34%;min-width:9rem}
.share .pct{display:inline-block;min-width:3.4rem;font-variant-numeric:tabular-nums}
svg.bar{display:inline-block;vertical-align:middle;width:calc(100% - 3.6rem);height:.6rem}
svg.bar .track{fill:var(--track)}
svg.bar .fill{fill:var(--bar)}
.note{color:var(--muted);font-size:.88rem}
.checks{list-style:none;margin:0;padding:0}
.check{border-top:1px solid var(--rule);padding:.9rem 0}
.check:first-child{border-top:none;padding-top:.2rem}
.check .result{font-weight:500}
.check .means,.check .limits{color:var(--muted);font-size:.9rem}
.badge{display:inline-block;min-width:4.4rem;text-align:center;font-size:.75rem;font-weight:700;
letter-spacing:.03em;text-transform:uppercase;padding:.12rem .5rem;border-radius:999px;border:1px solid}
.badge.pass{color:var(--pass);background:var(--pass-bg)}
.badge.fail{color:var(--fail);background:var(--fail-bg)}
.badge.skip{color:var(--skip);background:var(--skip-bg)}
details{margin:.55rem 0 0;border:1px solid var(--rule);border-radius:6px;padding:.4rem .8rem}
details[open]{padding-bottom:.7rem}
summary{cursor:pointer;font-weight:600;font-size:.9rem}
ul.flags{list-style:none;padding:0;margin:.3rem 0}
ul.flags li{border-top:1px solid var(--rule);padding:.5rem 0}
blockquote{margin:.3rem 0 0;padding:.1rem 0 .1rem .8rem;border-left:3px solid var(--rule);color:var(--muted);
font-size:.9rem}
.verify{background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:.1rem 1.1rem .9rem;
margin-top:2.25rem}
.verify h2{margin-top:1rem}
.verify dl{display:grid;grid-template-columns:max-content 1fr;gap:.3rem 1rem;margin:.5rem 0 1rem}
.verify dt{font-weight:600}
.verify dd{margin:0;min-width:0}
pre{background:var(--code);border-radius:4px;padding:.7rem .8rem;overflow-x:auto;white-space:pre;margin:.5rem 0}
footer{color:var(--muted);font-size:.85rem;margin-top:2.5rem;padding-top:.8rem;border-top:1px solid var(--rule)}
@media (max-width:540px){
body{font-size:14px}
table.wide{min-width:34rem}
table.runs td:first-child{min-width:14rem}
main{padding:1.25rem 1rem 2rem}
.verify dl{grid-template-columns:1fr;gap:0}
.verify dd{margin-bottom:.4rem}}
@page{margin:15mm}
@media print{
body{font-size:9.5pt}
main{max-width:none;padding:0}
a{color:inherit}
details{border:none;padding:0}
details::details-content{content-visibility:visible;display:block}
summary{list-style:none;cursor:auto}
summary::-webkit-details-marker{display:none}
.check,tr,.verdict,ul.flags li,.verify dl{break-inside:avoid}
h2,h3,h4{break-after:avoid}
.table-wrap{overflow:visible}
pre{white-space:pre-wrap;word-break:break-all}}
"""


def render(report, check=None, billcheck=None, categories=None, claims=None, title=None):
    """The full HTML document as a string. Only `report` is required."""
    report = report if isinstance(report, dict) else {}
    title = title or "Agent usage report"
    checks = [c for c in (_chain(report, check), _coverage(check), _bill(report, check, billcheck),
                          _sessions(check), _continuity(check), _category(report, categories),
                          _claims(report, claims)) if c]
    warnings = _warnings(report, check)
    log = report.get("log") or {}
    meta = []
    if log.get("path"):
        meta.append("Log <code>%s</code>" % _e(log["path"]))
    if log.get("entries") is not None:
        meta.append(_count(_int(log.get("entries")), "entry", "entries"))
    for src in (check, billcheck):
        wt = _window_text(src.get("window")) if isinstance(src, dict) else None
        if wt:
            meta.append("checks cover " + wt)
            break
    inputs = [name for name, v in (("allocation report", report), ("check", check), ("bill check", billcheck),
                                   ("category check", categories), ("claims summary", claims)) if v]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return "".join([
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<meta name=\"generator\" content=\"vawr %s\">" % _e(__version__),
        "<title>%s</title><style>%s</style></head><body><main>" % (_e(title), CSS),
        "<header><h1>%s</h1><p class=\"meta\">%s</p></header>" % (_e(title), " · ".join(meta)),
        _verdict(checks, warnings, _level_line(check, report)),
        _usage(report),
        _checks_section(checks),
        _verify(report, check, billcheck),
        "<footer><p>Generated %s by vawr %s from: %s. Every figure on this page comes from those files; "
        "shares and totals are computed from them.</p></footer>" % (
            generated, _e(__version__), _e(", ".join(inputs))),
        "</main></body></html>\n",
    ])
