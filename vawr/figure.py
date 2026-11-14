"""Figure 1: where the provider's tokens went, minute by minute, for the API
key. Each bar is the provider's record for that minute, split into tokens the
hash-chained log accounts for, the harness's known background request, and the
unmatched remainder the auditor flags. Off-log runs are shaded (from run
manifests, for the reader only; the auditor never reads them). Plain SVG."""

import json
import os
from datetime import timedelta

from . import paths
from .auditor import check_provider, minute_of, parse_ts
from .logdata import api_requests

W, H = 980, 440
LEFT, RIGHT, TOP, BOTTOM = 70, 20, 44, 92
MATCHED, BACKGROUND, GAP, OFFLOG, INK, GRID = "#2b6cb0", "#a0aec0", "#c0392b", "#fbe3e0", "#222", "#e2e2e2"


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _nice_max(v):
    """Smallest round axis top with at most six steps."""
    for step in (1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000):
        if v <= step * 6:
            top = -(-int(v) // step) * step
            return max(top, step), step
    return v, v / 5


def build(window, provider_minutes, out_path, manifest_dir=paths.MANIFESTS, log_path=paths.LOG_PATH):
    start, end = window
    res = check_provider(api_requests(log_path), start, end, provider_minutes=provider_minutes)
    per = {parse_ts(k): v for k, v in res["per_minute"].items()}
    minutes = []
    m = minute_of(start)
    while m < end:
        minutes.append(m)
        m += timedelta(minutes=1)
    ymax, step = _nice_max(max([1] + [v["provider"] for v in per.values()]))
    pw, ph = W - LEFT - RIGHT, H - TOP - BOTTOM
    bw = pw / max(1, len(minutes))
    x = lambda i: LEFT + i * bw
    y = lambda v: TOP + ph - (v / ymax) * ph

    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
           'font-family="Helvetica, Arial, sans-serif" font-size="12">' % (W, H, W, H),
           '<rect width="100%" height="100%" fill="white"/>']
    for name in sorted(os.listdir(manifest_dir)):
        man = json.load(open(os.path.join(manifest_dir, name)))
        if man.get("mode") != "sprint" or man.get("plant") not in ("off_log", "off_log_no_files"):
            continue
        s, e = minute_of(parse_ts(man["start"])), minute_of(parse_ts(man["end"]))
        if s not in minutes:
            continue
        i0 = minutes.index(s)
        i1 = minutes.index(e) if e in minutes else i0
        svg.append('<rect x="%.1f" y="%d" width="%.1f" height="%d" fill="%s"/>' % (x(i0), TOP, (i1 - i0 + 1) * bw, ph, OFFLOG))
        svg.append('<text x="%.1f" y="%d" font-size="10" fill="%s" text-anchor="middle">%s</text>'
                   % (x(i0) + bw / 2, TOP - 8, GAP, "off-log" if man["plant"] == "off_log" else "off-log, no files"))
    v = 0
    while v <= ymax:
        svg.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="%s"/>' % (LEFT, W - RIGHT, y(v), y(v), GRID))
        svg.append('<text x="%d" y="%.1f" text-anchor="end" fill="%s">%s</text>' % (LEFT - 6, y(v) + 4, INK, format(int(v), ",")))
        v += step
    for i, mm in enumerate(minutes):
        d = per.get(mm)
        if not d:
            continue
        base = 0
        for value, color in ((d["matched"], MATCHED), (d["background"], BACKGROUND), (d["gap"], GAP)):
            if value:
                svg.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>'
                           % (x(i) + bw * 0.15, y(base + value), bw * 0.7, y(base) - y(base + value), color))
                base += value
    for i, mm in enumerate(minutes):
        if mm.minute % 5 == 0:
            svg.append('<text x="%.1f" y="%d" text-anchor="middle" fill="%s">%s</text>' % (x(i) + bw / 2, TOP + ph + 18, INK, mm.strftime("%H:%M")))
    svg.append('<line x1="%d" x2="%d" y1="%d" y2="%d" stroke="%s"/>' % (LEFT, W - RIGHT, TOP + ph, TOP + ph, INK))
    svg.append('<text x="%d" y="%d" fill="%s">Provider-recorded tokens per minute on the API key (UTC)</text>' % (LEFT, TOP + ph + 40, INK))
    lx, ly = LEFT, H - 18
    for j, (color, label) in enumerate(((MATCHED, "Matched by the hash-chained log"),
                                        (BACKGROUND, "Harness background request (one per logged session)"),
                                        (GAP, "Unmatched: flagged as work off the log"))):
        xx = lx + [0, 230, 590][j]
        svg.append('<rect x="%d" y="%d" width="12" height="12" fill="%s"/><text x="%d" y="%d" fill="%s">%s</text>'
                   % (xx, ly - 11, color, xx + 16, ly, INK, _esc(label)))
    svg.append("</svg>")
    with open(out_path, "w") as fh:
        fh.write("\n".join(svg))
    return out_path, res
