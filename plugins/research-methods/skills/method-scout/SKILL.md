---
name: method-scout
description: For a professional/industry problem, find out "how do the most expert people in this field actually do it" — theses and dissertations, review articles, formal standards and institutional guidance, and practitioners' published methods (consultants, banks, listed companies' disclosures) — and produce method cards with evidence grades, an applicability judgment, and a gap list framed as "what we do now vs. what the field does". Use when the user asks "what is the professional way to do this", "is there a standard method or workflow for X", "how do experts estimate/decide this", "don't search GitHub, find the thinking in papers and professional literature". Pairs with oss-benchmark (which looks outward for existing code/tools; this skill looks outward for methods). Not for a single fact or regulation lookup, not when the method is already known and only needs implementing, not for news/policy monitoring. It produces cards and recommendations; it does not make the final decision or set the final number.
---

# method-scout — find how the professionals do it

## 0. Paths and tools

```bash
MS_HOME="${METHOD_SCOUT_DIR:-$PWD/method-scout}"   # where your research notes live; set once
MS="$MS_HOME/reports"      # one report per question: YYYY-MM-DD-<topic>.md
SRC="$MS_HOME/sources"     # per-domain lists of targeted institutions: <domain-kebab-case>.md
METHODS="$MS_HOME/methods" # reusable method-card library: one short file per method + INDEX.md
SK="${CLAUDE_PLUGIN_ROOT}/skills/method-scout"
mkdir -p "$MS" "$SRC" "$METHODS"
```

If you keep a knowledge base, point `METHOD_SCOUT_DIR` inside it so reports and method cards are
searchable later.

| Tool | Use |
|---|---|
| `python3 $SK/fetch_pdf.py <url> <out.pdf>` | Download a PDF that curl gets blocked on. Tries curl, then a headless Chromium session (optional `playwright`). If the output name ends in `.pdf`, the content must start with `%PDF` — verification pages often come back as HTTP 200 HTML. On failure it leaves no file and exits 1; mark that source [unread] |
| `$SK/report_template.md` | Report skeleton (required sections + `review` field); `<<...>>` are placeholders |
| `python3 $SK/check_report.py <report>` | Checks that required sections/fields exist and no placeholders remain. **Does not check whether the content is right** |
| `pdftotext -layout x.pdf x.txt` | Read the source text |
| `pdftoppm -f N -l N -r 110 -png x.pdf p` then look at the image | **Numbers from tables must be checked against the page image** — text extraction merges columns |
| `https://arxiv.org/html/<id>` | arXiv papers: tables are cleaner than PDF extraction |
| Europe PMC REST `fullTextXML` endpoint | Full text for open-access biomedical papers when the web page shows a captcha |
| `file <download>` | Look at what you actually downloaded before filing it |

## 1. Objective

Given a professional problem, answer: **what methods and workflows do the most expert people in
this field use? Which fit our situation and constraints, which don't, and where are the gaps?**

The output is a report of method cards with evidence grades, with conclusions organised as a
**"what we do now vs. what the field does" difference list** — not an encyclopedia of methods.
**It does not make the final decision**; that is the user's call.

Backbone: **split into sub-questions and mark the bottleneck (Phase 0) → write down the current
baseline (Phase 1) → dispatch searches per sub-question (Phase 3) → four checks before any
calibrated number (Phase 5)**; add Phase 8 when the result is meant to change a real pipeline.
Spend the search budget where the bottleneck is, not evenly.

## 2. Red lines

Domain-specific pitfalls live in `references/` and are loaded in Phase 1 when the topic matches
(for example `references/pitfalls-<topic>.md`). None ship with the skill; add your own as you learn them.

1. **Search your own notes before the web.** Much of what a new question needs has often been
   answered before; re-researching wastes effort and invites overturning an earlier, better-checked
   conclusion by accident.
