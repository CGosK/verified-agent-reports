"""Report bundles: one file a team sends to whoever pays for its API key, and the
payer's one-command check of it.

    vawr bundle --since 2026-11-01 --until 2026-12-01 --project grant-x   (the team)
    vawr receive vawr-report-....zip                                       (the payer)

A bundle is a zip of five files: bundle.json (what it covers), report.json (usage
by category), check.json (the team's own `vawr check`), report.html (the team's
page, for reading without vawr; `receive` doesn't check it and `receive --html`
builds the recipient's own) and log.jsonl (the log up to the report's head hash,
shared whole because the chain can only be checked whole).

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
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone

from . import __version__, chainlog, check, paths, report as report_mod
from .logdata import sessions as log_sessions

FORMAT = "vawr-bundle/1"
MEMBERS = ("bundle.json", "report.json", "check.json", "report.html", "log.jsonl")
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
        if info.file_size > 1024 ** 2:
            raise ValueError("bundle.json is too large")
        m = chainlog.loads(z.read(info).decode("utf-8", "replace"))
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
    # in UTC: Anthropic's records and the sessions check's days are UTC, and a window
    # written with another offset mustn't shift which day a minute falls on
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


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
    if not os.path.exists(log_path) or log_id(log_path) is None:
        raise ValueError("the log is empty: there's nothing to report yet (start the receiver with `vawr start`, "
                         "then use Claude Code)")
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

MAX_LOG_BYTES = 1024 ** 3        # 1 GiB uncompressed
MAX_OTHER_BYTES = 64 * 1024 ** 2
MAX_RATIO = 200                  # our logs compress about 10:1; far more is a zip bomb
KEY_ID = re.compile(r"apikey_[A-Za-z0-9]{1,64}")   # used with fullmatch: no trailing newline sneaks through
HASH = re.compile(r"[0-9a-f]{64}")
MAX_WINDOW_DAYS = 100
SETTLE = timedelta(minutes=60)  # Anthropic's usage records for a minute can take this long to appear


def clean(value, limit=200):
    """A sender-written string, safe to print: no control characters (no fake lines,
    no terminal escapes), at most `limit` characters."""
    text = "".join(ch for ch in str(value) if ch.isprintable())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _read_bundle(path, into):
    """Copy the five known members of the zip into `into` under fixed names; nothing
    else in the archive is read and no path from it is used. Returns {name: path}."""
    out = {}
    with zipfile.ZipFile(path) as z:
        infos = {}
        for info in z.infolist():
            if info.filename in MEMBERS:
                if info.filename in infos:
                    raise ValueError("the bundle has %s twice" % info.filename)
                infos[info.filename] = info
        for name in MEMBERS:
            info = infos.get(name)
            if info is None:
                continue
            cap = MAX_LOG_BYTES if name == "log.jsonl" else MAX_OTHER_BYTES
            if info.file_size > cap:
                raise ValueError("%s in the bundle is %d bytes; refusing to read it" % (name, info.file_size))
            if info.file_size > 1024 ** 2 and info.file_size > MAX_RATIO * max(info.compress_size, 1):
                raise ValueError("%s in the bundle expands %d-fold; refusing to read it" % (
                    name, info.file_size // max(info.compress_size, 1)))
            dest = os.path.join(into, name)
            with z.open(info) as src, open(dest, "wb") as dst:
                copied = 0
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > cap:
                        raise ValueError("%s in the bundle is larger than it claims; refusing to read it" % name)
                    dst.write(chunk)
            out[name] = dest
    missing = [n for n in ("bundle.json", "report.json", "log.jsonl") if n not in out]
    if missing:
        raise ValueError("not a vawr bundle: %s missing" % ", ".join(missing))
    return out


def read_manifest(path):
    """bundle.json, checked field by field; raises ValueError on anything malformed."""
    try:
        with open(path) as fh:
            m = json.load(fh, parse_int=chainlog.safe_int)
    except ValueError as exc:
        raise ValueError("bundle.json isn't JSON: %s" % exc)
    if not isinstance(m, dict) or m.get("format") != FORMAT:
        raise ValueError("not a %s bundle" % FORMAT)
    w = m.get("window")
    if not (isinstance(w, list) and len(w) == 2 and all(isinstance(x, str) for x in w)):
        raise ValueError("bundle.json has no window")
    try:
        start, end = _parse(w[0]), _parse(w[1])
    except ValueError:
        raise ValueError("bundle.json's window isn't two ISO times")
    if not start < end:
        raise ValueError("bundle.json's window ends before it starts")
    if start.second or start.microsecond or end.second or end.microsecond:
        raise ValueError("bundle.json's window must start and end on whole UTC minutes (the bill is per minute)")
    if (end - start).days > MAX_WINDOW_DAYS or start.year < 2023:
        raise ValueError("bundle.json's window is longer than %d days or starts before 2023; ask for a report "
                         "per month or quarter" % MAX_WINDOW_DAYS)
    only = m.get("only_projects")
    if only is not None:
        if not (isinstance(only, list) and only and all(isinstance(x, str) for x in only)):
            raise ValueError("bundle.json's only_projects isn't a list of names")
        m["only_projects"] = sorted(set(only))
    if m.get("key_id") is not None and not (isinstance(m["key_id"], str) and KEY_ID.fullmatch(m["key_id"])):
        raise ValueError("bundle.json's key_id isn't an API key ID")
    log = m.get("log")
    if not (isinstance(log, dict) and all(isinstance(log.get(k), str) and HASH.fullmatch(log[k]) for k in ("id", "head"))):
        raise ValueError("bundle.json doesn't name its log's first and last hashes")
    if m.get("previous_head") is not None and not (isinstance(m["previous_head"], str)
                                                   and HASH.fullmatch(m["previous_head"])):
        m["previous_head"] = None
    for k in ("title", "note"):
        m[k] = clean(m[k]) if m.get(k) is not None else None
    return m, start, end


def _hash_store(ledger):
    return os.path.join(os.path.dirname(os.path.abspath(ledger)), "received_logs")


def _stored_hashes(ledger, lid):
    path = os.path.join(_hash_store(ledger), "%s.json" % lid)
    if not (lid and HASH.fullmatch(lid) and os.path.exists(path)):
        return None
    try:
        with open(path) as fh:
            return json.load(fh).get("hashes")
    except (OSError, ValueError):
        return None


def _store_hashes(ledger, lid, hashes):
    d = _hash_store(ledger)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "%s.json" % lid), "w") as fh:
        json.dump({"log_id": lid, "entries": len(hashes), "hashes": hashes}, fh)


def log_hashes(log_path):
    return [e.get("hash") if isinstance(e, dict) else None for _, e in chainlog.read_entries(log_path)]


def continuity(lid, log_path, known, head=None, key_id=None, entries=None, siblings=(), ledger=RECEIVED,
               hashes=None):
    """Is this log consistent with every earlier report received from it, and with the
    log behind earlier verified reports for the same API key?

    For each log you receive, the entry hashes of the longest version you've accepted are
    kept next to the ledger (received_logs/<log id>.json). A later report must match them
    entry for entry wherever the two overlap, whether it is longer (it extends them) or
    shorter (an older report arriving late). A report for an API key whose earlier
    verified reports came from a different log fails: a log rebuilt from its first entry
    looks like a new log. Keys only count once a report on them was verified with your
    own Admin key, so a bundle that merely names someone's key can't poison the ledger."""
    known = [r for r in known if isinstance(r, dict)]
    hashes = hashes if hashes is not None else log_hashes(log_path)
    if key_id:
        mine = [r for r in known if r.get("log_id") == lid and r.get("key_id") == key_id]
        others = [r for r in known if r.get("key_id") == key_id and r.get("log_id") not in (lid,) + tuple(siblings)
                  and r.get("verdict") == "verified"]
        if others and not mine:
            r = max(others, key=lambda x: x.get("received") or "")
            return {"ok": False, "short": "a different log from your earlier reports for this key",
                    "note": "Your earlier verified reports for API key %s (last received %s) came from a different "
                            "log; this one doesn't extend it. Either the team started a new log, or the old one was "
                            "rebuilt from its first entry. Ask which before relying on the earlier figures." % (
                                key_id, clean(r.get("received") or "")[:16].replace("T", " ")),
                    "other_logs": sorted({str(x.get("log_id")) for x in others})}
    stored = _stored_hashes(ledger, lid)
    if not stored:
        note = ("This is the first report you have received from this log, so there is nothing earlier to compare "
                "it with. Its entries' hashes are now kept for the next one.")
        if not key_id:
            note += (" The bundle names no API key, so a later log rebuilt from scratch can't be told from a new "
                     "one; pass --key-id with the key you issued.")
        return {"ok": None, "short": "first report from this log", "note": note}
    n = min(len(stored), len(hashes))
    diverge = next((i for i in range(n) if stored[i] != hashes[i]), None)
    if diverge is not None:
        return {"ok": False, "short": "history changed since an earlier report",
                "note": "An earlier report you received from this log had a different entry %d: entries up to "
                        "that point were changed and the chain rebuilt." % diverge, "diverges_at": diverge}
    if len(hashes) < len(stored):
        return {"ok": True, "short": "an older report than one you have; matches it entry for entry",
                "note": "This log is the first %d entries of one you already received, unchanged." % len(hashes)}
    if len(hashes) == len(stored):
        return {"ok": True, "short": "the same log as a report you received", "note": "Nothing new since then."}
    return {"ok": True, "short": "extends the earlier report%s from this log" % ("" if len(
                [r for r in known if r.get("log_id") == lid]) <= 1 else "s"),
            "note": "The first %d entries match what you received before, entry for entry; %d are new." % (
                len(stored), len(hashes) - len(stored))}


def record_received(ledger, lid, head, entries, window, key, only, verdict, bundle_name, hashes):
    """Add a receive to the ledger, and keep the log's hashes if it was accepted. The key is
    recorded as this log's only when the report was verified against it."""
    _append(ledger, {"received": _iso(datetime.now(timezone.utc)), "log_id": lid, "head": head,
                     "entries": entries, "window": window, "key_id": key if verdict == "verified" else None,
                     "named_key": key, "only_projects": only, "verdict": verdict, "bundle": clean(bundle_name)})
    if verdict != "failed":
        stored = _stored_hashes(ledger, lid) or []
        if len(hashes) > len(stored):
            _store_hashes(ledger, lid, hashes)


