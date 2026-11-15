"""`vawr team`: an organization admin checks everyone's bundles at once against
the organization's own Anthropic records.

For each API key with usage in the window, it answers: did any bundle cover it,
is everything billed to it accounted for by the bundles' logs (per minute), and
does Anthropic's daily count of Claude Code sessions on it equal the logs' (see
daily.py)? Keys that billed usage but no bundle covers are listed with their
tokens: that is usage nobody reported.
"""
import os
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
    with tempfile.TemporaryDirectory(prefix="vawr-team-") as work:
        return _run(work, bundle_paths, admin_key, start, end, ledger, record, sessions, org_minutes, keys, fetch,
                    now)


def _run(work, bundle_paths, admin_key, start, end, ledger, record, sessions, org_minutes, keys, fetch, now):
    members, unreadable = [], []
    known = bundle._ledger(ledger)  # before this run, so bundles in it don't count as each other's history
    for i, path in enumerate(bundle_paths):
        try:
            out = bundle.receive(path, admin_key=None, ledger=ledger, record=False, known=known,
                                 workdir=tempfile.mkdtemp(prefix="m%d-" % i, dir=work))
        except Exception as exc:  # one unreadable bundle shouldn't stop the others
            unreadable.append({"bundle": path, "error": bundle.clean("%s: %s" % (type(exc).__name__, exc), 300)})
            continue
        m = out["manifest"]
        members.append({"bundle": path, "title": m.get("title"), "key_id": m.get("key_id"),
                        "only_projects": m.get("only_projects"),
                        "window": [_parse(m["window"][0]), _parse(m["window"][1])],
                        "log": out["files"]["log.jsonl"], "log_id": m["log"]["id"], "chain_ok": out["chain"]["ok"],
                        "report_ok": out["report"]["ok"], "continuity": out["continuity"],
                        "head": out["chain"]["head"], "entries": out["chain"]["entries"]})
    # teammates' logs on the same key don't count against each other, but only logs whose chains verified
    verified_ids = {mb["log_id"] for mb in members if mb["chain_ok"]}
    for mb in members:
        if mb["chain_ok"] and mb["continuity"]["ok"] is False and mb["continuity"].get("other_logs"):
            mb["continuity"] = bundle.continuity(mb["log_id"], mb["log"], known, mb["head"], mb["key_id"],
                                                 mb["entries"], siblings=tuple(verified_ids - {mb["log_id"]}),
                                                 ledger=ledger)
    starts = [mb["window"][0] for mb in members]
    ends = [mb["window"][1] for mb in members]
    start = start or (min(starts) if starts else None)
    end = end or (max(ends) if ends else None)
    if not (start and end):
        raise ValueError("no time window: give --since and --until, or readable bundles that carry one")

    if org_minutes is None:
        org_minutes = usage_api.org_minute_usage(admin_key, start, end)
    if keys is None:
        keys = usage_api.api_keys(admin_key)
    names = {k.get("id"): k.get("name") for k in keys}

    rows = []
    key_ids = sorted({k for k in org_minutes if k} | {mb["key_id"] for mb in members if mb["key_id"]},
                     key=lambda k: -_total(org_minutes.get(k)))
    for kid in key_ids:
        try:
            rows.append(_key_row(kid, members, org_minutes, names, keys, admin_key, start, end, sessions, fetch,
                                 now))
        except Exception as exc:  # a malformed log fails its key, not the whole run
            rows.append({"key_id": kid, "key_name": names.get(kid), "in_organization": kid in names,
                         "billed_tokens": _total(org_minutes.get(kid)), "bundles": [mb["bundle"] for mb in members
                                                                                   if mb["key_id"] == kid],
                         "bill": None, "sessions": None, "status": "fail",
                         "error": bundle.clean("%s: %s" % (type(exc).__name__, exc), 300)})
    if record:
        for mb in members:
            if mb["chain_ok"]:
                row = next((r for r in rows if r["key_id"] == mb["key_id"]), None)
                verdict = ("failed" if not mb["report_ok"] or mb["continuity"]["ok"] is False else
                           "verified" if row and row["status"] == "pass" else "consistent")
                bundle.record_received(ledger, mb["log_id"], mb["head"], mb["entries"],
                                       [x.isoformat() for x in mb["window"]], mb["key_id"], mb["only_projects"],
                                       verdict, os.path.basename(mb["bundle"]), bundle.log_hashes(mb["log"]))
    total = sum(r["billed_tokens"] for r in rows)
    reported = sum(max(0, r["billed_tokens"] - _gap(r)) for r in rows if r["status"] == "pass")
    return {"window": [start.isoformat(), end.isoformat()], "members": [
                {k: (v if k != "window" else [x.isoformat() if x else None for x in v]) for k, v in mb.items()
                 if k not in ("log",)} for mb in members],
            "unreadable": unreadable, "keys": rows, "billed_tokens": total, "accounted_tokens": reported,
            "no_key_tokens": _total(org_minutes.get(None))}