2. **Every source carries an evidence grade:** `[checked]` = the main thread read the original
   text or recomputed it itself; `[agent-read]` = a sub-agent read it, the main thread has not
   re-checked; `[abstract-only]` = only a search snippet or summary page was seen; `[unread]` =
   blocked. **`[abstract-only]` and `[unread]` may not be used as a basis** — they go in the
   "unverified" list.
3. **Check table numbers against the page image.** Text extraction silently merges adjacent columns.
4. **Star counts, blog rankings and vendor claims are not method evidence.** Law-firm
   blogs and vendor sites can at most corroborate "practitioner practice", labelled as second-hand.
5. **Say "not found" when you didn't find it.** A gap is a valid result. Never invent paper titles,
   authors or numbers. Paywalled/blocked sources mean "not covered", not "doesn't exist". **For a
   standard or document you did not read in full, write "not seen in the sources read", never
   "confirmed absent".**
6. **Parameters without empirical backing must be labelled "expert estimate"**, so no reader assumes
   statistical support.
7. **Respect the user's constraints.** If the user keeps a register of settled decisions and
   constraints (for example the decision-registry skill in this repository), list the applicable
   ones in Phase 0 and judge each method's applicability against them.
8. **Closing review, and name the main-line break.** State explicitly the link in the argument
   that is still missing (e.g. "a method exists for X and for Y, but nothing converts X into Y").
   - A fact-checking reviewer (e.g. `research-verifier` from this repository's review-agents
     plugin) **always** runs, on three parts only: the headline conclusion, the answers to the
     bottleneck sub-questions, and the difference list. Reports that get filed are later cited as
     settled; "internal only" is not low-risk.
   - An argument-structure reviewer runs **when the report supports a concrete decision** (pick an
     option, set a value, change a tool or standard) or goes outside; a pure landscape survey may
     skip it.
   - **Skipping is written down:** the frontmatter `review` field records each review as passed
     or skipped with a reason. A report without it is unfinished.
9. **Check the basis, not only the source.** Many errors are "right number, wrong scope": the
   sample, the stage, or the applicability range was different. Matching "institution – year –
   number" catches misattribution but not this; read the sentence the number came from.
10. **Keep the original author's hedges.** If the source says "limitation", "secondary signal",
    "single case", that goes into the card's limitations column verbatim. Dropping hedges during
    synthesis inflates the conclusion.
11. **The main thread must re-check its own writing.** Numbers checked during reading drift while
    writing the report ("planned" becomes "built", "inside the boundary" becomes "on site", two
    copies of the same table are counted as two independent sources). After each card, re-check
    four things: planned vs. done, who did it, which column, same origin or independent.
    Sources listed as "unverified, do not cite" may not support any conclusion in the body.
12. **Before concluding "lost / doesn't exist / never had", check the recoverable places:** session
    transcripts, git history, backups, archives.
13. **Numbers produced in synthesis get four checks** (Phase 5). The errors reviewers catch mostly
    appear when the main thread draws conclusions, not while it reads sources.

## 3. Workflow

### Phase 0 — Frame the question (**user confirms**)

Write one paragraph and have the user confirm:
1. **The decision it supports** (e.g. "choose a service interval for a fleet of pumps").
2. **Object and stage** (technology, geography, lifecycle stage) and **what is excluded**.
3. **Applicable constraints** from the user's register, if any.
4. **Sub-questions and the bottleneck.** Split the decision into 3–6 sub-questions and type each:
   - `missing method`: don't know what framework/workflow the field uses;
   - `missing parameter`: the framework is clear, but there is no citable benchmark value;
   - `missing data`: a class of raw data or a data source is needed;
   - `missing precedent`: real projects, transactions or approvals are needed.
   Mark the **bottleneck**: the 1–2 sub-questions the decision depends on most and that are least
   answered. Spend the search budget there first. Method questions are often the easiest to answer
   and rarely where the decision is actually stuck.