def receive(bundle_path, admin_key=None, key_id=None, ledger=RECEIVED, record=True, workdir=None, known=None,
            siblings=(), now=None):
    """Check a bundle. Returns a result dict with "verdict":
    - "verified": the log and report hold together, continuity holds, and with the
      payer's own Admin key the bill check passed (nothing billed missing from the
      log, nothing in the log that wasn't billed), the sessions check ran without
      failing or finding days Anthropic counted less than the log has, and every
      token in the report is on that API key;
    - "consistent": the log and report hold together, but not all of it was checked
      against Anthropic's records (no Admin key, the records couldn't be read, usage
      marked as a subscription, a window that hasn't ended, or sessions Claude Code
      didn't report to Anthropic);
    - "failed": anything failed, including a log that makes the checks crash.
    Raises ValueError for a file that isn't a readable bundle. Without `workdir`, the
    bundle's files are deleted before returning."""
    import urllib.error
    from . import usage_api
    if workdir is None:
        with tempfile.TemporaryDirectory(prefix="vawr-receive-") as tmp:
            out = receive(bundle_path, admin_key, key_id, ledger, record, tmp, known, siblings, now)
            out.pop("files", None)
            return out
    now = now or datetime.now(timezone.utc)
    files = _read_bundle(bundle_path, workdir)
    manifest, start, end = read_manifest(files["bundle.json"])
    if key_id is not None and not KEY_ID.fullmatch(key_id):
        raise ValueError("--key-id isn't an API key ID")
    log = files["log.jsonl"]
    out = {"bundle": os.path.abspath(bundle_path), "manifest": manifest, "files": files}

    ok, problems, entries, head = chainlog.verify(log)
    lid = log_id(log) if ok else None
    m_log = manifest["log"]
    chain = {"ok": ok and head == m_log["head"] and lid == m_log["id"], "entries": entries, "head": head,
             "problems": [clean(p, 300) for p in problems[:5]]}
    if ok and head != m_log["head"]:
        chain["problems"].append("the log ends at %s…, but the bundle says %s…" % ((head or "")[:16], m_log["head"][:16]))
    if ok and lid != m_log["id"]:
        chain["problems"].append("the log starts at %s…, but the bundle says %s…" % ((lid or "")[:16], m_log["id"][:16]))
    out["chain"] = chain

    try:
        vr = check.verify_report(log, files["report.json"], expect={
            "window": manifest["window"], "only_projects": manifest["only_projects"], "head": head})
    except Exception as exc:  # e.g. a negative token count: no real session writes one
        vr = {"ok": False, "note": "the log can't be read as a usage record: %s" % clean(exc, 200)}
    out["report"] = {"ok": vr["ok"], "head_found": vr.get("head_found"), "differences": vr.get("differences"),
                     "note": vr.get("note")}
    rebuilt = vr.get("report")
    out["log_contents"] = log_contents(log) if ok else []

    key = key_id or manifest.get("key_id")
    out["key_checked"] = key
    known = _ledger(ledger) if known is None else known
    hashes = log_hashes(log) if ok else []
    out["continuity"] = continuity(lid, log, known, head, key, entries, siblings=tuple(set(siblings) - {lid}),
                                   ledger=ledger, hashes=hashes) if ok else {"ok": None, "short": "chain broken",
                                                                              "note": ""}
    if manifest.get("previous_head") and not any(r.get("head") == manifest["previous_head"] for r in known
                                                 if isinstance(r, dict)):
        out["continuity"]["unseen_previous"] = manifest["previous_head"]

    only = manifest["only_projects"]
    res, crashed = None, None
    if admin_key and key and chain["ok"] and out["report"]["ok"]:
        try:
            res = check.run(start, end, log, None, admin_key=admin_key, key_id=key, coverage=False,
                            only_projects=only)
        except urllib.error.URLError as exc:  # couldn't read Anthropic's records
            out["provider_error"] = clean(usage_api.explain(exc), 400)
        except OSError as exc:
            out["provider_error"] = "%s: %s" % (type(exc).__name__, clean(exc, 200))
        except Exception as exc:  # the log itself broke the checks: no honest log does that
            crashed = "%s: %s" % (type(exc).__name__, clean(exc, 200))
            out["provider_error"] = "the log made the checks fail: " + crashed
    elif admin_key and not key:
        out["provider_error"] = "the bundle names no API key; pass --key-id with the key you issued"
    elif admin_key:
        out["provider_error"] = "the log or the report already failed its own checks, so it wasn't run"
    out["check"] = res

    billing = (rebuilt or {}).get("billing") or {}
    unchecked = int(billing.get("subscription") or 0) + int(billing.get("unknown") or 0)
    out["unchecked_tokens"] = unchecked
    out["window_open"] = end > now
    bill = (res or {}).get("bill")
    sess = (res or {}).get("sessions")
    out["settling"] = not (end > now) and end + SETTLE > now
    # while the last minutes may not be billed yet, a log ahead of the bill isn't a failure (a gap still is)
    unbilled_yet = out["settling"] and bill is not None and not bill.get("gaps")
    failed = (crashed or not chain["ok"] or not out["report"]["ok"] or out["continuity"]["ok"] is False
              or (bill is not None and not bill.get("ok") and not unbilled_yet)
              or (isinstance(sess, dict) and sess.get("ok") is False))
    if failed:
        verdict = "failed"
    elif (bill is not None and isinstance(sess, dict) and sess.get("ok") is True  # every day confirmed
          and bill.get("ok") and not unchecked and not out["window_open"] and not out["settling"]):
        verdict = "verified"
    else:
        verdict = "consistent"
    out["verdict"] = verdict
    out["rebuilt_report"] = rebuilt

    if record and chain["ok"] and not any(isinstance(r, dict) and r.get("head") == head and r.get("log_id") == lid
                                          and r.get("verdict") == verdict for r in known):
        record_received(ledger, lid, head, entries, manifest["window"], key, only, verdict,
                        os.path.basename(bundle_path), hashes)
    return out


