# method-scout

A Claude Code skill for answering "how do the real experts in this field do this?" — using theses, review articles, formal standards and practitioners' published material rather than blog posts and GitHub stars.

## The problem

Ask an AI agent how a professional problem "is usually done" and you tend to get a fluent survey of methods that doesn't tell you what to change, cites a few things nobody re-read, quietly drops the original authors' caveats, and turns single anecdotes into norms. The expensive errors also come late: in the numbers the main thread derives while synthesising, not in the search.

This skill fixes the shape of the work:

- **Frame first**: split the decision into 3–6 sub-questions, type each (missing method / parameter / data / precedent) and mark the **bottleneck**, so the search budget goes where the decision is actually stuck.
- **Baseline before search**: write down how you do it now, so the result is a **"we do X → the field does Y → change / don't" difference list**, not an encyclopedia.
- **One sub-agent per sub-question**, with mandatory quote anchors (verbatim sentence + page, including the number's scope), a stop condition, and a PDF fetcher that refuses bot-check pages disguised as PDFs.
- **Two separate grades** on every source: evidence grade (did the main thread actually read it?) and source tier (how reliable is the source type?).
- **Four checks on synthesised numbers**: two-level sensitivity for directional claims, decomposed deltas, labelled scenario parameters, independent magnitude check of self-derived formulas.
- **Closing fact-check** on atomic claims, recorded in the report's frontmatter; reusable methods are filed as short **method cards** so they can be found again.

## Files

| File | What it is |
|---|---|
| `SKILL.md` | The procedure Claude follows |
| `report_template.md` | Report skeleton with all required sections |
| `check_report.py` | Checks a report for required sections, the `review` field, leftover placeholders and listed method cards. Standard library only |
| `fetch_pdf.py` | curl download with a `%PDF` content check, plus an optional headless-browser fallback (Playwright) |

## Usage

Install the plugin, optionally set `METHOD_SCOUT_DIR` (default: `./method-scout` in the working directory) to where reports and method cards should live, then ask e.g. "what is the professional way to choose a maintenance interval for this equipment? Find it in standards and the literature, not on GitHub."

It works best with a fact-checking reviewer agent installed (for example `research-verifier` from this repository's `review-agents` plugin) and, optionally, a register of settled constraints (the `decision-registry` skill in `agent-governance`).

## Limits

- It is expensive: several parallel research sub-agents plus a closing review. Use it for questions that feed a real decision, not for single-fact lookups.
- Coverage is limited to what can be read online; paywalled standards and many non-English theses end up in the gap list, not in the answer.
- Evidence rules reduce, but do not eliminate, errors; the fact-checker also misses things and should be spot-checked.
- The heuristics (stop after 5 fruitless searches, 3–6 sub-questions, ≤25-line method cards) are working defaults, not calibrated values.

Part of [claude-skills](../../../../). MIT — see the repository root [`LICENSE`](../../../../LICENSE).
