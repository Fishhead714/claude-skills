---
name: oss-benchmark
description: Search GitHub for open-source projects on a topic, extract the key mechanisms, and benchmark them against one of your own projects — producing a ranked list of things worth borrowing with evidence, cost and an adopt/reject recommendation. Use when the user says "look on GitHub for similar open-source projects", "could an open-source solution in X improve my Y", "benchmark my X", "is there a better open-source implementation", "how do others do this part". The target can be a skill/tool library or a local service/code repository. This skill only produces conclusions and recommendations; it does not change the target's code. Boundary: use it to look **outward** at external implementations. Looking **inward** (stress-testing your own project for its own bugs) is a different job — one object, one round of improvement → an improvement agent; several auditors, blind review, fix to convergence → audit-closeout. For a general topic survey not tied to one of your projects, use a general research workflow. If the user says something ambiguous like "what else could be improved in X", ask whether they want external solutions or internal hardening.
---

# oss-benchmark — benchmark your project against open source

## 0. Paths and tools

```bash
export OSS_BENCHMARK_DIR="${OSS_BENCHMARK_DIR:-$PWD/oss-benchmark}"   # ledger + reports; point it into your notes if you keep any
OSSB="$OSS_BENCHMARK_DIR"
SK="${CLAUDE_PLUGIN_ROOT}/skills/oss-benchmark"
mkdir -p "$OSSB/reports"
```

