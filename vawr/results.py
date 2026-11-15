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
            if r["plant"] not in ("off_log", "off_log_no_files"):
                continue
            share = "%.0f%%" % (100 * r["share_of_window"]) if r["share_of_window"] is not None else "n/a"
            out.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                r["task"], r["plant"], r["model"], "caught" if r["provider_flag"] else "missed",
                "caught" if r["session_flag"] else ("no files" if r["plant"] == "off_log_no_files" else "missed"),
                format(r["gap_tokens"], ","), share))
        logged = [r for r in off["runs"] if r["plant"] not in ("off_log", "off_log_no_files")]
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
    up = _load("underperform.json")
    if up:
        su, hs = up["summary"], (up.get("hidden_tests") or {}).get("summary") or {}
        out += ["## Weaker work, told to hide it (planted)", "",
                "Safety tasks run with an instruction to do a deliberately partial job and describe it in general "
                "terms, without mentioning tests, failures or what was left out (`prompt_underperform`), plus "
                "same-time controls. Summaries read by hand.", "",
                "- Planted runs whose work fails the task's tests: %s" % _fmt(su.get("planted_tests_fail")),
                "- Of those, the summary disclosed it anyway: %s" % _fmt(su.get("weak_runs_disclosed_in_summary")),
                "- Of those it hid, flagged by the claim checker: %s" % _fmt(su.get("covert_weak_runs_flagged_by_claim_checker")),
                "- All weak runs flagged by the claim checker: %s; controls flagged: %s; controls passing their tests: %s"
                % (_fmt(su.get("weak_runs_flagged_by_claim_checker")), _fmt(su.get("claim_checker_flags_controls")),
                   _fmt(su.get("controls_tests_pass"))),
                "- Hidden tests: normal safety runs passing them %s; planted runs that passed the visible tests but "
                "fail the hidden ones %s" % (_fmt(hs.get("normal_runs_pass_hidden")),
                                             _fmt(hs.get("planted_passing_visible_but_failing_hidden"))),
                ""]
    dt = _load("daytest_received.json")
    if dt:
        ck = dt.get("check") or {}
        b = ck.get("bill") or {}
        days = (ck.get("sessions") or {}).get("days") or []
        comp = [d for d in days if d.get("complete")]
        out += ["## Full day on a separate key (payer's receive)", "",
                "Key %s, bundle received with the organization's Admin key. Days compared: %s." % (
                    (dt.get("manifest") or {}).get("key_id"),
                    ", ".join("%s (%s)" % (d["day"], d["status"].replace("_", " ")) for d in days) or "none"), "",
                "- Verdict: %s" % dt.get("verdict"),
                "- Bill: %s tokens billed, %s unexplained, %d minute(s) of log excess" % (
                    "{:,}".format(sum((b.get("provider_tokens") or {}).values())),
                    "{:,}".format(sum(sum(g["tokens"].values()) for g in b.get("gaps") or [])),
                    len(b.get("log_excess") or []))]
        for d in days:
            out.append("- Sessions, %s (%s): Anthropic %d, log %d, token difference %s" % (
                d["day"], d["status"].replace("_", " "), d["anthropic_sessions"], d["log_sessions"],
                d["token_difference"] or "none"))
        out.append("")
    ver = _load("version_2_1_325.json")
    if ver and ver.get("ab"):
        be, c = ver["ab"]["by_env"], ver["check"]
        out += ["## Claude Code %s (the environment A/B again)" % ver["claude_version"], "",
                "- Unrecorded small-model request: %d of %d runs in the desktop app's environment (cache read %s), "
                "%d of %d clean" % (be["inherited"]["with_unrecorded_request"], be["inherited"]["runs"],
                                     be["inherited"]["cache_read_values"], be["clean"]["with_unrecorded_request"],
                                     be["clean"]["runs"]),
                "- Checks over the window: chain %s, session files %s, bill %s (%d gaps, %d excess), level %s" % (
                    "intact" if c["chain_ok"] else "BROKEN", "pass" if c["coverage"]["ok"] else "FAIL",
                    "pass" if c["bill_ok"] else "FAIL", len(c["gaps"] or []), len(c["log_excess"] or []), c["level"]),
                ""]
    tt = _load("telemetry_off_test.json")
    if tt:
        tb = _load("telemetry_off_bisect.json") or {}
        out += ["## Can a team switch off Anthropic's session count?", "",
                "Nov 15, main key, one-line sessions marked by terminal name; none sent telemetry to vawr.", "",
                "- Control (defaults, TERM=vt100): %s of 2 counted" % tt.get("control_vt100_counted"),
                "- DISABLE_TELEMETRY=1 and CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 (TERM=vt220): %s of 2 counted"
                % tt.get("telemetry_off_vt220_counted"),
                "- Billed in that minute, all four sessions: %s Haiku tokens" % "{:,}".format(
                    sum(sum(t.values()) for mv in (tt.get("billed_08_43_to_08_46") or {}).values() for t in mv.values()))]
        if tb:
            out += ["- Only DISABLE_TELEMETRY=1 (TERM=vt52): %s of 2 counted" % tb.get("only_DISABLE_TELEMETRY_vt52_counted"),
                    "- Only CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 (TERM=vt320): %s of 2 counted"
                    % tb.get("only_CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC_vt320_counted"),
                    "- Billed in that minute, all four: %s Haiku tokens (checked %s UTC, %d minutes after the "
                    "sessions; the first test's controls appeared within an hour)" % (
                        "{:,}".format(sum(sum(t.values()) for mv in (tb.get("billed_09_49_to_09_52") or {}).values()
                                          for t in mv.values())),
                        (tb.get("checked_at") or "")[11:16], _minutes_after(tb.get("checked_at"), "09:50"))]
        logged = [(name, _load("telemetry_off_otel_%s.json" % name)) for name in
                  ("disable_telemetry", "nonessential", "control")]
        if all(r for _, r in logged):
            out += ["", "Does vawr still log such a session? One headless session each, OpenTelemetry to a scratch "
                    "receiver:", ""]
            labels = {"disable_telemetry": "Only DISABLE_TELEMETRY=1",
                      "nonessential": "Only CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1",
                      "control": "Control (neither)"}
            for name, r in logged:
                out.append("- %s: %d session and %d API request logged" % (
                    labels[name], len(r.get("log_sessions") or {}), r.get("api_requests") or 0))
            th = _load("telemetry_off_headless.json")
            if th:
                billed = sum(sum(m.values()) for minute in (th.get("billed_11_22_to_11_25") or {}).values()
                             for m in minute.values())
                n = th.get("non_interactive_counted")
                out.append("- Anthropic's count of these three headless sessions: %s of %s, %s (checked %s UTC, "
                           "about an hour after)" % (
                               n, th.get("headless_sessions_run"),
                               "the control" if n == 1 else "where only the control was expected",
                               th.get("checked_at", "")[11:16]))
                out.append("- Billed on the key 11:22–11:25 UTC, while the three ran: %s Haiku tokens"
                           % format(billed, ","))
            out += ["", "So an honest team with either setting has more in its log than Anthropic counted. The "
                    "sessions check reports such a day as uncounted: not a failure, but not VERIFIED."]
        out.append("")
    ct = _load("continuity_trials.json")
    if ct:
        out += ["## Continuity (relabel and rebuild after an earlier report)", "",
                "%d trials on a copy of %s (%d entries): an earlier report's head at a random point, one API "
                "request relabeled at a random point and the chain rebuilt." % (ct["trials"], ct["log"], ct["entries"]), "",
                "- Edits at or before the earlier head caught: %s" % _fmt(ct["caught_before_earlier_head"]),
                "- Edits after it caught (by design, none): %s" % _fmt(ct["caught_after_earlier_head"]), ""]
    return "\n".join(out)


def _minutes_after(checked_at, hhmm):
    try:
        h, m = int(checked_at[11:13]), int(checked_at[14:16])
        return (h * 60 + m) - (int(hhmm[:2]) * 60 + int(hhmm[3:]))
    except (TypeError, ValueError):
        return 0


def write():
    text = render()
    path = os.path.join(RESULTS, "summary.md")
    os.makedirs(RESULTS, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)
    return path, text
