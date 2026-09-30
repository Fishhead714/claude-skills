---
name: audit-closeout
description: Run a full closed-loop audit on something that already exists and is in use (a calculation pipeline, a skill or tool library, a data product, a script collection) — independent audit → numbered, severity-graded defects → fix one by one until full regression is clean for consecutive rounds → verified knowledge written back. Use when the user says "audit X, turn the problems into targets and loop-fix them until it converges", "do an independent second-round review of X, excluding what the last round covered", "find what's wrong with X, fix it, record it", "deep-audit this pipeline". Not for a single diff/PR/branch review (use a code-review command), not for looking outward for alternative open-source implementations (use oss-benchmark), not for drafts that are still changing daily, lint-level style issues, or one-off "is this function right?" questions.
---

# audit-closeout — audit, grade, fix to convergence, write back

## 0. Your role

**You are the orchestrator on the main thread.** The whole value of this loop comes from one
property: *the author of the thing under audit does not judge it.* Auditors, fixers and the final
verifier should be different parties as far as possible.

Sub-agents usually cannot dispatch further sub-agents. That is why this procedure lives in a
skill (run by the main thread) rather than inside a single "optimizer" agent: one agent cannot
call in a data validator, a fact-checker and a blind judge.

If the object is a single skill with executable code and the user only wants one round of
improvement, a single improvement agent is cheaper. If the object is **pure prompt** (nothing
executable), a blind judge is mandatory (see §2), so use this skill even for "just improve this
skill".

## 1. Pin the object and the intent, then read the history

**Pin the object to a directory or file path first.** For requests that don't name one ("is this
pipeline OK?", "go over everything"), ask for the path before starting — this loop dispatches
several agents and writes files into the object's directory; a wrong guess wastes a whole round.

**Two levels of intent:** "I just want the defect list" → delivering `AUDIT-*.md` finishes the job
and §5 does not start. "Fix it until it converges" → open the loop after the AUDIT file is final.
If the user only said "audit it", treat it as list-only and ask before changing anything.

First action: **read every existing `AUDIT-*.md` in the object's directory.**

- The previous round's "checked, confirmed fine (don't re-investigate)" goes straight into this
  round's exclusion scope.
- The previous round's "could not verify" items are this round's priority candidates.
- State at the top of this round's AUDIT file: "This round excludes A1–An / B1–Bn".

Skipping this step means repeating a whole round of work and re-reporting already-settled issues
as new findings.

## 2. Choose the checkers (the path forks on object type here, then merges)

The object type decides who audits and what counts as evidence:

| Object | Who audits (role) | What counts as evidence |
|---|---|---|
| Engineering / numeric pipeline | a data-validation reviewer, optionally plus a code-evidence checker | Reproduced numbers: same input, one parameter changed, both results side by side |
| Data product (layers, delivered JSON, registers) | data-validation reviewer + code-evidence checker | Recompute from the generating script and inputs; compare field by field with the delivered values |
| Code / script library | a code reviewer + a silent-failure reviewer | file:line plus the smallest input that triggers the defect |
| Pure prompt / nothing executable | an auditor who produces a rubric + adversarial scenarios + raw outputs, **handed back to you**, then a blind judge | The judge's independent score — never the auditor's self-assessment |
| Tool that calls external APIs | code reviewer, **after the side-effect gate** | Real call results |
| Knowledge base content / metadata | a curator-type reviewer, optionally plus a code-evidence checker for the indexing scripts | Counts from direct file traversal and check-script output — not the "feel" of search results |
| Infrastructure / automation channels (cron, fan-out, sync) | an infrastructure diagnostician, optionally plus a silent-failure reviewer | Log timestamps, heartbeats and **evidence of the last real success** — a crontab entry is not evidence |

If you installed the review-agents plugin from this repository, `code-reviewer` and `research-verifier`
fill two of these roles; any read-only reviewer agent with a clear brief works for the rest.

**Every dispatch states the evidence form**, not just who to send. Without it, what comes back
cannot be judged true or false. **Objects that span types go under their main type**; only stack
the combinations the table names — don't invent new ones.

**Scope code reviewers to a file set.** Most code reviewers are designed for diffs; an audit
usually has no diff. Narrow to specific modules/files and dispatch in batches. Open-ended "is
there anything systematically wrong across the codebase" questions go to reviewers built to scan
wide (silent-failure hunting, claim-by-claim code evidence).

**Side-effect gate (mandatory for objects with external APIs):** real calls can write the user's
real data (task managers, online spreadsheets, cloud sync services). Before running, confirm you
are on a sandbox account or a reversible target, and count quota usage into the round budget.
No sandbox → no real write calls; use read-only calls plus constructed inputs.

## 3. Number and grade defects in `AUDIT-YYYY-MM-DD.md`

### 3.0 Writing it down is **your** job, not the auditors'

Reviewer agents should be read-only (no Write/Edit) — a verifier that quietly fixes things is
grading its own work. The consequence: **their conclusions exist only in the message they return
to you. If you don't write them down, they are gone when the session ends.**

- Write each reviewer's conclusion to disk as soon as it arrives; don't wait to be asked.
- "Nothing found" **is written down too** — it becomes exclusion scope so the next round doesn't
  re-check it (§1).
- An audit reported only in chat is, for all practical purposes, an audit that never happened.
  The typical symptom: half of every later round is spent rediscovering what an earlier round
  already settled.

### 3.1 Where to write it