| Tool | Use |
|---|---|
| `python3 $SK/ossprobe.py <repo...> --clone` | Hard-gate feasibility check of candidates (activity, license, Python version, hidden heavy dependencies, scriptable entry point) |
| `python3 $SK/ledger.py check\|add\|list\|render` | Ledger of already-evaluated projects, so nothing is evaluated twice |
| `$OSSB/LEDGER.md` | Human-readable view of the ledger (generated — **don't edit**; the source of truth is `ledger.jsonl`) |
| `$OSSB/reports/YYYY-MM-DD-<topic>.md` | One report per round |

No `gh` CLI needed: GitHub is queried through the anonymous REST API (60 requests/hour) plus
`git clone --depth 1`. Setting `GITHUB_TOKEN` raises the limit automatically.

## 1. Objective

Given a topic and a target (the user's own skill / tool library / service), answer one question
systematically: **among existing open-source implementations, what do they have that we genuinely
lack and that is worth bringing over?**

The output is a ranked list of borrowable points, each with evidence, cost and a recommendation.
**No code changes here** — when the user decides to act, hand over to an implementation step.

## 2. Red lines

1. **Star counts, benchmarks claimed in READMEs, and third-party review blogs/rankings are not
   evidence.** Only two kinds count: code in the repository (with `file:line`), and numbers you
   measured on your own machine. Sorting by stars alone tends to surface abandoned academic
   repositories while the actively maintained project doesn't appear at all.
2. **Verify your own side first.** Before comparing, read the target's **actual code** to confirm
   how it works today — not memory, docs or impressions. A wrong premise about your own project
   ("we use library A" when it actually uses B) invalidates the whole comparison.
3. **Hard gates before reading code.** Candidates that fail the gates aren't worth reading (Phase 3).
4. **A refutation is a result and goes into the ledger**, with a reason specific enough for someone
   else to reproduce — "fails to build: requires CUDA_HOME, not set on this machine", not
   "incompatible".
5. **Latency and resource cost weigh as much as quality.** Equal quality but an order of magnitude
   slower = rejected for interactive use.
6. **Before adding a dependency, check what you already have.** Ask "have I already deployed this
   capability and just not wired it up (or has it silently stopped running)?" Sometimes that is the
   most valuable finding of the round.
7. **This skill does not change the target's code.** It only produces the list and recommendations.

## 3. Workflow

### Phase 0 — Pin the baseline (your side)

1. Confirm with the user: **the topic**, and **the target** project. If vague, ask; don't guess.
2. Locate the target and **read its actual implementation**:
   - skill/tool library → its `SKILL.md` and scripts
   - local service/repository → project root; start with `git log --oneline -10` to see what's moving
   Write one paragraph: "this is how it actually works now", citing the files. **If this differs from
   what the user said or remembered, the code wins — say so right away.**
3. **Define a measurable metric** and measure the current value. Without one, "is it better?" cannot
   be falsified.
   - retrieval → recall@k / latency on a fixed query set
   - transcription/OCR → manual comparison on a sample of your own real material
   - computation → error on known reference cases
   - services → end-to-end time, failure rate, lines of code
   If it really can't be measured, downgrade explicitly to a **qualitative comparison** and say so at
   the top of the report, so no one assumes the conclusion rests on measurements.

### Phase 1 — Check the ledger (don't evaluate twice)

```bash
python3 $SK/ledger.py check "<topic keyword>"
python3 $SK/ledger.py list --target <target>
```

On a hit, tell the user "this was evaluated before; the verdict was X because Y" — unless they ask
for a re-evaluation or a premise has changed (e.g. it failed on a dependency that now installs).
Re-evaluations use `ledger.py add --update`.

### Phase 2 — Cast a wide net (10–20 candidates, shallow)

Use at least three channels; any single channel has systematic blind spots:

```bash
# Channel A: by stars (mature projects)
curl -s "https://api.github.com/search/repositories?q=<keywords>+language:python&sort=stars&order=desc&per_page=20" \
 | python3 -c "import sys,json;[print(f\"{r['stargazers_count']:>6}★ {r['pushed_at'][:10]} {r['full_name']:<42} {(r['description'] or '')[:60]}\") for r in json.load(sys.stdin)['items']]"

# Channel B: by recent update (living projects — channel A's top results are often dead)
curl -s "https://api.github.com/search/repositories?q=<keywords>+language:python&sort=updated&order=desc&per_page=20" | <same as above>
```

- **Channel C: domain awesome-lists and upstream organisations** (research institutes, standards
  bodies, the maintainers of the ecosystem's core library). Repositories under such organisations
  are often more reliable than search results.
- **Channel D: web search** for "X alternatives", "X vs Y" — **only to discover candidate names,
  never to adopt their conclusions** (red line 1).

Watch for upstream / mirror / abandoned namesakes: a same-named repository may be an old abandoned
version, and the living main repository may be hosted elsewhere with GitHub as a mirror. Confirm
which one is alive.

Shortlist 5–8 for Phase 3 and show the list to the user.

### Phase 3 — Hard-gate check (mechanical, no code reading)

```bash
python3 $SK/ossprobe.py owner/a owner/b owner/c --clone --target-python 3.12
```

It checks: archived / days since last push; license (including "GitHub couldn't identify it",
which needs a human); `requires-python` vs. your target Python; heavy accelerator dependencies
(flash-attn, vLLM, DeepSpeed, …) that often fail to install; **heavy imports in source that the
dependency files don't declare**; whether there is a scriptable entry point or only a GUI.

- `RED` → drop it, or record explicitly "what extra cost would make it usable" (a Python-version
  clash may just mean "needs its own venv", not an absolute veto).
- `YELLOW` → a human looks before deciding.
- License RED → **open and read the LICENSE yourself**; model weights are often licensed separately
  from code, and some licenses carry user-count or revenue thresholds.
- GUI-only doesn't mean worthless — **re-implementing its algorithm yourself** is a valid way to
  adopt it; just count the cost.

2–4 survivors go to Phase 4. Record the dropped ones in the ledger now (Phase 7 collects them, but
don't lose them).

### Phase 4 — Read the real code, extract the key mechanism

For each survivor, keep the clone (`ossprobe.py ... --clone --keep`) and **read only the mechanism
you care about**; don't read the whole repository.

One structured note per candidate:

| Field | Requirement |
|---|---|
| Core mechanism | What it actually does, one or two sentences |
| Where | `file:line` — **no observation without file:line goes into the report** |
| Difference from ours | What it does more / less / differently |
| Porting cost | Copy a parameter, port an algorithm, or pull in a whole dependency? |

With many candidates and independent questions, dispatch read-only sub-agents in parallel, one per
candidate. Tell them **not to spawn further sub-agents** and to return `file:line`.

### Phase 5 — Head-to-head measurement (most often skipped, most decisive)

Run an A/B with **the Phase 0 metric on your own real data**. Don't accept the project's own
benchmark numbers — polished benchmark figures frequently collapse on your own material.

- Installs and runs → install into an isolated venv and run it, **recording quality and
  latency/memory**.
- Won't install or run → that is a hard result; record **the failing command and the verbatim
  error** as refutation evidence.
- Too heavy to install whole → at least port its algorithm/parameter into your code as a minimal
  experiment.
- No measurement possible → the verdict can only be `pending`; **never `adopted`.**

Keep test artefacts (venvs, model weights) in a separate scratch directory and note its location in
the report for cleanup.

### Phase 6 — Report

Write to `$OSSB/reports/$(date +%F)-<topic>.md` using the template in §4. The core is a **ranked
list of borrowable points**, ranked by evidence strength × inverse porting cost — not grouped by
candidate project.

It must include an **"existing capability check"** section (red line 6): is the capability this
round wanted already present locally, just not wired up or silently broken?

### Phase 7 — Ledger and filing

Every candidate that reached Phase 3 gets a ledger entry, **including the rejected ones**:

```bash
python3 $SK/ledger.py add --repo owner/name --topic "<topic>" --target <target> \
  --verdict adopted|rejected|pending \
  --reason "<specific enough to reproduce>" --evidence "<file:line, or command + error, or measured numbers>" \
  --report "reports/$(date +%F)-<topic>.md"
```

If `$OSSB` lives in a git repository shared with other work, commit only this skill's files
(`git commit --only -- <path>`), so you don't sweep in other uncommitted changes.

### Phase 8 — Report back

State conclusions; don't narrate the process:
1. The 1–3 most worthwhile adoptions: one sentence each on what to change, why, and what it costs.
2. Refuted candidates with a one-line reason (so the user sees where the effort went).
3. Whether the existing-capability check turned up anything.
4. Where the ledger and report are.

When the user decides to act, implementation happens outside this skill.

## 4. Report template

```markdown
# <topic> — open-source benchmark — YYYY-MM-DD

**Target**: <project> | **Baseline**: <how it works now, with file paths>
**Metric**: <metric + current value>   ← if qualitative: "no measured metric; qualitative comparison this round"

## 1. Summary
| # | Borrowable point | Source | Evidence | Porting cost | Recommendation |
|---|---|---|---|---|---|
| 1 | ... | owner/name `file:line` | measured / code-read / docs only | low/med/high | adopt / pending / reject |

## 2. Borrowable points in detail
### 1. <title>
- **How they do it**: ... (`file:line`)
- **How we do it now**: ... (`file:line`)
- **Measured**: <A/B numbers incl. latency>; or "not measured, because ..."
- **Cost**: new dependency / venv / runtime overhead / maintenance
- **Recommendation**: ...

## 3. Rejected candidates
| Repository | Where it failed | Evidence |
|---|---|---|
| ... | no push for 1000+ days | ossprobe |
| ... | imports a heavy accelerator library in source without declaring it | `model/x.py:4` |

## 4. Existing capability check
Is the capability wanted this round already deployed here but not wired up / silently broken?
- ...

## 5. Test environment and leftovers
- venv / model weight locations; cleanup needed?
```

## 5. Common failure modes

| Symptom | What's really going on |
|---|---|
| A third-party report or ranking taken as the conclusion | The repository's actual state doesn't match the report |
| The comparison's premise is wrong | You thought your project used A; it uses B |
| Selecting by star count | The top results are dead academic repositories; the living main project isn't in the list |
| Dependency files look clean | Source code imports a heavy accelerator library unconditionally |
| The official benchmark looks great | It breaks on your own real material |
| Quality ties, so adopt it | Latency is unacceptable for the real-time use case |
| A long search for something new | The biggest win is discovering an existing capability that was never wired up |
| Picked the wrong namesake | The GitHub repository is an old abandoned version |
| The plugin works but only by clicking | No CLI or scriptable entry point anywhere in the repository |

## 6. Wording rules

- Recommendations must be actionable down to "change which file, into what"; no "could consider
  introducing X".
- Evidence strength is stated honestly in three levels: `measured` / `code-read` / `docs only`.
  Reading code is not measuring.
- Refutations give the reproducible failing command and the verbatim error, not just "doesn't run".
- The report is read top to bottom as an argument, not used as a lookup table: **section headings
  state conclusions, not topics**, and **tables are only for side-by-side comparison** of several
  candidates on the same dimensions — don't put argument paragraphs into table cells.
