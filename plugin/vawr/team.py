"""`vawr team`: an organization admin checks everyone's bundles at once against
the organization's own Anthropic records.

For each API key with usage in the window, it answers: did any bundle cover it,
is everything billed to it accounted for by the bundles' logs (per minute), and
does Anthropic's daily count of Claude Code sessions on it equal the logs' (see
daily.py)? Keys that billed usage but no bundle covers are listed with their
tokens: that is usage nobody reported.
"""
import tempfile
from datetime import datetime

from . import auditor, bundle, daily, usage_api
from .logdata import api_requests
from .sessions import parse_ts


def _parse(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def run(bundle_paths, admin_key, start=None, end=None, ledger=bundle.RECEIVED, record=True, sessions=True,
        org_minutes=None, keys=None, fetch=None, now=None):
    """`org_minutes`, `keys` and `fetch` replace the Admin API calls in tests."""
    work = tempfile.mkdtemp(prefix="vawr-team-")
    members = []
    known = bundle._ledger(ledger)  # before this run, so bundles in it don't count as each other's history
    siblings = set()
    for path in bundle_paths:
        try:
            siblings.add(bundle.bundle_log_id(path))
        except Exception:
            pass
    for i, path in enumerate(bundle_paths):
        out = bundle.receive(path, admin_key=None, ledger=ledger, record=record, known=known, siblings=siblings,
                             workdir=tempfile.mkdtemp(prefix="m%d-" % i, dir=work))
        m = out["manifest"]
        w = m.get("window") or [None, None]
        members.append({"bundle": path, "title": m.get("title"), "key_id": m.get("key_id"),
                        "only_projects": m.get("only_projects"), "window": [_parse(w[0]), _parse(w[1])],
                        "log": out["files"]["log.jsonl"], "chain_ok": out["chain"]["ok"],
                        "report_ok": out["report"]["ok"], "continuity": out["continuity"]})
    starts = [mb["window"][0] for mb in members if mb["window"][0]]
    ends = [mb["window"][1] for mb in members if mb["window"][1]]
    start = start or (min(starts) if starts else None)
    end = end or (max(ends) if ends else None)
    if not (start and end):
        raise ValueError("no time window: give --since and --until, or bundles that carry one")

    if org_minutes is None:
        org_minutes = usage_api.org_minute_usage(admin_key, start, end)
    if keys is None:
        keys = usage_api.api_keys(admin_key)
    names = {k.get("id"): k.get("name") for k in keys}

    rows = []
    key_ids = sorted({k for k in org_minutes if k} | {mb["key_id"] for mb in members if mb["key_id"]},
                     key=lambda k: -_total(org_minutes.get(k)))
    for kid in key_ids:
        mine = [mb for mb in members if mb["key_id"] == kid]
        minutes = {parse_ts(t): v for t, v in (org_minutes.get(kid) or {}).items()}
        billed = _total(org_minutes.get(kid))
        row = {"key_id": kid, "key_name": names.get(kid), "billed_tokens": billed,
               "bundles": [mb["bundle"] for mb in mine], "bill": None, "sessions": None}
        if not mine:
            row["status"] = "no report"
            rows.append(row)
            continue
        reqs = []
        for mb in mine:
            ws, we = mb["window"]
            for r in api_requests(mb["log"]):
                t = r.get("time")
                if (t and r.get("mode") in daily.API_KEY_MODES and ws <= parse_ts(t) < we
                        and (not mb["only_projects"] or r.get("project") in mb["only_projects"])):
                    reqs.append(dict(r, mode="api_key"))
        row["bill"] = auditor.check_provider(reqs, start, end, key_mode="api_key", provider_minutes=minutes)
        if sessions and sum(1 for k in keys if k.get("name") == names.get(kid)) > 1:
            row["sessions"] = {"ok": None, "error": "more than one key is named %r; Anthropic's Claude Code "
                               "analytics names keys, not IDs, so it can't tell them apart" % names.get(kid)}
        elif sessions:
            try:
                row["sessions"] = daily.check(admin_key, kid, start, end,
                                              [(mb["log"], mb["only_projects"]) for mb in mine],
                                              key_name=names.get(kid), fetch=fetch, now=now)
            except Exception as exc:
                row["sessions"] = {"ok": None, "error": "%s: %s" % (type(exc).__name__, exc)}
        broken = [mb for mb in mine if not mb["chain_ok"] or not mb["report_ok"] or mb["continuity"]["ok"] is False]
        row["status"] = ("fail" if broken or row["bill"]["gaps"] or (row["sessions"] or {}).get("ok") is False
                         else "pass")
        rows.append(row)
    total = sum(r["billed_tokens"] for r in rows)
    reported = sum(r["billed_tokens"] - _gap(r) for r in rows if r["bundles"])
    return {"window": [start.isoformat(), end.isoformat()], "members": [
                {k: (v if k != "window" else [x.isoformat() if x else None for x in v]) for k, v in mb.items()
                 if k != "log"} for mb in members],
            "keys": rows, "billed_tokens": total, "accounted_tokens": reported,
            "no_key_tokens": _total(org_minutes.get(None))}


def _total(minutes):
    return sum(sum(t.values()) for by_model in (minutes or {}).values() for t in by_model.values())


def _gap(row):
    b = row.get("bill") or {}
    return sum(sum(g["tokens"].values()) for g in b.get("gaps") or [])


def render(res):
    lines = ["vawr team, %s to %s UTC" % (res["window"][0][:16].replace("T", " "),
                                          res["window"][1][:16].replace("T", " ")), ""]
    for mb in res["members"]:
        lines.append("  bundle %s: key %s, chain %s, report %s, continuity: %s" % (
            mb["bundle"].rsplit("/", 1)[-1], mb["key_id"] or "?", "intact" if mb["chain_ok"] else "BROKEN",
            "matches its log" if mb["report_ok"] else "DOES NOT match its log", mb["continuity"]["short"]))
    lines.append("")
    for r in res["keys"]:
        label = "%s (%s)" % (r["key_name"] or "unnamed key", r["key_id"])
        if r["status"] == "no report":
            lines.append("NO REPORT  %s: %s tokens billed, no bundle covers this key" % (
                label, "{:,}".format(r["billed_tokens"])))
            continue
        gap = _gap(r)
        lines.append("%s  %s: %s tokens billed, %s unexplained; %d bundle(s)" % (
            "PASS" if r["status"] == "pass" else "FAIL", label, "{:,}".format(r["billed_tokens"]),
            "{:,}".format(gap), len(r["bundles"])))
        s = r.get("sessions")
        if s and s.get("error"):
            lines.append("        sessions: %s" % s["error"])
        elif s:
            lines += daily.render_lines(s)
    lines += ["", "Organization: %s tokens billed to API keys in the window; %s (%s) accounted for by bundles." % (
        "{:,}".format(res["billed_tokens"]), "{:,}".format(res["accounted_tokens"]),
        "%.1f%%" % (100.0 * res["accounted_tokens"] / res["billed_tokens"]) if res["billed_tokens"] else "n/a")]
    if res["no_key_tokens"]:
        lines.append("Plus %s tokens with no API key (for example the Console), which no bundle can cover."
                     % "{:,}".format(res["no_key_tokens"]))
    return "\n".join(lines)