| Object | Location |
|---|---|
| Has its own directory (skill / repo / pipeline dir) | `AUDIT-YYYY-MM-DD.md` in that directory ← default |
| Already has an issue ledger (e.g. an "open issues" page with numbering and status) | Append to that ledger instead; don't create a second, differently formatted one |
| Spans several machines/repos, no single home | The directory of whatever started the audit; failing that, `docs/audits/AUDIT-<object>-YYYY-MM-DD.md` |

The value of an audit trail comes from "findable next time", not from "uniform format". If an
existing ledger can hold it, put it there.

Format (see `AUDIT_TEMPLATE.md`):

- Three severities: **Critical** (directly affects delivered numbers/conclusions), **Medium**,
  **Low / latent**.
- Each item: symptom → root cause (with file:line) → reproduction → blast radius.
- Three closing sections, none optional: "Checked and confirmed fine (don't re-investigate)",
  "Could not verify", "Excluded from this round".

**Always append** to `AUDIT-*.md`; rewriting the whole file wipes out the previous round's
exclusion scope.

"Could not verify" exists for the next round and for knowledge write-back — **without it,
second-hand conclusions get used as if verified.**

## 4. Project tracker: risks and pointers only (optional)

If you keep a project tracker, register **risks** ("[Critical] one-line defect + measured number,
see AUDIT-YYYY-MM-DD.md") and a one-line round summary. Don't create a tracker project just to
register an audit — that adds an empty shell nobody will move forward.

**The single source of truth is each defect's status in `AUDIT-*.md`, not the tracker.** Keep
per-item completion in one place only; two copies of the same status always drift, and the
tracker's checkbox turns green before the deliverable does.

## 5. Loop until convergence

Fix item by item → **run the full regression every round** (not just the failing item) →
converged only after N consecutive fully clean rounds. Default N = 2, hard cap 5 rounds.

- Hit the cap without converging: **say it did not converge**, list what remains. Don't blur it
  into "done".
- Every fix comes with a regression assertion that reproduces the original defect; otherwise a
  later change silently undoes it.
- **Root cause or patch?** For each fix, judge whether it changes the design/structure that
  caused the defect, or adds a special case that hides the symptom. Symptom-only fixes are
  recorded in `AUDIT-*.md` as "containment, not a cure" and **do not count toward a clean round**
  — the same root cause will resurface through another input and be miscounted as new.
  This judgment belongs to whoever runs the final regression, not the fixer.
- The final full regression is **run by a party that did not do the fixes.** Setting the goal,
  dispatching the fixes and declaring convergence yourself is self-review.
- **Sampled outcomes need repeated passes.** For outputs that vary run to run (pure-prompt skill
  outputs, end-to-end agent runs), each case in a counted round must pass k independent runs
  (pass^k, default k = 3). Deterministic scripts and unit tests need one run. When you send
  outputs to a blind judge, send all k — don't pick.

Before the loop and while it runs:

```bash
git -C <repo> status --short     # start only when clean; if another session has WIP, commit with explicit paths only
```

Several sessions editing the same repository at once is a real failure mode.

## 6. Write-back: only verified knowledge goes into the knowledge base

1. Tool defects stay in the object's directory. Only reusable, cross-project decisions (a unit
   convention, a method choice) are write-back candidates.
2. Label each candidate **primary** / **secondary** / **self-reproduced**. **Anything not checked is
   secondary by default.**
3. Secondary items go to a fact-checking reviewer as **source checks** ("does this document/clause
   exist, and does it really say this?"). Self-reproduced items you re-run yourself — a web
   fact-checker cannot execute anything.
4. Only verified items are written back. Items that fail or cannot be checked carry "unverified"
   **in the body text**, not in a footnote. If your knowledge base has a search index, re-index
   after writing; a page on disk that search can't find is not written back.
5. Before writing, read the target page — **resolve conflicts, don't list two values side by side.**

## 7. Red lines

- **No unattended scheduled audits.** Any step may need a human decision (which convention to
  adopt, whether to accept a degradation). A cron job would write undecided things into products
  while no one is watching. For long runs use an in-session loop with a human present, and keep the
  convergence state in `AUDIT-*.md` so anyone can pick it up by hand.

  This rule is about **audits**, not **checks**. The line:

  | | May be scheduled | Must not be scheduled |
  |---|---|---|
  | What it is | **Check**: pure script, zero LLM/agent calls | **Audit**: dispatches agents, judges, grades |
  | Effect on the object | Read-only | Modifies it |
  | Output | Logs and alerts only | Writes to `AUDIT-*.md`, registers, deliverables |
  | Judgment | None that needs a human | Any step may need a human |

  One-sentence test: **will downstream treat its output as settled?** Yes → don't schedule it.
- **Don't create new agents for this.** Auditors, blind judges and verifiers already exist; what
  is usually missing is orchestration.
- At gates (round cap hit, verification failed, a defect affects already-delivered numbers),
  notify the user actively; don't make them poll.

## 8. After editing this file, run the self-check

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/audit-closeout/check_skill.py
```

This file is almost entirely "who to dispatch, which command, which file". A dangling reference
only blows up after something has been dispatched. `check_skill.py` checks that every backticked
agent/skill/command name exists in your Claude Code setup, that relative paths resolve, and that a
count written in prose ("three severities") matches the table right after it.

**The self-check cannot test routing** — whether the skill triggers and which branch it takes.
For that, run the adversarial cases in `BATTERY.md` and have a blind judge score the outputs.
Re-run it after changing the description or §0–§2.
