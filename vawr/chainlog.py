"""Append-only JSONL log in which every entry carries the SHA-256 hash of the
entry before it. Editing, deleting or reordering an entry breaks the chain.

Entry layout (one JSON object per line):
    {"seq": 0, "prev": "<64 hex>", "recv_ts": "<UTC ISO time>",
     "event": {...}, "hash": "<64 hex>"}

`hash` is SHA-256 over the canonical JSON of the other four fields.
"""

import hashlib
import json
import os
import threading
from datetime import datetime, timezone

GENESIS = "0" * 64


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entry_hash(seq, prev, recv_ts, event):
    body = {"seq": seq, "prev": prev, "recv_ts": recv_ts, "event": event}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


MAX_INT_DIGITS = 40  # token counts and sequence numbers are far shorter


def safe_int(s):
    """json parse_int hook: Python 3.9 parses a huge integer in quadratic time, so a
    crafted bundle could stall `receive`; refuse anything longer than any real count."""
    if len(s.lstrip("-")) > MAX_INT_DIGITS:
        raise ValueError("an integer with %d digits" % len(s))
    return int(s)


def loads(text):
    return json.loads(text, parse_int=safe_int)


def read_entries(path):
    """Yield (line_number, entry) for every line; raises on unparsable JSON."""
    with open(path, "r", encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                yield n, loads(line)


def last_entry(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    last = None
    for _, e in read_entries(path):
        last = e
    return last


class ChainLog:
    """Thread-safe appender. One process should own a log file at a time."""

    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._lock = threading.Lock()
        last = last_entry(path)
        self._seq = (last["seq"] + 1) if last else 0
        self._prev = last["hash"] if last else GENESIS

    def append(self, event):
        with self._lock:
            recv_ts = utc_now()
            h = entry_hash(self._seq, self._prev, recv_ts, event)
            entry = {"seq": self._seq, "prev": self._prev, "recv_ts": recv_ts,
                     "event": event, "hash": h}
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(canonical(entry) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            self._seq += 1
            self._prev = h
            return entry


def verify(path, max_problems=50):
    """Recompute the chain, reading one line at a time. Returns (ok, problems, count, head_hash)."""
    problems = []
    nproblems = 0
    prev = GENESIS
    expected_seq = 0
    count = 0
    head = GENESIS
    try:
        for line_no, e in read_entries(path):
            count += 1
            before = len(problems)
            prev, head, expected_seq = _check_entry(line_no, e, prev, head, expected_seq, problems)
            nproblems += len(problems) - before
            del problems[max_problems:]
    except (ValueError, UnicodeDecodeError) as exc:
        return False, (problems + ["unparsable line: %s" % exc])[:max_problems], count, None
    return (not nproblems), problems, count, head


def _check_entry(line_no, e, prev, head, expected_seq, problems):
    if True:
        if not isinstance(e, dict):
            problems.append("line %d: not a log entry" % line_no)
            return prev, head, expected_seq + 1
        missing = [k for k in ("seq", "prev", "recv_ts", "event", "hash") if k not in e]
        if missing:
            problems.append("line %d: missing fields %s" % (line_no, missing))
            return prev, head, expected_seq + 1
        if e["seq"] != expected_seq:
            problems.append("line %d: seq %s, expected %d" % (line_no, e["seq"], expected_seq))
        if e["prev"] != prev:
            problems.append("line %d (seq %s): prev hash does not match the entry before it"
                            % (line_no, e["seq"]))
        recomputed = entry_hash(e["seq"], e["prev"], e["recv_ts"], e["event"])
        if recomputed != e["hash"]:
            problems.append("line %d (seq %s): content does not match its hash" % (line_no, e["seq"]))
        prev = e["hash"]
        head = e["hash"]
        expected_seq = e["seq"] + 1 if isinstance(e["seq"], int) else expected_seq + 1
    return prev, head, expected_seq
