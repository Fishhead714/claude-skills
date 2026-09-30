# decision-registry

A small, file-based registry of **things that are already settled** --
constraints, decisions and stances -- for AI coding/agent workflows (packaged as
a Claude Code skill, but the scripts are plain Python and work on their own).

## The problem

An AI agent working across many sessions keeps re-opening questions that were
closed weeks ago. It proposes the option that was rejected, treats a hunch as a
hard rule, or keeps building on a decision that has since been reversed.
Notes and knowledge bases don't fix this: they answer "how does this work?",
and search only helps if the agent thinks to search.

This registry answers a narrower question: **before doing X, what has already
been decided that must not be re-argued?** Each answer is a one-page card
with a traceable source, and `check.py` lists the cards that apply to an
activity.

## Three card types

| Type | Meaning | Change rule |
|---|---|---|
| constraint | Imposed from outside (policy, law, hard technical limit) | Changes only when its source changes |
| decision | A judgement already made, with the rejected alternatives | Immutable; replaced only by a new card that supersedes it |
| stance | A current view that evidence could overturn | Must state `falsified_if` |

## Why `force` and `enforcement` are separate

Most rule lists have one axis: how important is it. That conflates two
different questions:

- **force** -- how bad is a violation? (`binding` / `guidance` / `assumption`)
- **enforcement** -- what actually guarantees the rule reaches the agent at the
  moment it matters? (`retrieved` < `skill` < `resident` < `gated` < `code` < `eliminated`)

A binding rule that is only findable by search is a rule that will be missed.
A minor convention that applies to every single task may deserve to be always
loaded. Choosing enforcement by *cost of violation x chance of being ignored*
(instead of "importance") also tends to reveal rules that should not be notes
at all but code changes that make the violation impossible.

## The three gates

`audit.py` checks 15 error conditions; three of them are the reason the tool exists:

- **E003 -- an inference cannot be binding.** `source_tier: my-inference` with
  `force: binding` is rejected. Source tiers make "I think the boss said" and
  "the policy document says" visibly different.
- **E004 -- binding cannot rely on retrieval.** A hard rule must be loaded by
  a skill, always resident, gated by a hook, or enforced in code.
- **E007 -- the resident layer has a quota** (default 12). An always-loaded
  list that grows without limit dilutes itself until nothing stands out.

Other mechanics: decisions are never edited, only superseded (with both links
checked); the review interval depends on the source tier (softer source,
more frequent review); every card records how it will be re-verified
(`acquisition`); the candidate scanner only writes to `_inbox/` and never
enrolls anything.

## Quick start

Requires Python 3.9+, standard library only.

```bash
python3 init.py --with-examples          # creates ./decision-registry with 3 fictional cards
python3 audit.py                         # -> Clean.
python3 check.py --activity customer-email
python3 add.py new decision --title "We release on Tuesdays" \
    --source "Team retro" --source-tier meeting-resolution \
    --consequence "Friday releases need a new decision card" \
    --acquisition human_only --asked "Team lead, retro notes" \
    --decided-by "Team" --activities release
python3 audit.py
```

Then edit `activities` in `decision-registry/schema.json` to fit your work
(the shipped list is an example).

The registry is found via `--registry`, then `$DECISION_REGISTRY`, then by
walking up from the current directory to a `decision-registry/` folder. If
none is found, scripts exit with an error instead of reporting "no rules".

As a Claude Code skill, place this directory at `skills/decision-registry/`
in a plugin; `SKILL.md` tells the agent when and how to use it.

Tests:

```bash
python3 -m unittest discover -s tests -v
```

## Limitations

- It only knows what was registered. An empty result means nobody wrote the
  rule down, not that no rule exists -- `check.py` says this explicitly.
- `enforcement` is metadata plus audit checks. The registry does not inject
  resident cards into a prompt or install hooks for you.
- Matching on region/project/activity is exact, case-sensitive string/glob
  matching. There is no semantic matching of free-text requests to activities.
- Card frontmatter uses a strict YAML subset (no anchors, aliases or tags) so
  that the tool stays dependency-free.
- The candidate scanner is keyword-based; expect false positives. It is a
  queue for a human, not a classifier.
- It is designed for tens to low hundreds of cards maintained by one person or
  a small team; it has no locking for concurrent writers.