5. **Success criterion**: a workflow skeleton? a method survey? a benchmark range for one parameter?

Show the sub-question table (Q1…Qn | sub-question | type | bottleneck?) with the above. If anything
is vague, ask — don't guess.

### Phase 1 — Deduplicate against what you already have

If the topic matches a `references/pitfalls-*.md` file, read it first.

Search your own notes (`$MS`, your knowledge base, decision logs) for the same topic. A hit means
**cite the path, don't redo it**, and write "already have X; this round only adds Y".

**Search two ways:** (1) method terms; (2) **the names, units and typical values of the key
parameters** in the question. Searching only method vocabulary misses pages that would be found
instantly by the parameter's unit.

Also read project notes and meeting minutes and list **conflicts** (files of different dates
saying opposite things). This skill doesn't resolve them; put them in report §0 for the user.

**Write the current baseline** (mandatory, before §0 of the report):
1. **How we do it now**: which tools, scripts, standards and past reports already cover this
   (name files/sections), or what our default assumption is. If nothing, write "none".
2. **Status per sub-question**: `have` (answered already; cite the path, don't search) | `partial`
   (say which piece is missing) | `blank`. Only `partial`/`blank` go to Phase 3.
3. If a bottleneck sub-question turns out to be `have`, go back to Phase 0 and re-mark.

Reports without a baseline read like method encyclopedias: after reading them nobody knows what
to change.

### Phase 2 — Translate into the field's vocabulary

Rewrite the user's business wording into **the standard terms of the field's literature** before
searching (e.g. "how often should we service these pumps" → reliability-centred maintenance,
preventive maintenance interval optimisation, Weibull analysis, failure-mode criticality).
**List terms per sub-question** (3–6 per sub-question, in English and local languages if
relevant), including synonyms and neighbouring fields (e.g. aviation maintenance programmes,
medical-device reliability). For `missing parameter` sub-questions the list must
include the parameter's name, unit and usual written forms, not only method vocabulary.

**Reverse-engineer vocabulary:** search with the narrowest terms until you find 2–3 clearly relevant
documents; harvest the authors' own terms from their titles, keywords, classification codes and
abstracts; expand and search again. Stop when no new terms appear (usually 1–2 rounds).

### Phase 3 — Parallel search per sub-question (2–4 sub-agents, dispatched in one message)

**Split the work by sub-question, not by source type.** Each sub-agent owns 1–2 sub-questions that
are still `partial`/`blank` and covers academic, standards and practitioner sources for them; **the
bottleneck sub-question gets its own agent.** Ask for ≤1500 words, only sources actually accessed,
each with an evidence grade. Splitting by source type makes every agent skim the whole topic and
leaves the key sub-question without an owner.

Few sub-questions (one parameter, one country) → 2 agents are enough. Don't send `have`
sub-questions out again to fill a quota. Record the token cost in the run log.

**Source map** — in each dispatch, say which source types to try first for its sub-question type
(`missing method`: academic reviews + standards; `missing parameter`: standards/institutional
reports + practitioner disclosures such as annual reports, investor presentations, regulatory
filings; `missing data`: institutional data portals + practitioners; `missing precedent`:
practitioners + regulator/court public records):

| Source class | Look for | Typical sources |
|---|---|---|
| **Academic** | Theses, reviews (a review or a thesis literature chapter is a ready-made map), core researchers | OpenAlex, CORE, OATD, Semantic Scholar, university repositories |
| **Standards** | Formal standards and institutional guidance, industry association disclosures, frameworks usable as a workflow skeleton | Standards bodies, professional institutes, international agencies, listed companies' investor days and annual reports |
| **Practitioners** | The people and firms actually doing it, downloadable primary material, consensus and disagreement | Consultants', banks' and operators' public articles and interviews, conference proceedings, association reports |

Two supplementary strategies are **on by default**; skipping them needs a written reason:
- **Academic dispatches:** start from 1–3 reviews or thesis literature chapters, then snowball one
  round **backward** (their references) and **forward** (who cites them, via OpenAlex / Semantic
  Scholar cited-by).
- **Practitioner dispatches:** first read `$SRC/<domain>.md`, the targeted list of institutions,
  and check each site; append newly found high-value institutions (create the file if missing).
  One line per institution: name | URL | what it publishes | last used for which report.
- Each source records **how it was found** (keyword search / snowballing / targeted institution /
  other), so you can later tell which strategies pay off.

Sub-agents return **method cards**: **sub-question (Q number)** | method name | problem it solves |
core idea | inputs | key assumptions | how it is validated | limitations (**author's hedges
verbatim**) | applicable here? and why | source (author / year / institution / URL / evidence grade
/ **source tier** / how found).

**Source tier** (adapted from the three-tier grey-literature model of Garousi et al. 2019, with
peer review listed separately): `peer` = peer-reviewed papers, theses | `tier 1` = formal standards,
government and international agency reports, white papers | `tier 2` = annual reports, investor
presentations, news, conference talks | `tier 3` = blogs, vendor sites, forum claims. Practitioner
sources also get `insider` (a party to the decision or transaction) or `outsider` (consultant,
analyst). Source tier and evidence grade are different things — the grade says whether the main
thread read it, the tier says how reliable the source is. **Record both; don't merge them into one
score.**

**Five things every dispatch must contain:**
1. **Quote anchors**: every number, year and attribution in a card comes with a ≤2-sentence
   verbatim quote + URL + page/section/table. **The quote must include the number's sample, stage
   or scope**; if the source doesn't state it, write "scope not stated in source". No anchor →
   the agent self-grades `[abstract-only]`.
2. **Source quality and downloads**: download PDFs **only** with `fetch_pdf.py` (it rejects
   verification pages disguised as PDFs); agents told merely where the script is will still
   curl directly. Prefer the institution's original page, the journal/arXiv original, the
   standard's text; SEO content sites and search-engine AI summaries are leads, never numbers.
3. **Stop condition**: "stop after N consecutive searches (default 5, a working heuristic) that
   produce no new method or source, and report the state at stopping". Searching repeatedly for a
   source that doesn't exist is a known failure mode.
4. **Applicable constraints**: paste the user's applicable settled constraints (id + one line);
   methods that conflict are marked "conflicts with <id>, not applicable" rather than recommended.
5. **Owned sub-questions and baseline**: the Q numbers, their type, whether bottleneck, and the
   relevant baseline paragraphs; ask for **only what is new relative to the baseline** ("same as
   current practice" in one line). `missing parameter` questions must return value + scope +
   quote anchor, not just a method name.

Don't write specific paper titles or years from memory into a dispatch — give topic terms; a
remembered title that doesn't exist sends an agent hunting for it.

**When academic APIs rate-limit:** add `&mailto=<your email>` to OpenAlex requests (polite pool)
and honour `retryAfter`; otherwise fall back to web search on publisher pages and scholar
"cited by" pages. Note the unavailable API under coverage gaps.

**Write the stopping rule into the report**, per sub-question, one of: theoretical saturation (no
new methods appear) / bounded effort (top N per sub-question) / evidence exhausted — with the state
at stopping. **"Exhausted" alone is not allowed**; say what the last rounds searched and why more
is unlikely to turn up anything.

### Phase 4 — Main thread re-reads the key sources

Sub-agent conclusions are **not accepted as is**. For each card you intend to use:
1. Fetch the original with `fetch_pdf.py` and read it with `pdftotext`;
2. **Compare against the anchor item by item**: institution, year, number, **sample/stage/scope**.
   Any mismatch → don't upgrade (keep or downgrade to `[abstract-only]`), and note it in the
   report's methodology notes;
3. Check table numbers against the page image, and **read the whole table**, not only the cell the
   agent quoted; read the hedge sentences next to any new number;
4. Recompute what can be recomputed;
5. Upgrade to `[checked]`; what you couldn't read keeps its grade.

### Phase 5 — Calibrate with your own data (if any)

Ask: "for the key inputs of these methods, do we have real data to calibrate them?" If yes,
calibrate and **state which part of the problem the calibration covers and which it doesn't**. If
no, say so and list the data needed.

Calibration usually means scenario comparisons (change a threshold or parameter, see what moves).
This is where the main thread errs most. Before writing any numeric conclusion, run four checks:
1. **Directional claims need at least two sensitivity levels**: a claim like "capacity will go
   down" is written only if two sourced parameter values give the same direction; if the direction
   flips, write "direction depends on X" with both numbers.
2. **Decompose every delta**: split the difference between scenario and baseline by which parameter
   changed and give each contribution; don't attribute a delta to the parameter you were thinking
   about.
3. **Label each scenario parameter's source and nature**: which card it came from, and whether it
   is a standard value / manufacturer spec / UI example / single-project value / our own choice.
   Parameters with no source don't enter scenarios. (A value from an example for one product type
   silently reused for another is a classic error.)
4. **Check self-derived formulas with an independent tool**: if an inference rests on a formula or
   conversion you derived, check its order of magnitude with an independent implementation (an
   open-source library, a second derivation) before writing.

### Phase 6 — Applicability filter and convergence

1. Each card gets "applicable / partial / not applicable + reason" against the Phase 0 constraints,
   **and a certainty rating high / medium / low** for the card's conclusion as a whole (in the
   spirit of GRADE-CERQual), with one sentence on each of:
   - methodological limitations of the underlying sources;
   - coherence: do sources agree? write out conflicts, don't force a reconciliation;
   - adequacy: how many independent sources? **single source or single case → at most "medium"**;
   - relevance: how far the sources' industry, geography and stage are from this problem.
   A card can be all `[checked]` and still "low" certainty — the two are independent.
