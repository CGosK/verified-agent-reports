# Sunday tasks (Nov 15)

**Deadline:** Sun Nov 15, 11:59 PM AoE = Mon Nov 16, 01:59 HST (11:59 UTC). Aim to submit by **20:00 HST Sunday**. A resubmission must use the exact same title.

**Who:** **C** = Claude in this session; **You** = Chris.

## 0. When the laptop opens (C, about 30 minutes)

- [ ] Collect what ran while the laptop was closed:
    - [ ] **Full-day test** (`work/daytest/`): bundle, receive and team outputs. Expect VERIFIED. Nov 14 UTC has closed by then, so re-run `vawr receive` for the final whole-day sessions result.
    - [ ] **Claude Code 2.1.325 re-test** (`work/results/version_2_1_325.json`): does the unrecorded request still follow the desktop entrypoint, and do the bill and coverage checks still pass? Re-measure the background allowance if it moved.
    - [ ] **Midnight session** (`work/midnight/`): ran Saturday, or is due at 13:58 HST Sunday. Once Anthropic's records land (about an hour later), see how a session that spans midnight UTC is split across days, and fix the sessions check if needed.
- [ ] Fold the results into `work/results/summary.md`, the README table and the outline (as suggestions).
- [ ] Summarize for you in five lines.

## 1. Quality checks (C, morning)

- [ ] Fact-check every number added since the last fact-check, with a separate agent, against the result files: sessions check, continuity, underperformance, full day, 2.1.325, funder guide.
- [ ] Regenerate `report/tables.md` from the result files, with rows for the new checks.
- [ ] Clean-machine walkthrough: a fresh `VAWR_HOME` and config folder, follow the README word for word (setup, start, tag, a session, check, bundle, receive). Fix every step that doesn't work as written.
- [ ] Plugin: install it from the repo's marketplace into a separate config folder and run every `/vawr:` command, including the new `bundle`, `receive` and `team`.
- [ ] Full test suite; plugin copy in sync; nothing secret in the repo (keys, `.env`, config folders).

## 2. Independent review (C starts them in parallel, morning)

- [ ] **Code review** of everything since the last review: the outcome column, the underperformance plant and hidden tests, the version and midnight harness, the interactive changes. Fixes go in with tests.
- [ ] **Security re-check** of `vawr receive`: confirm the ten fixes hold, and try new attacks with crafted bundles.
- [ ] **Judge's read:** a reviewer who hasn't seen our work scores the outline (with the suggestions accepted) on Apart's three criteria and names the weakest claims. Repeat on your draft in the afternoon.

## 3. Tool improvements (C, time-boxed to 2 hours, after the reviews)

- [ ] Report page: show the level, the outcome column and the sessions check clearly; check it at phone width and in print.
- [ ] Speed on a large log (a synthetic 100,000-entry log) for `check`, `bundle` and `receive`.
- [ ] Error messages and first-run output: every failure says what to do next.
- [ ] Anything the reviews or the walkthrough turn up.
- [ ] Optional, your call: Codex and OpenAI support (needs Codex installed and OpenAI keys in `.env`).

## 4. Paper (You write; C supports)

- [ ] **You:** accept or reject the suggestions in the Report outline tab.
- [ ] **You:** write the paper on the template (4–8 pages) from the outline and `report/tables.md`.
- [ ] **C:** Figure 1 and the tables from the result files; page-count check.
- [ ] **C:** fact-check your draft against the results and list any number or claim it can't source.
- [ ] Required appendix, Limitations and Dual-Use, updated: subscription usage, the scope of the underperformance test, the versions tested, one operator and one machine.
- [ ] LLM usage statement; "what predates the sprint: nothing".
- [ ] Optional: a 3–5 minute demo video. C writes the script and a terminal sequence: bill check, bundle, receive VERIFIED, a hidden run FAILED.
- [ ] **You:** submit by 20:00 HST.

## 5. After submitting (your decisions)

- [ ] Make the repo public; post the two drafts in `docs/drafts/`; whether to approach Apart as the first funder to use it; the tool's name.
- [ ] Delete the `vawr-daytest` key in the Console once the final results are in.
