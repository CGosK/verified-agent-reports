"""Report bundles: one file a team sends to whoever pays for its API key, and the
payer's one-command check of it.

    vawr bundle --since 2026-11-01 --until 2026-12-01 --project grant-x   (the team)
    vawr receive vawr-report-....zip                                       (the payer)

A bundle is a zip of five files: bundle.json (what it covers), report.json (usage
by category), check.json (the team's own `vawr check`), report.html (the page to
read) and log.jsonl (the log up to the report's head hash, shared whole because
the chain can only be checked whole).

`receive` treats the bundle as untrusted. It reads only those five names, never
extracts paths from the zip, and rebuilds the report from the log itself. With
the payer's own Admin key it re-runs the bill and sessions checks against
Anthropic's records, so nothing rests on the team's word if the payer owns the
API key. It also keeps a ledger of the head hashes it has received from each log
(~/.vawr/received.jsonl): a later report whose log no longer contains an earlier
head means history was rewritten between reports (continuity).
"""
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone

from . import __version__, chainlog, check, paths, report as report_mod
from .logdata import sessions as log_sessions

FORMAT = "vawr-bundle/1"
MEMBERS = ("bundle.json", "report.json", "check.json", "report.html", "log.jsonl")
MAX_MEMBER_BYTES = 2 * 1024 ** 3  # refuse absurd sizes (zip bombs) before reading
SENT = os.path.join(paths.WORK, "sent.jsonl")
RECEIVED = os.path.join(paths.WORK, "received.jsonl")
# Event attributes that carry text people wrote or read: Claude Code sends them as
# "<REDACTED>" unless OTEL_LOG_USER_PROMPTS / OTEL_LOG_TOOL_DETAILS are turned on.
CONTENT_ATTRIBUTES = ("prompt", "prompt_text", "response", "tool_parameters", "tool_input", "tool_output")


# ---------- shared ----------

def bundle_log_id(bundle_path):
    """The log ID inside a bundle, as its manifest states it (for grouping only;
    receive() checks it against the log)."""
    with zipfile.ZipFile(bundle_path) as z:
        info = z.getinfo("bundle.json")
        if info.file_size > MAX_MEMBER_BYTES:
            raise ValueError("bundle.json is too large")
        m = json.loads(z.read(info))
    return ((m.get("log") or {}) if isinstance(m, dict) else {}).get("id")


def log_id(log_path):
    """The hash of the log's first entry: names the log across reports."""
    for _, e in chainlog.read_entries(log_path):
        return e.get("hash")
    return None


def _ledger(path):
    out = []
    if os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    return out


