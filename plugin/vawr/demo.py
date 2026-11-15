"""`vawr demo`: see a payer's checks without an Admin key.

Runs `vawr receive` on three bundles from the Sprint: an honest day (VERIFIED), batch
runs with 25 runs hidden from the log (FAILED), and the honest day with one number
edited in its report (FAILED). The checks run for real on this machine; only
Anthropic's records are replayed, from responses saved once with the organization's
Admin key (`demo_data/anthropic_records.json`). Nothing is written to your ledger.

`python -m vawr.demo record` (maintainers, with the Admin key in .env) saves those
responses again, trimmed to the two sample keys: their IDs and names, their per-minute
usage and their Claude Code analytics rows. Key hints and other actors are dropped.
"""
import json
import os
import shutil
import sys
import tempfile
import urllib.parse
import zipfile
from datetime import datetime, timezone

from . import bundle, usage_api

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_data")
RECORDS = os.path.join(DATA, "anthropic_records.json")
HONEST = os.path.join(DATA, "full-day.zip")
HIDDEN = os.path.join(DATA, "batch-runs-with-hidden.zip")
HONEST_KEY = "apikey_01ACxYY1jehtHaxqdPihHsqV"  # the day test's key; the batch bundle names its own


def _key(path, params):
    items = sorted((k, v) for k, v in (params or {}).items())
    return "%s?%s" % (path, urllib.parse.urlencode(items, doseq=True))


def _trim(path, data, names, ids):
    """Keep only what the demo's two keys need."""
    if not isinstance(data, dict):
        return data
    data = dict(data)
    if path.endswith("/api_keys"):
        data["data"] = [{"id": k.get("id"), "name": k.get("name"), "status": k.get("status")}
                        for k in data.get("data") or [] if k.get("id") in ids]
        data["has_more"], data["first_id"], data["last_id"] = False, None, None
    elif "claude_code" in path:
        data["data"] = [r for r in data.get("data") or []
                        if ((r.get("actor") or {}).get("api_key_name")) in names]
    return data


def record(out=RECORDS):
    """Fetch what `receive` asks for on the two sample bundles and save it."""
    from .billcheck import admin_and_key
    admin, _ = admin_and_key()
    if not admin:
        raise SystemExit("record needs ANTHROPIC_ADMIN_KEY")
    seen, real = {}, usage_api._get

    def rec(admin_key, path, params, **kw):
        data = real(admin_key, path, params, **kw)
        seen[_key(path, params)] = (path, data)
        return data
    usage_api._get = rec
    try:
        with tempfile.TemporaryDirectory() as d:
            ledger = os.path.join(d, "received.jsonl")
            bundle.receive(HONEST, admin_key=admin, key_id=HONEST_KEY, ledger=ledger, record=False)
            bundle.receive(HIDDEN, admin_key=admin, ledger=ledger, record=False)
    finally:
        usage_api._get = real
    keys = next((data for k, (p, data) in seen.items() if p.endswith("/api_keys")), {"data": []})
    with zipfile.ZipFile(HIDDEN) as z:
        hidden_key = json.loads(z.read("bundle.json")).get("key_id")
    ids = {HONEST_KEY, hidden_key}
    names = {k.get("name") for k in keys.get("data") or [] if k.get("id") in ids}
    saved = {k: _trim(p, data, names, ids) for k, (p, data) in seen.items()}
    with open(out, "w") as fh:
        json.dump({"fetched": datetime.now(timezone.utc).isoformat(timespec="minutes"), "responses": saved},
                  fh, indent=0, sort_keys=True)
    return out


def _edited_copy(src, dst):
    """The honest bundle with one usage number in report.json raised by 1,000."""
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as b:
        for name in a.namelist():
            data = a.read(name)
            if name == "report.json":
                rep = json.loads(data)
                cat = rep["categories"][0]
                cat["tokens"]["input"] += 1000
                if isinstance(cat.get("total_tokens"), int):
                    cat["total_tokens"] += 1000
                data = json.dumps(rep, indent=1).encode()
            b.writestr(name, data)
    return dst


def run(html_dir=None, out=sys.stdout):
    if not os.path.exists(RECORDS):
        raise SystemExit("vawr demo: no saved records at %s" % RECORDS)
    with open(RECORDS) as fh:
        saved = json.load(fh)
    responses = saved["responses"]

    def replay(admin_key, path, params, **kw):
        k = _key(path, params)
        if k not in responses:
            raise RuntimeError("the demo has no saved Anthropic record for %s" % k)
        return responses[k]
    real = usage_api._get
    usage_api._get = replay
    w = out.write
    w("vawr demo: what a payer sees. The checks run here, for real; Anthropic's records for these\n"
      "bundles are replayed from responses saved with our Admin key on %s UTC.\n"
      "With your own Admin key, `vawr receive <bundle>` checks live records instead.\n"
      % saved["fetched"].replace("T", " ")[:16])
    try:
        with tempfile.TemporaryDirectory(prefix="vawr-demo-") as d:
            ledger = os.path.join(d, "received.jsonl")  # never your own ledger
            edited = _edited_copy(HONEST, os.path.join(d, "full-day-edited.zip"))
            cases = [("1. An honest day: every session on a key logged (Nov 14, 2026)", HONEST, HONEST_KEY,
                      "full-day.html"),
                     ("2. Batch runs, 25 of them hidden from the log on purpose", HIDDEN, None, "batch-hidden.html"),
                     ("3. The honest day again, with one number in its report raised by 1,000", edited, HONEST_KEY,
                      "full-day-edited.html")]
            verdicts = []
            for title, path, key, page in cases:
                res = bundle.receive(path, admin_key="replay", key_id=key, ledger=ledger, record=False)
                verdicts.append(res["verdict"])
                w("\n%s\n%s\n\n%s\n" % (title, "=" * len(title), bundle.render_receive(res)))
                if html_dir:
                    os.makedirs(html_dir, exist_ok=True)
                    with open(os.path.join(html_dir, page), "w") as fh:
                        fh.write(bundle.receive_html(res))
    finally:
        usage_api._get = real
    w("\nThe bundles are in %s.%s\n" % (DATA, " Pages: %s" % html_dir if html_dir else ""))
    return verdicts


if __name__ == "__main__":
    if sys.argv[1:] == ["record"]:
        print(record())
    else:
        run()
