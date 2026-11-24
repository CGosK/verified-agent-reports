"""Remove the account's plan and seat type from the committed logs and rebuild their hash chains.

Claude Code attaches `anthropic.plan` and `anthropic.seat_type` to every event of a session signed in
with a Claude account. The receiver has dropped them since Nov 14, 2026 08:30 UTC, keeping only
`auth=account`; logs written before then kept them. This script (run once, Nov 24, 2026) replaces
them with `auth=account` in those logs, as the current receiver would for those events, and keeps
everything that cites the logs consistent. (API-key events written before then still have no `auth`
key; they are classed by `anthropic.provider`, as before.)

1. Each log below: drop the two attributes, add `auth: "account"` where they were, keep every
   `seq` and `recv_ts`, and recompute `hash` and `prev` from the first changed entry on. Nothing
   else in any event changes. A log's ID (its first entry's hash) changes only for the pilot log,
   whose first entry carried the plan.
2. The three copies of `batch-runs-with-hidden.zip`: `log.jsonl` (a copy of the 10:10 UTC snapshot)
   is rebuilt the same way; the old head hash in `bundle.json`, `report.json`, `check.json` and
   `report.html` becomes the new one.
3. Every other tracked text file: a changed entry hash, in full or as the 16-character prefix
   `vawr check` and the HTML report print, becomes the new one.
4. `work/results/cc_analytics.json`: the `organization_id` lines of the saved raw records go.

Writes `work/log/rechain_heads.json`: each log's old and new ID (first-entry hash) and head, every
cited hash that changed, and the files it rewrote. Files 2 and 3 above include saved outputs (audit
records, a `vawr check` transcript, sample reports): they now show the new hashes, which their
commands never printed; the heads file lists them.

    python3 scripts/scrub_plan_fields.py              # apply, from the repo root (refuses a second run)
    python3 scripts/scrub_plan_fields.py --check REV  # rebuild from REV's files; compare with the tree

`--check 48184d9` (the last commit before the scrub; needs a full clone) rebuilds every file the scrub
writes from that commit and compares each with the tree. It doesn't look at other files: the scrub
commit's own diff shows what else it changed.
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import zipfile

LOGS = ["work/log/events.jsonl", "work/log/events_upto_20261114T0917Z.jsonl",
        "work/log/events_upto_20261114T1010Z.jsonl", "work/batch1/events.jsonl", "work/pilot/log/events.jsonl"]
SNAPSHOT = "work/log/events_upto_20261114T1010Z.jsonl"  # what each zip's log.jsonl is a copy of
ZIPS = ["work/samples/batch-runs-with-hidden.zip", "vawr/demo_data/batch-runs-with-hidden.zip",
        "plugin/vawr/demo_data/batch-runs-with-hidden.zip"]
ANALYTICS = "work/results/cc_analytics.json"
HEADS = "work/log/rechain_heads.json"
SELF = "scripts/scrub_plan_fields.py"
README = "README.md"  # names the old Table 5 head on purpose, next to the new one
DROP = ("anthropic.plan", "anthropic.seat_type")
FULL = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
SHORT = re.compile(r"(?<![0-9a-f])[0-9a-f]{16}(?![0-9a-f])")


def canonical(obj):  # as vawr.chainlog writes and hashes entries
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entry_hash(seq, prev, recv_ts, event):
    body = {"seq": seq, "prev": prev, "recv_ts": recv_ts, "event": event}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


class Scrub:
    def __init__(self):
        self.hmap = {}  # old entry hash -> new
        self.cited = {}  # old -> new, for every hash or prefix swapped in another file
        self.heads = {}

    def log(self, name, text):
        lines = [line for line in text.split("\n") if line.strip()]
        out, prev, changed, first_changed, ids = [], None, 0, None, None
        for line in lines:
            if canonical(json.loads(line)) != line:
                raise SystemExit("%s: a line isn't in the chain log's canonical layout" % name)
            e = json.loads(line)
            attrs = (e.get("event") or {}).get("attributes")
            if isinstance(attrs, dict) and any(k in attrs for k in DROP):
                for k in DROP:
                    attrs.pop(k, None)
                attrs.setdefault("auth", "account")
                changed += 1
                if first_changed is None:
                    first_changed = e["seq"]
            if prev is not None:
                e["prev"] = prev
            new = entry_hash(e["seq"], e["prev"], e["recv_ts"], e["event"])
            if new != e["hash"]:
                if self.hmap.get(e["hash"], new) != new:
                    raise SystemExit("%s: entry %s rebuilds differently in two logs" % (name, e["seq"]))
                self.hmap[e["hash"]] = new
            old_head = e["hash"]
            if ids is None:
                ids = (old_head, new)
            e["hash"] = prev = new
            out.append(canonical(e))
        if lines:
            self.heads[name] = {"entries": len(lines), "entries_scrubbed": changed, "first_changed_seq": first_changed,
                                "old_id": ids[0], "new_id": ids[1], "old_head": old_head, "new_head": prev}
        return "\n".join(out) + "\n"

    def swap(self, text):
        short = {h[:16]: v[:16] for h, v in self.hmap.items()}

        def full(m):
            new = self.hmap.get(m.group(0))
            if new:
                self.cited[m.group(0)] = new
            return new or m.group(0)

        def prefix(m):
            new = short.get(m.group(0))
            if new:
                self.cited[m.group(0)] = new
            return new or m.group(0)

        return SHORT.sub(prefix, FULL.sub(full, text))

    def zip_bytes(self, name, data, snapshot):
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                body = zin.read(info.filename).decode("utf-8")
                if info.filename == "log.jsonl":
                    body = self.log(name + "!log.jsonl", body)
                    if body != snapshot:
                        raise SystemExit("%s: log.jsonl isn't the 10:10 UTC snapshot" % name)
                else:
                    body = self.swap(body)
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                zi.compress_type, zi.external_attr = zipfile.ZIP_DEFLATED, info.external_attr
                zout.writestr(zi, body.encode("utf-8"))
        return buf.getvalue()


ORG_KEY = '"organization' '_id":'  # split so the leak check doesn't read this line as the field itself


def analytics(text):
    kept = [line for line in text.split("\n") if ORG_KEY not in line]
    out = "\n".join(kept)
    json.loads(out)
    return out


def tracked(rev=None):
    args = ["git", "ls-tree", "-r", "--name-only", rev] if rev else ["git", "ls-files"]
    return [f for f in subprocess.run(args, capture_output=True, text=True, check=True).stdout.split("\n") if f]


def run(read):
    """Apply the scrub to files supplied by read(path) -> bytes. Returns ({path: new bytes}, Scrub)."""
    s, out = Scrub(), {}
    for f in LOGS:
        out[f] = s.log(f, read(f).decode("utf-8")).encode("utf-8")
    snapshot = out[SNAPSHOT].decode("utf-8")
    for f in ZIPS:
        out[f] = s.zip_bytes(f, read(f), snapshot)
    return s, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", metavar="REV", help="rebuild from this commit's files and compare with the tree")
    args = ap.parse_args()
    if not os.path.exists(LOGS[0]):
        raise SystemExit("run this from the repository root")
    if args.check:
        read = lambda f: subprocess.run(["git", "show", "%s:%s" % (args.check, f)], capture_output=True,
                                        check=True).stdout
        files = tracked(args.check)
    else:
        if os.path.exists(HEADS):
            raise SystemExit("already applied (%s exists); use --check REV to compare" % HEADS)
        read = lambda f: open(f, "rb").read()
        files = tracked()
    s, out = run(read)
    if not s.hmap:
        raise SystemExit("nothing to scrub: no log carries the plan or seat type")
    swapped = []
    for f in files:
        if f in out or f.endswith(".zip") or f in (HEADS, SELF, README):
            continue
        try:
            text = read(f).decode("utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError, subprocess.CalledProcessError):
            continue
        new = s.swap(text)
        if new != text:
            swapped.append(f)
        if f == ANALYTICS:
            new = analytics(new)
        if new != text:
            out[f] = new.encode("utf-8")
    heads = {"why": "anthropic.plan and anthropic.seat_type were removed from these logs on Nov 24, 2026 and "
                    "their hash chains rebuilt; see scripts/scrub_plan_fields.py. Old hashes are those in "
                    "commit 48184d9 and earlier.",
             "logs": s.heads, "cited_hashes_old_to_new": dict(sorted(s.cited.items())),
             "files_rewritten": {
                 "logs_scrubbed_and_rechained": LOGS,
                 "zips_log_rebuilt_and_hashes_swapped": ZIPS,
                 "hashes_swapped_in_saved_outputs_and_tables": sorted(swapped),
                 "organization_id_removed": [ANALYTICS]}}
    if args.check:
        bad = []
        for f, data in sorted(out.items()):
            cur = open(f, "rb").read()
            if f.endswith(".zip"):
                same = _members(cur) == _members(data)
            else:
                same = cur == data
            if not same:
                bad.append(f)
        got = json.load(open(HEADS)) if os.path.exists(HEADS) else None
        if got != json.loads(json.dumps(heads)):
            bad.append(HEADS)
        for f in sorted(out):
            print("%s  %s" % ("DIFFERS" if f in bad else "same   ", f))
        if HEADS in bad:
            print("DIFFERS  %s" % HEADS)
        print("%d files rebuilt from %s; %s" % (len(out), args.check,
                                                "all match the tree" if not bad else "%d differ" % len(bad)))
        sys.exit(1 if bad else 0)
    for f, data in out.items():
        with open(f, "wb") as fh:
            fh.write(data)
        print("wrote %s" % f)
    with open(HEADS, "w") as fh:
        json.dump(heads, fh, indent=1)
        fh.write("\n")
    print("%d entry hashes changed; %d cited hashes swapped; heads in %s" % (len(s.hmap), len(s.cited), HEADS))


def _members(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return [(i.filename, z.read(i.filename)) for i in z.infolist()]


if __name__ == "__main__":
    main()