VERDICTS = {
    "verified": "VERIFIED  checked against your own Anthropic records",
    "consistent": "CONSISTENT  the log and report hold together; not everything was checked against Anthropic's "
                  "records",
    "failed": "FAILED",
}


def _gap_tokens(bill):
    return sum(sum((g.get("tokens") or {}).values()) for g in (bill or {}).get("gaps") or [])


def verdict_reasons(out):
    """Plain reasons for the verdict, most serious first."""
    res = out.get("check") or {}
    bill, sess = res.get("bill"), res.get("sessions")
    if out["verdict"] == "verified":
        bg = sum(((bill or {}).get("background_tokens") or {}).values())
        return ["every token Anthropic billed the key in this period is in the log%s, and Anthropic's daily count "
                "of Claude Code sessions matches the log on every day"
                % (" or is Claude Code's known background request (%s tokens)" % "{:,}".format(bg) if bg else "")]
    why = []
    if not out["chain"]["ok"]:
        why.append("the log's hash chain is broken, so entries were changed or removed")
    if not out["report"]["ok"]:
        why.append("the report's figures differ from the log")
    if out["continuity"]["ok"] is False:
        why.append("continuity: %s" % clean(out["continuity"].get("short") or "doesn't match a report you received", 200))
    if "the log made the checks fail" in (out.get("provider_error") or ""):
        why.append("the log made the checks fail, which no honest log does")
    if isinstance(bill, dict) and not bill.get("ok"):
        gap = _gap_tokens(bill)
        if gap:
            why.append("Anthropic billed the key %s tokens that the log doesn't account for" % "{:,}".format(gap))
        if bill.get("log_excess"):
            why.append("the log claims usage that wasn't billed to this key")
    if isinstance(sess, dict) and sess.get("ok") is False:
        why.append("Anthropic's daily count of Claude Code sessions and tokens doesn't match the log")
    if out["verdict"] == "failed":
        return why or ["a check failed"]
    # consistent: what kept it from VERIFIED
    if not out.get("check"):
        why.append("not checked against Anthropic's records (%s)" % (
            out.get("provider_error") or "no Admin key; pass yours to check the bill"))
    elif bill is None:
        why.append("the bill check didn't run")
    if out.get("check") and isinstance(sess, dict) and sess.get("ok") is not True:
        why.append("Anthropic's daily session count couldn't confirm every day" + (
            " (%s)" % sess["error"] if sess.get("error") else ""))
    if out.get("unchecked_tokens"):
        why.append("%s tokens were on a Claude subscription or unknown billing, which no record you can read covers"
                   % "{:,}".format(out["unchecked_tokens"]))
    if out.get("window_open"):
        why.append("the period hasn't ended")
    if out.get("settling"):
        why.append("the period ended too recently for Anthropic's records of its last minutes" + (
            " (the log has usage not billed yet)" if bill is not None and bill.get("log_excess") else ""))
    return why or ["not everything could be checked against Anthropic's records"]


