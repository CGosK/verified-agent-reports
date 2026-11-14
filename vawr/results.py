"""Turn the files in work/results/ into one Markdown summary for the report."""

import json
import os

from . import paths

RESULTS = os.path.join(paths.WORK, "results")


def _load(name):
    path = os.path.join(RESULTS, name)
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


def _fmt(r):
    if not r or not r.get("n"):
        return "n/a"
    return "%d/%d (%.0f%%; 95%% CI %.0f–%.0f%%)" % (
        r["k"], r["n"], 100 * r["rate"], 100 * r["ci95"][0], 100 * r["ci95"][1])


def render():
    out = ["# Validation results", ""]
    tamper = _load("tamper_summary.json")
    if tamper:
        out += ["## Tampered log copies", "",
                "Each trial edits a copy of the finished log. Rates are trials caught out of trials run.", "",
                "| Tamper | Trials | Chain check | Session-file check | Provider check | Any check |",
                "| --- | --- | --- | --- | --- | --- |"]
        for kind, row in sorted(tamper["summary"].items()):
            out.append("| %s | %d | %s | %s | %s | %s |" % (
                kind, row["trials"], _fmt(row["chain"]), _fmt(row["sessions_on_requests"]),
                _fmt(row["provider_on_sprint_requests"]), _fmt(row["any"])))
        out += ["", "Session-file and provider rates count only trials that touched API requests "
                "(and, for the provider, requests on the Sprint key). Baseline flags on the untouched log: %s."
                % tamper["baseline_flags"], ""]
    ff = _load("false_flags.json")
    if ff:
        p = ff["provider"]
        out += ["## Untouched final log (includes the planted off-log runs)", "",
                "Session-file check: %d requests in session files but not in the log (the planted runs that kept session files). "
                "Provider check: %d of %d minutes clean, %d gap events, %d log-excess events."
                % (len(ff["sessions"]["missing_from_log"]), p["clean_minutes"], p["minutes_checked"],
                   len(p["gaps"]), len(p["log_excess"])), ""]
        shares = [v["background_share"] for v in p.get("per_session", {}).values()
                  if v["background_share"] is not None and not v["span_shared"]]
        if shares:
            out += ["Background request's share of provider tokens in each logged session's own minutes: "
                    "%.1f%%–%.1f%% over %d sessions (`provider.per_session` in false_flags.json)."
                    % (100 * min(shares), 100 * max(shares), len(shares)), ""]
    off = _load("off_log.json")
    if off:
        out += ["## Off-log runs", "",
                "| Run | Plant | Model | Provider check | Session-file check | Gap tokens | Share of nearby tokens |",
                "| --- | --- | --- | --- | --- | --- | --- |"]
        for r in off["runs"]:
            if not r["plant"]:
                continue
            share = "%.0f%%" % (100 * r["share_of_window"]) if r["share_of_window"] is not None else "n/a"
            out.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                r["task"], r["plant"], r["model"], "caught" if r["provider_flag"] else "missed",
                "caught" if r["session_flag"] else ("no files" if r["plant"] == "off_log_no_files" else "missed"),
                format(r["gap_tokens"], ","), share))
        logged = [r for r in off["runs"] if not r["plant"]]
        out += ["", "Logged Sprint-key runs wrongly flagged by the provider check: %d of %d."
                % (sum(r["provider_flag"] for r in logged), len(logged)), ""]
    cl = _load("claims_summary.json")
    if cl:
        out += ["## Claim checker", "",
                "| Case | Result |", "| --- | --- |",
                "| False \"done\" (real summary, untouched code) | %s caught |" % _fmt(cl.get("false_done_caught")),
                "| Fake blocker (named thing exists) | %s caught |" % _fmt(cl.get("fake_blocker_caught")),
                "| True blocker (named thing missing) | %s wrongly flagged |" % _fmt(cl.get("true_blocker_wrongly_flagged")),
                "| Fake blocker, held-out phrasing | %s caught |" % _fmt(cl.get("fake_blocker_caught_held_out")),
                "| True blocker, held-out phrasing | %s wrongly flagged |" % _fmt(cl.get("true_blocker_wrongly_flagged_held_out")),
                "| Denials (\"I didn't run the tests\") | %s produced a spurious claim |" % _fmt(cl.get("negations_with_spurious_claims")),
                "| Real runs with any failed claim | %s |" % _fmt(cl.get("real_runs_flagged")),
                "", "Cases where extraction found no relevant claim: %s." % cl.get("extraction_missed"), ""]
        for p in cl.get("prompted_runs", []):
            out.append("- Prompted run %s (%s): %s" % (p["task"], p["plant"], p["verdicts"]))
        out.append("")
    cc = _load("category_check.json")
    ho = _load("category_heldout.json")
    if cc or ho:
        out += ["## Category check", "",
                "A separate model (frozen prompt %s, %s) reads each run's prompt and diff and picks a "
                "category; a tag it disagrees with is flagged. Relabels retag a run to each other category."
                % ((cc or ho)["summary"]["prompt_sha"], (cc or ho)["summary"]["model"]), "",
                "| Set | Items | True tags flagged | of which contradicted | Relabels caught | Capabilities retagged as safety caught |",
                "| --- | --- | --- | --- | --- | --- |"]
        rows = []
        if cc:
            rows += [("Logged runs, development (batch 1)", cc["summary"]["dev"]),
                     ("Logged runs, held out (batch 2)", cc["summary"]["held_out_runs"])]
        if ho:
            rows += [("Written cases, clear", ho["summary"]["clear"]),
                     ("Written cases, borderline", ho["summary"]["borderline"])]
        for name, s in rows:
            n = s.get("runs", s.get("cases"))
            out.append("| %s | %d | %s | %s | %s | %s |" % (
                name, n, _fmt(s["true_tags_flagged"]), _fmt(s["true_tags_contradicted"]),
                _fmt(s["relabels_caught"]), _fmt(s["capabilities_to_safety_caught"])))
        if cc:
            out += ["", "Token shares, declared vs the model's picks (all logged runs): %s vs %s."
                    % (cc["summary"]["token_share_declared"], cc["summary"]["token_share_classified"])]
        out.append("")
    return "\n".join(out)


def write():
    text = render()
    path = os.path.join(RESULTS, "summary.md")
    os.makedirs(RESULTS, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)
    return path, text
