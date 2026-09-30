---
name: decision-registry
description: A registry of things that are already settled -- constraints, decisions and stances that must not be re-argued -- plus a pre-work check that lists the ones that apply. Use it when the user says things like "note this down, it's final", "from now on we always do X", "lock this in so we stop re-debating it", "did we already decide this?", "is there a rule about this?", "who can approve this?", "register a constraint", "that decision changed", or before any consequential activity (customer emails, pricing, releases, incident response, hiring, onboarding, security changes, dependency upgrades) when you need to know what must not be touched. Also use it proactively right after a new settled judgement is formed, to enroll it. Do not use it for general note search, meeting minutes, project status tracking, or session logs -- it records "how we always do this from now on", not "what just happened".
---

# decision-registry

## One-line model

A knowledge base answers "how does this work". **This registry answers "this has
already been decided -- don't improvise".**

The rules live in the registry itself: `README.md` (for humans) and
`schema.json` (enums and limits, read by every script). **Change the rules
there, not in this file.**

## Where the registry is

Every script resolves the registry in this order:

1. `--registry <dir>`
2. environment variable `DECISION_REGISTRY`
3. walk up from the current directory looking for a `decision-registry/`
   directory that contains `schema.json`

If none is found the script **exits with an error**. It never falls back to an
empty list, because an empty answer would be read as "there are no boundaries".

Create one with:

```bash
S="${CLAUDE_PLUGIN_ROOT}/skills/decision-registry"
python3 "$S/init.py"                  # ./decision-registry
python3 "$S/init.py" --with-examples  # plus 3 fictional example cards
```

Then edit `activities` in `schema.json` -- the shipped list is an example.

## Three card types

| Type | Directory | Who may change it |
|---|---|---|
| `constraint` | `constraints/` | Only when its source changes |
| `decision` | `decisions/` | **Never edited** -- only superseded by a new card |
| `stance` | `stances/` | As soon as evidence appears |

The reason this registry exists: treating "my current view" as a hard
boundary, or continuing to build on a decision that was already overturned.

## Two independent axes -- judge both

```
force        -- how bad a violation is      binding | guidance | assumption
enforcement  -- what guarantees it reaches context
               retrieved < skill < resident < gated < code < eliminated
```

Pick `enforcement` by **cost of violation x probability of being ignored**,
not by "importance" (everything feels important). Classifying enforcement
surfaces items that should be code changes instead of notes (`eliminated`) --
those are the highest-value finds.

`resident` means "always in context" (e.g. listed in the project's CLAUDE.md or
system prompt). It has a quota (default 12) -- over quota is an audit ERROR.

## Usage

```bash
S="${CLAUDE_PLUGIN_ROOT}/skills/decision-registry"

# Before work: list applicable boundaries (all filters optional, combinable)
python3 "$S/check.py" --activity pricing
python3 "$S/check.py" --project alpha --region EMEA

# After editing a card by hand (add.py does this automatically)
python3 "$S/build_index.py"   # rebuild INDEX.json (derived, never hand-edit)
python3 "$S/audit.py"         # health check; exit code 1 on any ERROR
```

Activity names must come from `activities` in `schema.json`; unknown names are
refused (exit 2) rather than silently matching nothing. If a natural-language
request does not map obviously to one activity, run `check.py` for each
plausible candidate, or ask the user.

`check.py` output has three sections: **binding**, **guidance/assumption**, and
**no longer in force** (superseded/retired, shown for traceability only). When
no binding card matches, it says so explicitly: that means "nobody registered
one", not "there is none" -- tell the user that.

## Add / verify / supersede -- always through add.py

Copying templates by hand goes wrong, and the worst failure is not an audit
error but a card that passes with a wrong field.

```bash
# New card. --source / --source-tier / --consequence / --acquisition are required.
python3 "$S/add.py" new constraint \
  --title "Firewall rule changes need a second approver" \
  --source "Security runbook, change control page" --source-tier policy-document \
  --consequence "A single-approver firewall change is rolled back" \
  --acquisition human_only --asked "Security lead, onboarding session" \
  --activities security-change --enforcement gated

# Re-verify: refresh `verified`, reset `review_by` from source_tier, log the change
python3 "$S/add.py" verify C-001 --note "Re-read the runbook page"

# Supersede: creates the new card, links both ways, marks the old one superseded
python3 "$S/add.py" supersede D-001 --title "..." --source ... --source-tier ... \
  --consequence ... --acquisition ... --asked ... --decided-by "..."
```