2. **Separate fact from inference** in card bodies (as in analytic tradecraft standards such as
   ICD 203): "what the source says" and "what we infer from it" are separate paragraphs; inference
   sentences start with "Inference:".
3. Choose 1–2 methods as the **workflow skeleton** and say why; the rest are supporting or excluded.
4. **Gap list**: what wasn't found, which databases weren't covered, what the user must supply
   (paywalled standards, local-language theses). **Final status per sub-question**: `answered` |
   `partial` (what's missing) | `unanswered`. For an unanswered bottleneck, say what is still
   needed and where to look next.
5. **Difference list** against the Phase 1 baseline, line by line: "we now do X → the field does Y
   → change / don't change + reason". Practices that already match are merged into one sentence.
   The "we now" column **quotes specific baseline entries** (file/section), not a paraphrase from
   memory.
6. Closing review per red line 8; record results in the frontmatter `review` field. Give the
   fact-checker only the headline, bottleneck answers and difference list, and ask it to **split
   them into atomic claims first** (one number / year / attribution / quotation each), judging each
   "supported / partial / not supported + anchor" (the atomic-claim approach of FActScore/SAFE).
   Automated checking also misses things; spot-check its verdicts.

### Phase 7 — File it

1. **Keep the originals** you downloaded (non-reproducible primary documents especially) in
   whatever archive you use, and note the location at the top of the report.
2. **Write the report** to `$MS/YYYY-MM-DD-<topic>.md`, **starting from a copy of
   `$SK/report_template.md`**, then run `python3 $SK/check_report.py <report>`; it must pass. It
   contains: **sub-question table and baseline** (before the conclusions), conclusions first (as the
   difference list), method cards, practitioner consensus and disagreement, local calibration, the
   **unverified — do not cite** list, coverage gaps and next round, methodology notes, and:
   - the **stopping rule** (Phase 3);
   - **relation to earlier conclusions**: each headline marked "new / consistent with earlier /
     corrects earlier (say which sentence of which report)".
   `check_report.py` only checks that required sections and fields exist and placeholders are
   gone. Passing it says nothing about correctness.
3. **Write method cards (mandatory).** A report is a one-off long document that is hard to find
   again; what is reusable is the methods. For each "applicable/partial" method with certainty ≥
   medium, write an **independent short card** (≤25 lines) at `$METHODS/<method-kebab-case>.md`:
   ```markdown
   ---
   summary: <one sentence: what problem it solves and how — phrased the way someone would search for it>
   tags: [method, <domain>, <generic scenario words>]
   scenarios: [<2-3 other situations where it applies>]
   certainty: high|medium
   source_report: reports/YYYY-MM-DD-<topic>.md
   updated: YYYY-MM-DD
   ---
   # <method name, written as an action>
   **When to use**: <trigger, one or two sentences>
   **How**: 1. … 2. … 3. … (3–6 steps you can follow directly)
   **Pitfalls / limits**: <key points of the author's own hedges>
   **Source**: <URL + evidence grade>; details in source_report
   ```
   - **Write it as a general method, not as this question's answer**: no project names in title
     or summary, so other situations find it.
   - **Deduplicate first** (`grep -ril <keyword> $METHODS`); if the method exists, add a source and
     scenario to that card and bump `updated`.
   - **No confidential specifics** (project names, sites, coordinates, amounts) in cards.
   - Add/update a row in `$METHODS/INDEX.md` (method | one line | scenarios | certainty | report).
   - End report §1 with the line "Method cards added this round: <file names>" (or "none" + reason).
   - If you have a search index over your notes, re-index so the cards are findable immediately.
4. **Run log**: fill the report's last section with what is automatically known (agents, tokens,
   time, extra rounds, errors caught by the fact-checker). Leave "adopted" empty until the user acts
   on a recommendation (or explicitly declines) — judge usefulness by what the user does, not by
   asking them to fill in a survey.

