# dig-until-dry

Unattended, multi-round research that keeps digging until a round turns up nothing new.

A normal "research this for me" request is a single pass: split the question, search in parallel,
verify, write up. That is a sample, not an exhaustive answer. This skill runs the pass as a loop —
**plan → parallel research → adversarial verification of every new finding → reflect on what is
still missing, contradictory or thinly sourced → turn those gaps into the next round's questions** —
and stops only when two consecutive rounds produce no new findings ("dry") or a hard round/token cap
is hit. Nobody has to approve each round.

## How to use

- **With Claude Code:** install the `research-methods` plugin and ask for exhaustive, hands-off
  research ("keep digging until you run out, don't stop to ask me each round"). The skill tells the
  main agent to run the embedded script with the `Workflow` tool, passing
  `{"topic": "...", "maxDryRounds": 2, "maxRounds": 8}`. The result is `{topic, rounds, confirmed, stopped_reason}`;
  the skill then says how to turn `confirmed` into a report and how to word it differently when the
  run stopped at the cap instead of running dry.
- **Without Claude Code:** the script in section 3 of `SKILL.md` is a readable template of the loop
  (schemas, dedup key, batching, stop conditions) that you can port to any agent framework that can
  call a sub-agent with a JSON schema and run calls in parallel.

## Limits

- Requires Claude Code's `Workflow` tool, which is not available in every environment or plan.
- Expensive and slow by design: many sub-agent calls per round, runs from tens of minutes to hours.
  Use it only when the user explicitly wants exhaustive digging; a single-pass research workflow is
  the right tool for most questions.
- "Confirmed" means one independent sub-agent tried and failed to refute the claim — not that a
  human checked it. Low-confidence and single-source findings are kept and must be labelled as such.
- The skill text (instructions and prompts) is written in Chinese; the script and schemas are English.

Part of [claude-skills](../../../../). MIT — see the repository root [`LICENSE`](../../../../LICENSE).