def _append(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def _iso(t):
    return t.isoformat() if t else None


def _parse(s):
    if not s:
        return None
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


# ---------- the team's side ----------

def text_in_log(log_path):
    """Entries whose events carry prompt, response or tool text (not "<REDACTED>")."""
    found = []
    for _, e in chainlog.read_entries(log_path):
        a = (e.get("event") or {}).get("attributes") or {}
        keys = [k for k in CONTENT_ATTRIBUTES if isinstance(a.get(k), str) and a[k] and a[k] != "<REDACTED>"]
        if keys:
            found.append((e.get("seq"), keys))
    return found


def log_contents(log_path):
    """What the recipient will see in the log: sessions per project tag and category."""
    per = {}
    for s in log_sessions(log_path).values():
        k = (s.get("project") or "(no project tag)", s.get("category") or "untagged", s.get("mode") or "?")
        per[k] = per.get(k, 0) + 1
    return [{"project": k[0], "category": k[1], "billing": k[2], "sessions": n}
            for k, n in sorted(per.items(), key=lambda kv: -kv[1])]


def make(out_path, log_path, start, end, only_projects=None, title=None, admin_key=None, key_id=None,
         api_key=None, claude_projects=None, previous=None, allow_text=False, run_check=True, note=None,
         record=True):
    """Write a bundle; returns its manifest. `previous`: a head hash (or None to use the
    last bundle sent from this log for the same key and projects; "" for none)."""
    from . import html_report
    if not allow_text:
        text = text_in_log(log_path)
        if text:
            raise ValueError("the log has prompt, response or tool text in %d entries (first: entry %s, %s); "
                             "turn off OTEL_LOG_USER_PROMPTS / OTEL_LOG_TOOL_DETAILS for future sessions, or pass "
                             "--allow-text to share it anyway" % (len(text), text[0][0], ", ".join(text[0][1])))
    with tempfile.TemporaryDirectory() as d:
        log_copy = os.path.join(d, "log.jsonl")
        shutil.copyfile(log_path, log_copy)  # the receiver may append while we work
        ok, problems, entries, head = chainlog.verify(log_copy)
        if not ok:
            raise ValueError("the log's chain doesn't verify (%s); fix or explain that before sharing" % problems[0])
        rep = report_mod.build(log_copy, start=start, end=end, only_projects=only_projects)
        res = None
        if run_check:
            res = check.run(start, end, log_copy, claude_projects or paths.CLAUDE_PROJECTS, admin_key=admin_key,
                            key_id=key_id, api_key=api_key, coverage=True, only_projects=only_projects)
            key_id = key_id or (res.get("bill") or {}).get("key_id")
            res["checked_by"] = "the team that sent this report, on its own machine"
        lid = log_id(log_copy)
        projs = sorted(only_projects) if only_projects else None
        if previous is None:
            prior = [r for r in _ledger(SENT) if r.get("log_id") == lid and r.get("key_id") == key_id
                     and r.get("only_projects") == projs and r.get("head") != head]
            previous = prior[-1]["head"] if prior else ""
        manifest = {
            "format": FORMAT, "created": _iso(datetime.now(timezone.utc)), "vawr": __version__,
            "title": title, "note": note, "window": [_iso(start), _iso(end)], "only_projects": projs,
            "key_id": key_id, "log": {"id": lid, "head": head, "entries": entries},
            "previous_head": previous or None,
            "level": res["level"] if res else None,
            "log_contents": log_contents(log_copy),
        }
        rep["log"]["path"] = "log.jsonl"
        page = html_report.render(rep, check=res, title=title or "Agent usage report")
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("bundle.json", json.dumps(manifest, indent=1))
            z.writestr("report.json", json.dumps(rep, indent=1))
            z.writestr("check.json", json.dumps(res, indent=1, default=str))
            z.writestr("report.html", page)
            z.write(log_copy, "log.jsonl")
    if record:
        _append(SENT, {"created": manifest["created"], "log_id": lid, "head": head, "key_id": key_id,
                       "only_projects": projs, "window": manifest["window"], "file": os.path.abspath(out_path)})
    return manifest


# ---------- the payer's side ----------

def _read_bundle(path, into):
    """Copy the five known members of the zip into `into` under fixed names; nothing
    else in the archive is read. Returns {name: path}."""
    out = {}
    with zipfile.ZipFile(path) as z:
        infos = {i.filename: i for i in z.infolist()}
        for name in MEMBERS:
            info = infos.get(name)
            if info is None:
                continue
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError("%s in the bundle is %d bytes; refusing to read it" % (name, info.file_size))
            dest = os.path.join(into, name)
            with z.open(info) as src, open(dest, "wb") as dst:
                copied = 0
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > MAX_MEMBER_BYTES:
                        raise ValueError("%s in the bundle is larger than it claims; refusing to read it" % name)
                    dst.write(chunk)
            out[name] = dest
    missing = [n for n in ("bundle.json", "report.json", "log.jsonl") if n not in out]
    if missing:
        raise ValueError("not a vawr bundle: %s missing" % ", ".join(missing))
    return out


def continuity(lid, log_path, known, head=None, key_id=None, only_projects=None, siblings=()):
    """Does this log contain every head hash already received from the same log?
    `known`: earlier ledger records. Returns a dict with ok True/False/None. Reports
    received before for the same API key and projects from a different log fail too:
    a log rebuilt from its first entry looks like a new log."""
    same = [r for r in known if r.get("log_id") == lid and head and r.get("head") == head]
    earlier = [r for r in known if r.get("log_id") == lid and r.get("head") != head]
    other_logs = [r for r in known if r.get("log_id") != lid and r.get("log_id") not in siblings and key_id
                  and r.get("key_id") == key_id and r.get("only_projects") == only_projects]
    if other_logs and not earlier:
        r = max(other_logs, key=lambda x: x.get("received") or "")
        return {"ok": False, "short": "a different log from your earlier reports for this key",
                "note": "Your earlier reports for API key %s%s (last received %s) came from a different log; this "
                        "one doesn't extend it. Either the team started a new log, or the old one was rebuilt "
                        "from its first entry. Ask which before relying on the earlier figures." % (
                            key_id, " and projects %s" % ", ".join(only_projects) if only_projects else "",
                            (r.get("received") or "")[:16].replace("T", " ")),
                "earlier": 0, "other_logs": sorted({x.get("log_id") for x in other_logs})}
    if not earlier and same:
        return {"ok": None, "short": "same report you received %s" % (same[0].get("received") or "")[:16].replace("T", " "),
                "note": "You received this exact log before, and no other report from it.", "earlier": 0}
    if not earlier:
        return {"ok": None, "short": "first report from this log",
                "note": "This is the first report you have received from this log, so there is nothing earlier "
                        "to compare it with. Its head hash is now recorded for the next one.",
                "earlier": 0}
    hashes = set()
    for _, e in chainlog.read_entries(log_path):
        hashes.add(e.get("hash"))
    lost = [r for r in earlier if r.get("head") not in hashes]
    if lost:
        r = lost[0]
        return {"ok": False, "short": "history changed since an earlier report",
                "note": "The report received %s (head %s…) was built from this log, but its head hash is no longer "
                        "in it: entries up to that point were changed and the chain rebuilt." % (
                            (r.get("received") or "")[:16].replace("T", " "), (r.get("head") or "")[:16]),
                "earlier": len(earlier), "lost": [x.get("head") for x in lost]}
    last = max(earlier, key=lambda r: r.get("received") or "")
    gap = None
    if last.get("window") and last["window"][1]:
        gap = last["window"][1]
    return {"ok": True, "short": "extends the %d earlier report%s from this log" % (
                len(earlier), "" if len(earlier) == 1 else "s"),
            "note": "This log contains the head hash of every earlier report you received from it (%d), so "
                    "nothing before those points changed. The last one covered up to %s." % (
                        len(earlier), (gap or "?")[:16].replace("T", " ")),
            "earlier": len(earlier), "previous_window_end": gap}


def receive(bundle_path, admin_key=None, key_id=None, ledger=RECEIVED, record=True, workdir=None, known=None,
            siblings=()):
    """Check a bundle. Returns a result dict with "verdict": "verified" (everything
    passed, including the bill and sessions checks against the payer's own records),
    "consistent" (the log and report hold together, but no Admin key could check them
    against a bill) or "failed"."""
    tmp = workdir or tempfile.mkdtemp(prefix="vawr-receive-")
    files = _read_bundle(bundle_path, tmp)
    with open(files["bundle.json"]) as fh:
        manifest = json.load(fh)
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise ValueError("not a %s bundle (format %r)" % (FORMAT, manifest.get("format") if isinstance(
            manifest, dict) else None))
    log = files["log.jsonl"]
    out = {"bundle": os.path.abspath(bundle_path), "manifest": manifest, "files": files}

    ok, problems, entries, head = chainlog.verify(log)
    lid = log_id(log)
    m_log = manifest.get("log") or {}
    chain = {"ok": ok and head == m_log.get("head") and lid == m_log.get("id"), "entries": entries, "head": head,
             "problems": problems[:5]}
    if ok and head != m_log.get("head"):
        chain["problems"].append("the log ends at %s…, but the bundle says %s…" % (
            (head or "")[:16], (m_log.get("head") or "")[:16]))
    out["chain"] = chain

    vr = check.verify_report(log, files["report.json"])
    out["report"] = {"ok": vr["ok"], "head_found": vr.get("head_found"), "differences": vr.get("differences"),
                     "note": vr.get("note")}
    rebuilt = vr.get("report")

    known = _ledger(ledger) if known is None else known
    out["continuity"] = continuity(lid, log, known, head, key_id or manifest.get("key_id"),
                                   manifest.get("only_projects"), siblings=set(siblings) - {lid})
    if manifest.get("previous_head") and not any(r.get("head") == manifest["previous_head"] for r in known):
        out["continuity"]["unseen_previous"] = manifest["previous_head"]

    w = manifest.get("window") or [None, None]
    start, end = _parse(w[0]), _parse(w[1])
    only = manifest.get("only_projects")
    key = key_id or manifest.get("key_id")
    res = None
    if admin_key and key and start and end:
        try:
            res = check.run(start, end, log, None, admin_key=admin_key, key_id=key, coverage=False,
                            only_projects=only)
        except Exception as exc:  # e.g. the key isn't in the payer's organization
            out["provider_error"] = "%s: %s" % (type(exc).__name__, exc)
    elif admin_key and not key:
        out["provider_error"] = "the bundle names no API key; pass --key-id with the key you issued"
    elif admin_key and not (start and end):
        out["provider_error"] = "the bundle gives no time window"
    out["check"] = res

    failed = (not chain["ok"] or not out["report"]["ok"] or out["continuity"]["ok"] is False
              or (res is not None and res["level"] == "failed"))
    if failed:
        verdict = "failed"
    elif res is not None and res.get("bill") is not None and (res.get("sessions") or {}).get("ok") is not False:
        verdict = "verified"
    else:
        verdict = "consistent"
    out["verdict"] = verdict
    out["rebuilt_report"] = rebuilt

    if record and chain["ok"] and not any(r.get("head") == head and r.get("log_id") == lid for r in known):
        _append(ledger, {"received": _iso(datetime.now(timezone.utc)), "log_id": lid, "head": head,
                         "window": w, "key_id": key, "only_projects": only, "verdict": verdict,
                         "bundle": os.path.basename(bundle_path)})
    return out


VERDICTS = {
    "verified": "VERIFIED  checked against your own Anthropic records",
    "consistent": "CONSISTENT  the log and report hold together; not checked against Anthropic's records",
    "failed": "FAILED",
}


def render_receive(out):
    m = out["manifest"]
    mark = {True: "PASS", False: "FAIL", None: "SKIP"}
    lines = ["vawr receive %s" % os.path.basename(out["bundle"]), ""]
    w = m.get("window") or [None, None]
    lines.append("Report: %s, %s to %s UTC%s" % (
        m.get("title") or "untitled", (w[0] or "?")[:16].replace("T", " "), (w[1] or "?")[:16].replace("T", " "),
        ", projects %s" % ", ".join(m["only_projects"]) if m.get("only_projects") else ""))
    if m.get("key_id"):
        lines.append("API key: %s" % m["key_id"])
    lines.append("")
    c = out["chain"]
    lines.append("%s  chain        %d entries, head %s%s" % (mark[c["ok"]], c["entries"], (c["head"] or "")[:16],
                                                       "; " + c["problems"][0] if c["problems"] else ""))
    r = out["report"]
    lines.append("%s  report       %s" % (mark[r["ok"]], "rebuilt from the log: same tokens per category"
                                         if r["ok"] else (r.get("note") or "differs from the log: %s" % r["differences"])))
    co = out["continuity"]
    lines.append("%s  continuity   %s" % (mark[co["ok"]], co["short"]))
    if co["ok"] is False:
        lines.append("        " + co["note"])
    if co.get("unseen_previous"):
        lines.append("        the team says its previous report had head %s…, which you haven't received here"
                     % co["unseen_previous"][:16])
    res = out.get("check")
    if res is None:
        lines.append("SKIP  bill         %s" % (out.get("provider_error") or
                                                "set ANTHROPIC_ADMIN_KEY (yours, for the account that owns the key) "
                                                "to check against Anthropic's records"))
    else:
        for line in check.render(res).splitlines():
            if line.startswith(("PASS  bill", "FAIL  bill", "SKIP  bill", "PASS  sessions", "FAIL  sessions",
                                "SKIP  sessions", "        ", "          ")):
                lines.append(line)
    lines += ["", VERDICTS[out["verdict"]]]
    if out["verdict"] == "consistent":
        lines.append("Nothing was edited after the fact, but the usage figures rest on the team's log. If you own "
                     "the API key's organization, add your Admin key to check them against Anthropic's records.")
    other = [x for x in m.get("log_contents") or [] if m.get("only_projects") and x["project"] not in m["only_projects"]]
    if other:
        lines.append("The log also holds %d session(s) from other projects, which the report leaves out."
                     % sum(x["sessions"] for x in other))
    return "\n".join(lines)


def receive_html(out, title=None):
    """A fresh page built on the recipient's machine from the log itself and the
    recipient's own checks (not the page the team sent)."""
    from . import html_report
    rep = dict(out["rebuilt_report"] or {})
    rep["log"] = dict(rep.get("log") or {}, path="log.jsonl")
    res = dict(out["check"]) if out.get("check") else {
        "window": (out["manifest"].get("window") or [None, None]),
        "chain": out["chain"], "coverage": {"ok": None, "local_requests": 0, "logged_requests_in_window": 0,
                                            "token_mismatches": 0, "unlogged_sessions": []},
        "bill": None, "sessions": None}
    res["chain"] = out["chain"]
    res["continuity"] = out["continuity"]
    res["level"] = ("failed" if out["verdict"] == "failed" else
                    "provider" if out["verdict"] == "verified" else "tamper-evident")
    res["checked_by"] = "the recipient, on their own machine" + (
        " with their own Admin key" if out.get("check") else "")
    return html_report.render(rep, check=res, title=title or out["manifest"].get("title") or "Agent usage report")