def usage_line(rebuilt):
    """'1,214,264 tokens: safety 34% (36 runs), ...' from the report rebuilt from the log."""
    cats = [c for c in (rebuilt or {}).get("categories") or [] if isinstance(c, dict)]
    def tok(c):
        t = c.get("total_tokens")
        return t if isinstance(t, (int, float)) else sum(v for v in (c.get("tokens") or {}).values()
                                                          if isinstance(v, (int, float)))
    total = sum(tok(c) for c in cats)
    if not cats or not total:
        return ""
    parts = ["%s %d%%%s" % (clean(str(c.get("category") or "?"), 40), round(100.0 * tok(c) / total),
                            " (%d run%s)" % (c["runs"], "" if c["runs"] == 1 else "s") if isinstance(c.get("runs"), int) else "")
             for c in sorted(cats, key=tok, reverse=True)]
    return "%s tokens in the log: %s." % ("{:,}".format(int(total)), ", ".join(parts))


def summary_line(out):
    """One line a payer can paste into an email."""
    m = out["manifest"]
    w = m.get("window") or [None, None]
    reasons = verdict_reasons(out)
    return "%s%s: %s, %s UTC. %s." % (
        "DEMO, records replayed: " if out.get("replayed") else "", out["verdict"].upper(), clean(m.get("title") or "untitled report", 80), _window_utc(w),
        clean(reasons[0], 300)[:1].upper() + clean(reasons[0], 300)[1:])


