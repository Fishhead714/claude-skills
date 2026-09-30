# Decision registry

This directory answers one question: **before doing something, what has already
been settled that must not be re-argued?**

It is not a knowledge base and not a notes folder. A knowledge base answers "how
does this work". This registry answers "this has been decided -- don't improvise".

Scaffolded by `init.py`. The machine-readable rules are in `schema.json`; this
file is the same rules for humans. Change the rules in `schema.json` first.

## Three card types -- do not mix them

| Type | Directory | What it is | Who may change it |
|---|---|---|---|
| **constraint** | `constraints/` | An externally imposed hard boundary (policy, law, technical limit) | Only when its source changes |
| **decision** | `decisions/` | A judgement already made. **Never edited** -- only superseded by a new card | Supersede only |
| **stance** | `stances/` | My current view; evidence can overturn it | As soon as evidence appears |

The failure this prevents: treating "my current view" as a hard boundary, or
continuing to build on a decision that has already been overturned.

## Cards vs long-form notes

A card is a **conclusion**, one page at most, small enough to put in context.
The reasoning stays where it was written; `evidence:` points to it. Otherwise a
single `check` would pour every long document into context and the registry
would be pointless.

## Two independent axes

```
force        -- how bad it is to violate it
enforcement  -- what guarantees it actually reaches the agent's context
```

**They are independent.** A binding rule does not have to be resident; a
guidance rule may need to be.

### force

| Value | Meaning |
|---|---|
| `binding` | Crossing it invalidates the plan / breaks process |
| `guidance` | Recommended value or convention. Crossing it must be justified in the output |
| `assumption` | Unverified. **Never a reason to reject someone else's proposal** |

### enforcement (increasing strength)

| Value | Mechanism | When |
|---|---|---|
| `retrieved` | Found by search/RAG, if the search happens to hit it | Background; missing it is not fatal |
| `skill` | Loaded when a related skill/workflow is invoked | Applies only to certain kinds of work |
| `resident` | Always in context (e.g. CLAUDE.md / system prompt) | Applies to **everything**, and missing it is costly |
| `gated` | Mechanically blocked at the moment of action (hook, validation script) | Violations are machine-detectable |
| `code` | Code refuses to run without it; does not depend on an LLM reading anything | The quantity is decidable |
| `eliminated` | The violation is made physically impossible (the dangerous call is removed) | You can change things at that layer |

Choose by **cost of violation x probability of being ignored**, not by
"importance" -- people feel that everything is important. Classifying
enforcement tends to surface items that should have been code changes rather
than notes (`eliminated`); those are the highest-value finds.

## Three hard rules (checked mechanically by `audit.py`)

1. **`enforcement: resident` has a quota** (`limits.resident_quota`, default 12).
   To add one when full, demote one first. A bloated resident layer dilutes
   itself until nothing is effectively resident. (E007)
2. **`force: binding` + `enforcement: retrieved` is illegal.** A claimed force
   must not be detached from its guarantee. (E004)
3. **`source_tier: my-inference` + `force: binding` is illegal.** An inference
   cannot be a hard boundary. (E003)

## source_tier -- where a boundary's authority comes from

Internal boundaries get authority from *who said it, and where*:

`policy-document` > `meeting-resolution` > `verbal` > `owner-decision` > `my-inference`

External boundaries get it from the rank of the text:

`law`, `regulation`, `contract`, `authority-reply`, `international-standard`,
`guideline`, `industry-practice`

Without an explicit tier, "I remember the boss said" gets used exactly like
"the policy document says". That is the main failure mode of internal rules.

The review interval follows the tier (`review_months`): **the softer the
source, the more often it is reviewed.**

## Standard activity names

`check.py --activity` takes "what I am about to do". The name must come from
`activities` in `schema.json`. The shipped list is an **example** -- edit it to
match your team's work. Unknown names are refused rather than silently matching
nothing.

## Usage

```bash
python3 <skill>/check.py --activity customer-email
python3 <skill>/add.py new constraint --title ... --source ... --source-tier ... \
    --consequence ... --acquisition human_only --asked ...
python3 <skill>/build_index.py   # after editing a card by hand
python3 <skill>/audit.py         # exit code 1 on any ERROR
```

`INDEX.json` is **derived**. The truth is in the card frontmatter. Never edit
INDEX.json by hand.

## hard_value (optional, constraints)

Quantifiable parts of a constraint can be written as structured thresholds so
that audit can compare cards:

```yaml
hard_value:
  trigger_any:
    - {metric: max_open_incidents, op: "<=", value: 5, unit: count}
```

`op` is one of `<`, `<=`, `>`, `>=`, `==`. Audit warning W002 fires when two
active binding cards whose scopes overlap give a different `op`/`value`/`unit`
for the same `metric`.

## Frontmatter format

Cards use a strict YAML subset (mappings, lists, flow `[a, b]`, quoted strings,
`#` comments, `|` literal blocks). `>` folded blocks and nested block lists are
refused. Anchors, aliases and tags are refused with an
error naming the card. Dates are plain `YYYY-MM-DD`.

## _inbox/

`scan_candidates.py` writes `_inbox/QUEUE.md`. Nothing in `_inbox/` is ever
loaded as a card. Each queued item leaves by exactly one exit: a card created
with `add.py` (its `evidence` points at the note), or a line in
`_inbox/IGNORE.txt`.