### Phase 8 — Implementation check (optional; when the difference list targets a real pipeline)

The report stops at "what to change". When a change is actually going into a pipeline, most of the
value is here:
1. **Map to code**: each "change" in the difference list → file:line and config field. Read the
   project's own issue log/backlog first; if the topic is already there, advance that item instead
   of opening another.
2. **Read-only prototype**: in a scratch directory, reproduce the current behaviour with the
   project's own functions and quantify the proposed change's effect; don't modify project files.
3. **Independent re-check**: have a reviewer (data validator or code-evidence checker) recompute
   the prototype numbers; fix what they find before proposing.
4. **Propose, then wait**: an opt-in proposal (off by default, official outputs untouched, a control
   run reproducing current results), with the inputs the user must decide. Implementation follows
   the project's own rules once approved.
If the object is a whole pipeline to be fixed item by item to convergence, use audit-closeout
instead.

## 4. Reporting back

The user may not read the full report. The summary fits on one screen, in a fixed order; everything
else stays in the report file.

About 20 lines at most:

```
**One-line conclusion**: <how far the bottleneck was answered + the recommendation>

**Do next** (≤3, by priority)
1. <what> —— <why, one sentence> —— <cost/effort>
2. …

**Needs your decision** (≤2, or "none"; each with a recommended option)
- <question>? Recommended: <option>, because <one sentence>

**Method cards filed** (findable and reusable later)
- `<card file>`: <one line>

**Corrections and open items**: <errors corrected, sub-questions still open; or "none">
Report: `<path>`
```

- Don't restate the process, the source list or the evidence table in the summary.
- Don't end with survey questions to the user. Judge the skill from the run log: were
  recommendations adopted (the user's next actions), how many errors the fact-checker caught, what
  errors surfaced later. After about three runs, decide how to change the skill on five criteria —
  answered? correct? used? saved effort? cost the user time? — outcomes, not rule compliance.
