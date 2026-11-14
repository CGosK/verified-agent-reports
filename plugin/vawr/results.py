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
        bbs = p.get("background_by_session") or {}
        per = p.get("per_session") or {}
        shares = []
        for sid, b in bbs.items():
            bg = sum(b.values())
            if b.get("cache_read", 0) >= 7010 and sid in per:
                shares.append(bg / (bg + sum(per[sid]["logged_tokens"].values())))
        if shares:
            out += ["Background request credited to %d of %d logged sessions; %.1f%%–%.1f%% of each such session's "
                    "billed tokens (`provider.background_by_session` in false_flags.json; approximate where sessions "
                    "overlap)." % (len(shares), len(bbs), 100 * min(shares), 100 * max(shares)), ""]
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
    conc = _load("concurrency.json")
    if conc:
        out += ["## Concurrency (overlapping runs)", "",
                "Each window ran three logged runs at once; half also ran an off-log run among them. "
                "Per-minute provider records can't tell runs in the same minute apart, so the unit is a window.", "",
                "- Off-log windows flagged: %s" % _fmt(conc["off_log_windows_flagged"]),
                "- Clean windows flagged: %s (%d logged sessions in clean windows)"
                % (_fmt(conc["clean_windows_flagged"]), conc["logged_sessions_in_clean_windows"]), "",
                "| Window start | Runs | Off-log run (model, own tokens) | Flagged | Gap tokens |",
                "| --- | --- | --- | --- | --- |"]
        for w in conc["windows"]:
            off = "; ".join("%s %s, %s" % (o["plant"], o["model"], "{:,}".format(o["own_tokens"]))
                            for o in w["off_log"]) or "none"
            out.append("| %s | %d | %s | %s | %s |" % (w["start"][11:19], w["runs"], off,
                                                       "yes" if w["flagged"] else "no",
                                                       "{:,}".format(w["gap_tokens"])))
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
                     ("Logged runs, held out (all later runs)", cc["summary"]["held_out_runs"])]
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
    cca = _load("cc_analytics.json")
    if cca:
        out += ["## Anthropic's Claude Code analytics vs the log and the bill", "",
                "Anthropic's Claude Code Analytics API (Admin API) counts each API key's Claude Code sessions "
                "and tokens by model, per UTC day and terminal type. Key %s (%s)." % (cca["key_name"], cca["key_id"]), "",
                "| Day | Terminal | Anthropic's sessions | Log's sessions | Result | Tokens, Anthropic minus log |",
                "| --- | --- | --- | --- | --- | --- |"]
        for d, v in sorted(cca["days"].items()):
            for c in v["comparison"]["by_terminal"]:
                out.append("| %s | %s | %d | %d | %s | %s |" % (
                    d, c["terminal"], c["anthropic_sessions"], c["log_sessions"], c["status"].replace("_", " "),
                    ", ".join("%s %+d" % (m, x) for m, x in sorted(c["token_difference"].items())) or "none"))
        out.append("")
        for d, v in sorted(cca["days"].items()):
            out.append("- %s: %d runs on the key in the manifests, %d of them hidden from the log; billed minus "
                       "Anthropic's count: %s." % (d, v["sprint_key_runs_in_manifests"], v["hidden_runs_in_manifests"],
                                                   ", ".join("%s %+d" % kv for kv in sorted(v["billed_minus_anthropic"].items()))
                                                   or "none"))
        out.append("")
    ct = _load("continuity_trials.json")
    if ct:
        out += ["## Continuity (relabel and rebuild after an earlier report)", "",
                "%d trials on a copy of %s (%d entries): an earlier report's head at a random point, one API "
                "request relabeled at a random point and the chain rebuilt." % (ct["trials"], ct["log"], ct["entries"]), "",
                "- Edits at or before the earlier head caught: %s" % _fmt(ct["caught_before_earlier_head"]),
                "- Edits after it caught (by design, none): %s" % _fmt(ct["caught_after_earlier_head"]), ""]
    return "\n".join(out)


def write():
    text = render()
    path = os.path.join(RESULTS, "summary.md")
    os.makedirs(RESULTS, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)
    return path, text
