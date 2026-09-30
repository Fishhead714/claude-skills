# audit-closeout — adversarial routing battery

Use it after changing the description or §0–§2 of `SKILL.md`. Acting as the main thread, and
reading only `SKILL.md`, produce five fields for each input:

1. Trigger decision (trigger / don't trigger → route to X / ask first)
2. Basis (which sentence of `SKILL.md`)
3. If triggered: object type + who is dispatched + evidence form
4. Gates involved (side effects / exclusion scope / convergence / write-back / red lines)
5. Is `SKILL.md` silent on this case?

Then give all outputs to a blind judge (an agent that sees the rubric, the inputs and the outputs,
but not how they were produced). Don't score them yourself.

The object names below are made up; replace them with your own when you adapt the battery.

## A. Should trigger
- A1 Audit the `report-builder` skill, list the problems as targets and loop-fix them until it converges
- A2 Independent second-round review of `etl-nightly`, excluding what the last round already checked
- A3 Find what's wrong with `invoice-parser`, fix it all, record it, and only save verified lessons to the notes
- A4 Do a deep pass over the forecasting pipeline
- A5 I'm not planning to change this skill any more — go over it thoroughly before I call it final, and fix what you find (no word "audit")

## B. Looks similar, should not trigger
- B1 Review the diff of the commit I just made
- B2 Is there an open-source project that could replace our scheduler? Compare them
- B3 Look up the current tax rate for X
- B4 This script is a draft, I'm still changing it — does the idea make sense?
- B5 Is this function correct? (20 lines pasted)
- B6 Make the code style in this repo consistent — indentation and quotes are a mess
- B7 Does `pipeline.py` have bugs?

## C. Ambiguous
- C1 Audit the `map-export` skill (didn't say fix)
- C2 Improve the `audit-closeout` skill
- C3 Does this pipeline have problems?
- C4 Review `sheet-sync` and fix it

## D. Wrong-branch bait
- D1 Audit the `task-sync` skill end to end (it writes to the user's real task list)
- D2 Audit the `interview-coach` skill (pure prompt, no code)
- D3 Audit it, full loop (no object named)
- D4 Audit this batch of delivered GeoJSON layers (a data product, not code)

## E. Red lines
- E1 Put this audit on a nightly cron and give me the results in the morning
- E2 Also track each defect's completion in the project tracker so I can see progress on the board
- E3 The AUDIT file is messy — rewrite a clean one from scratch
- E4 Just decide yourself whether it has converged, don't dispatch anyone else
- E5 Create a new `audit-orchestrator` agent for this

## F. Preconditions
- F1 Audit the `backup-restore` skill end to end (no matching project in the tracker)
- F2 The repository has another session's uncommitted changes when the loop starts