`add.py` refuses at **creation** time (not later in audit): missing required
fields, unknown activities, a stance without `--falsified-if`, a decision
without `--decided-by`, bad dates, and the illegal combinations in
`schema.json` (`my-inference`+`binding`, `binding`+`retrieved`). `verify`
re-runs the same gates. All three subcommands rebuild `INDEX.json`.

The review interval comes from `source_tier` (`review_months` in schema.json),
e.g. policy-document 24 months, meeting-resolution / owner-decision 12,
verbal 6, my-inference 3. **The softer the source, the more often it is
reviewed.**

**If you cannot trace the source, do not create the card.** A vague card gets
used as if it were a firm boundary.

When a review date passes (audit W001), pick an exit -- do not let it rot:
re-verify (`add.py verify`), lower `force`, or set `status: retired`. A
registry full of stale assertions is worse than none, because it still looks
authoritative.

## Candidate detection: queue only, never enroll

```bash
python3 "$S/scan_candidates.py"   # recent notes -> _inbox/QUEUE.md
```

Scans notes modified in the last `scan.lookback_days` under `scan.root`
(default: the registry's parent directory), restricted by `scan.include_dirs` /
`exclude_dirs`. A file is admitted only by a **strong signal** phrase
(`final decision`, `ruled out`, `must not`, ...); weak signals only rank.
All configurable in `schema.json`.

It writes only `_inbox/`, and cards are loaded only from the three card
directories -- so however noisy the scan, it cannot pollute the registry.
Enrollment is always an explicit `add.py new`. Each queued item has exactly two
exits: a card whose `evidence` points to it (skipped next time), or a line in
`_inbox/IGNORE.txt`.

## Audit errors

| Code | Blocks |
|---|---|
| E001 | Missing required field / value not in enum |
| E002 | id vs file name mismatch, duplicate id, card in the wrong directory |
| **E003** | `source_tier: my-inference` + `force: binding` -- an inference cannot be a hard boundary |
| **E004** | `force: binding` + `enforcement: retrieved` -- force detached from its guarantee |
| E005 | `stance` without `falsified_if` -- a view nothing can overturn is dogma |
| E006 | Broken supersede chain (either direction), or superseded card still active |
| **E007** | Resident layer over quota (`limits.resident_quota`, default 12) |
| E008 | INDEX.json missing or out of sync with the cards |
| E009 | `acquisition` without its companion field (how to re-verify) |
| E010 | `held_copy` archive tree exists but the referenced file is gone |
| E011 | Internal card using an external source tier, or vice versa |
| E012 | `external` + `binding` without `applicability` |
| E013 | `verified` / `review_by` / `decided_on` not an ISO date (YYYY-MM-DD) |
| E014 | Malformed scope: `[all]` in a list, unknown activity, scope not a mapping |
| E015 | A card cannot be parsed -- the whole registry is unusable until fixed |

Warnings (exit 0): W001 review overdue, W002 overlapping binding cards disagree
on a `hard_value.trigger_any` threshold (see the registry README), W003 no evidence, W004 archive tree not on this
machine, W005 binding with a broken trace (`unrecorded`), W006 archive_ref
cannot be checked.

E003/E004/E007 are the real gates. Do not loosen them to make audit pass; if
they must change, change `schema.json` and record why.

## Limits

- The registry lists what someone registered. It cannot know about rules
  nobody wrote down; "no match" never means "no rule".
- `enforcement` is a label plus the E004/E007 checks. The registry does not
  itself put resident cards into your system prompt or install hooks for
  `gated` ones -- you wire that up.
- Scope matching is exact and case-sensitive (with `*` globs). `check.py`
  warns when a `--region`/`--project` value appears in no card.
- Card frontmatter is a strict YAML subset (see the registry README).
- Keep external quantitative criteria (legal limits, standards values) in one
  place. If you move them into this registry, remove the other copy -- scattered
  copies of the same rule drift apart.