def _key_row(kid, members, org_minutes, names, keys, admin_key, start, end, sessions, fetch, now):
    if True:
        mine = [mb for mb in members if mb["key_id"] == kid]
        minutes = {parse_ts(t): v for t, v in (org_minutes.get(kid) or {}).items()}
        billed = _total(org_minutes.get(kid))
        row = {"key_id": kid, "key_name": names.get(kid), "in_organization": kid in names, "billed_tokens": billed,
               "bundles": [mb["bundle"] for mb in mine], "bill": None, "sessions": None}
        if not mine:
            row["status"] = "no report"
            return row
        reqs, seen = [], set()  # two bundles cut from one log share entries: count each once
        for mb in mine:
            ws, we = mb["window"]
            for r in api_requests(mb["log"]):
                t = r.get("time")
                try:
                    tt = parse_ts(t) if t else None
                except (TypeError, ValueError):
                    tt = None
                if (tt and r.get("mode") in daily.API_KEY_MODES and ws <= tt < we
                        and (not mb["only_projects"] or r.get("project") in mb["only_projects"])
                        and (mb["log_id"], r.get("seq")) not in seen):
                    seen.add((mb["log_id"], r.get("seq")))
                    reqs.append(dict(r, mode="api_key"))
        row["bill"] = auditor.check_provider(reqs, start, end, key_mode="api_key", provider_minutes=minutes)
        if sessions and not row["in_organization"]:
            row["sessions"] = {"ok": None, "error": "this key isn't in your organization"}
        elif sessions and sum(1 for k in keys if k.get("name") == names.get(kid)) > 1:
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
        s = row["sessions"] or {}
        if broken or not row["bill"]["ok"] or s.get("ok") is False or not row["in_organization"]:
            row["status"] = "fail"
        elif s.get("error"):
            row["status"] = "check"  # the bill check passed; the session count couldn't run
        else:
            row["status"] = "pass"
        if len({mb["log_id"] for mb in mine}) > 1 and row["status"] == "pass":
            row["status"] = "check"
            row["note"] = "bundles from %d different logs cover this key; give each person their own key" % len(
                {mb["log_id"] for mb in mine})
        return row


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
            bundle.clean(mb["bundle"].rsplit("/", 1)[-1]), mb["key_id"] or "?",
            "intact" if mb["chain_ok"] else "BROKEN",
            "matches its log" if mb["report_ok"] else "DOES NOT match its log", mb["continuity"]["short"]))
    for u in res.get("unreadable") or []:
        lines.append("  bundle %s: UNREADABLE, %s" % (bundle.clean(u["bundle"].rsplit("/", 1)[-1]), u["error"]))
    lines.append("")
    for r in res["keys"]:
        label = "%s (%s)" % (bundle.clean(r["key_name"] or "unnamed key"), r["key_id"])
        if not r.get("in_organization", True):
            label += ", NOT IN YOUR ORGANIZATION"
        if r["status"] == "no report":
            lines.append("NO REPORT  %s: %s tokens billed, no bundle covers this key" % (
                label, "{:,}".format(r["billed_tokens"])))
            continue
        if r.get("error"):
            lines.append("FAIL  %s: the bundles' logs broke the checks (%s)" % (label, r["error"]))
            continue
        gap = _gap(r)
        excess = sum(sum(x["tokens"].values()) for x in (r["bill"] or {}).get("log_excess") or []
                     if isinstance(x.get("tokens"), dict))
        lines.append("%s  %s: %s tokens billed, %s unexplained%s; %d bundle(s)" % (
            {"pass": "PASS", "fail": "FAIL", "check": "CHECK"}[r["status"]], label,
            "{:,}".format(r["billed_tokens"]), "{:,}".format(gap),
            ", %s in the logs but not billed" % "{:,}".format(excess) if excess else "", len(r["bundles"])))
        if r.get("note"):
            lines.append("        " + r["note"])
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
