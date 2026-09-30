# audit-closeout

A Claude Code skill for auditing something that already exists and is in use — a calculation pipeline, a script library, a skill, a data product — and carrying the audit all the way to closure instead of stopping at a list of complaints.

## The problem

Ask an AI agent to "review X" and you get a plausible list in chat. Then the session ends and the list is gone; the next review rediscovers half of it; fixes are declared done by the same agent that made them; and "facts" learned along the way end up in your notes unverified. This skill turns that into a fixed loop:

1. **Pin the object and read prior rounds.** Earlier `AUDIT-*.md` files define what this round excludes and what it must re-try.
2. **Pick reviewers by object type**, each with an explicit evidence form (reproduced numbers, `file:line` plus a triggering input, a blind judge's score for pure-prompt skills, "last real success" for automation).
3. **Number and grade defects** (Critical / Medium / Low) in an append-only `AUDIT-YYYY-MM-DD.md`, with mandatory "checked and fine", "could not verify" and "excluded" sections — written by the orchestrator, because reviewers are read-only.
4. **Fix until convergence**: full regression every round, N consecutive clean rounds (default 2, cap 5), root-cause vs containment judged by someone other than the fixer, pass^k for non-deterministic outputs.
5. **Write back only verified knowledge**, with every claim labelled primary / secondary / self-reproduced.

## Files

| File | What it is |
|---|---|
| `SKILL.md` | The procedure Claude follows |
| `AUDIT_TEMPLATE.md` | Skeleton for an audit file |
| `BATTERY.md` | Adversarial routing cases (should / shouldn't trigger, wrong-branch bait, red lines) for testing the skill after you edit it |
| `check_skill.py` | Self-check: every backticked agent/skill/command/plugin name exists in your setup, relative paths resolve, prose counts match their tables. Standard library only |

## Usage

Install the plugin, then ask things like "audit the `report-builder` skill and loop-fix it until it converges" or "independent second-round review of this pipeline, excluding what the last round covered".

The skill describes reviewer **roles** (code reviewer, data validator, fact-checker, blind judge). It works best with read-only reviewer agents installed — for example `code-reviewer` and `research-verifier` from this repository's `review-agents` plugin. Run `python3 check_skill.py` to see which named components are missing from your setup.

## Limits

- It is an orchestration procedure, not an auditor: the quality of findings depends on the reviewer agents you give it.
- It is meant for a human-attended session. It deliberately refuses to run audits on a schedule; only pure-script checks should be scheduled.
- `check_skill.py` cannot test routing (whether the skill triggers and which branch it takes) — that is what `BATTERY.md` plus a blind judge are for.
- Convergence thresholds (N = 2, cap 5, k = 3) are working defaults, not calibrated values.

Part of [claude-skills](../../../../). MIT — see the repository root [`LICENSE`](../../../../LICENSE).