def _window_utc(w):
    """The window as checked, converted to UTC (a manifest may carry any offset)."""
    from .billcheck import window_text
    try:
        return window_text([_parse(w[0]).isoformat(), _parse(w[1]).isoformat()])
    except (TypeError, ValueError, AttributeError, IndexError):
        return "%s to %s" % (clean(str((w or ["?"])[0]))[:16], clean(str((w or ["?", "?"])[-1]))[:16])


def render_receive(out):
    m = out["manifest"]
    mark = {True: "PASS", False: "FAIL", None: "SKIP"}
    lines = ["vawr receive %s" % clean(os.path.basename(out["bundle"])), ""]
    w = m.get("window") or [None, None]
    lines.append("Report: %s, %s UTC%s" % (
        m.get("title") or "untitled", _window_utc(w),
        ", projects %s" % clean(", ".join(m["only_projects"])) if m.get("only_projects") else ""))
    if out.get("key_checked"):
        name = ((out.get("check") or {}).get("sessions") or {}).get("actor") or {}
        if out.get("replayed"):
            lines.append("Anthropic's records: REPLAYED from responses saved %s UTC (vawr demo), not fetched live"
                         % clean(out["replayed"], 20))
        lines.append("API key checked: %s%s%s" % (out["key_checked"], " (%s)" % clean(name["api_key_name"])
                                                  if name.get("api_key_name") else "",
                                                  "; the bundle names %s" % m["key_id"]
                                                  if m.get("key_id") and m["key_id"] != out["key_checked"] else ""))
    lines.append("")
    c = out["chain"]
    lines.append("%s  chain        %d entries, head %s%s" % (mark[c["ok"]], c["entries"], (c["head"] or "")[:16],
                                                       "; " + clean(c["problems"][0]) if c["problems"] else ""))
    r = out["report"]
    lines.append("%s  report       %s" % (mark[r["ok"]], "rebuilt from the log: same tokens per category"
                                         if r["ok"] else clean(r.get("note") or "differs from the log: %s"
                                                               % r["differences"], 400)))
    co = out["continuity"]
    lines.append("%s  continuity   %s" % (mark[co["ok"]], co["short"]))
    if co["ok"] is False or "no API key" in (co.get("note") or ""):
        lines.append("        " + co["note"])
    if co.get("unseen_previous"):
        lines.append("        the team says its previous report had head %s…, which you haven't received here"
                     % co["unseen_previous"][:16])
    res = out.get("check")
    if res is None:
        lines.append("SKIP  bill         %s" % (clean(out.get("provider_error") or "", 300) or
                                                "set ANTHROPIC_ADMIN_KEY (yours, for the account that owns the key) "
                                                "to check against Anthropic's records"))
    else:
        for line in check.render(res).splitlines():
            if line.startswith(("PASS  bill", "FAIL  bill", "SKIP  bill", "PASS  sessions", "FAIL  sessions",
                                "SKIP  sessions", "NOTE  sessions", "        ", "          ")):
                lines.append(clean(line, 400))
        s = res.get("sessions")
        if isinstance(s, dict) and s.get("ok") is not False and any(
                d.get("status") in ("pass_so_far", "pending") for d in s.get("days") or []):
            lines.append("        the last day isn't over: run `vawr receive` again an hour after it ends (UTC) "
                         "for the final count")
    if out.get("unchecked_tokens"):
        lines.append("NOTE  %s tokens in this report are marked as Claude subscription or unknown billing; no "
                     "Anthropic record you can read covers them" % "{:,}".format(out["unchecked_tokens"]))
    if out.get("window_open"):
        lines.append("NOTE  the report's window hasn't ended yet; usage after now can't be checked")
    if out.get("settling"):
        lines.append("NOTE  the window ended less than %d minutes ago; Anthropic's records for its last minutes may "
                     "not be in yet: run `vawr receive` again after that" % (SETTLE.total_seconds() // 60))
    lines += ["", VERDICTS[out["verdict"]] if not (out.get("replayed") and out["verdict"] == "verified")
              else "VERIFIED  checked against Anthropic's records as saved for this demo (replayed)"]
    why = verdict_reasons(out)
    text = clean("; ".join(why), 600)
    lines.append(("Why: " + text if out["verdict"] != "verified" else text[:1].upper() + text[1:]) + ".")
    usage = usage_line(out.get("rebuilt_report"))
    if usage:
        lines.append("Usage: " + usage)
    lines.append("Summary: " + summary_line(out))
    other = [x for x in out.get("log_contents") or [] if m.get("only_projects")
             and x["project"] not in m["only_projects"]]
    if other:
        lines.append("The log also holds %d session(s) from other projects, which the report leaves out."
                     % sum(x["sessions"] for x in other))
    lines.append("Figures: the report rebuilt from the log (--html writes it as a page); the team's own "
                 "report.html in the bundle is not checked.")
    return "\n".join(lines)


def receive_html(out, title=None):
    """A fresh page built on the recipient's machine from the log itself and the
    recipient's own checks (not the page the team sent)."""
    from . import html_report
    rep = dict(out["rebuilt_report"] or {"categories": [], "log": {}})
    rep["log"] = dict(rep.get("log") or {}, path="log.jsonl")
    res = dict(out["check"]) if out.get("check") else {
        "window": out["manifest"].get("window") or [None, None], "chain": out["chain"], "coverage": None,
        "bill": {"reason": out["provider_error"]} if out.get("provider_error") else None, "sessions": None}
    res["chain"] = out["chain"]
    res["coverage"] = None  # only the team can run it, on its own session files
    res["continuity"] = out["continuity"]
    sess = (out.get("check") or {}).get("sessions")
    res["level"] = ("failed" if out["verdict"] == "failed" else
                    "tamper-evident" if (out.get("check") or {}).get("bill") is None else
                    "provider-unconfirmed" if not (isinstance(sess, dict) and sess.get("ok") is True) else "provider")
    res["verdict"] = out["verdict"]
    res["only_projects"] = out["manifest"].get("only_projects")
    res["verdict_reasons"] = verdict_reasons(out)
    res["checked_by"] = "the recipient, on their own machine" + (
        " with their own Admin key" if out.get("check") else "")
    if out.get("replayed"):
        res["checked_by"] = ("vawr demo, on this machine, with Anthropic's records REPLAYED from responses saved "
                             "%s UTC (not fetched live)" % clean(out["replayed"], 20))
        res["replayed"] = out["replayed"]
        title = "DEMO (Anthropic's records replayed): " + (title or out["manifest"].get("title") or "Agent usage report")
    return html_report.render(rep, check=res, title=title or out["manifest"].get("title") or "Agent usage report")
