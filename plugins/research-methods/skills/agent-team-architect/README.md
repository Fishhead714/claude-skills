# agent-team-architect

A decision checklist for *whether* to build a new agent, *where* it belongs, and *how* to dispatch
work across agents — not how to write the agent file.

Once you have more than a handful of agents, the failure is rarely a badly written prompt; it is an
agent that should not exist (a producer with no one checking it, or a duplicate of an existing
reviewer), or a topology that wastes tokens (fan-out with a barrier nobody needed). This skill asks
three questions before anything gets built — which existing work shares the same background and
acceptance criteria, whether this output has a producer but no checker, and whether you can point to
a real incident that justifies the new agent — then helps pick a topology (delegate, fan-out,
pipeline, independent judge panel, debate), a model tier, and checks five hard constraints that each
came from a real failure (no recursive general-purpose sub-agents, verify `tools` empirically, no
self-review, cap parallel fan-out, reviewers get no Edit).

## How to use

- **With Claude Code:** install the `research-methods` plugin; the skill triggers on questions such as
  "should this be an agent?", "which team does this belong to?" or "should we split out a judge?",
  and after you add a new skill, to check which existing boundary it falls under.
- **Without Claude Code:** read `SKILL.md` as a checklist when designing any multi-agent setup.
- It works best alongside a single "team ledger" document in your own repository that records which
  agents exist and why; the skill deliberately does not keep that state itself.

## Limits

- It produces judgements, not files. For agent file syntax use a dedicated agent-authoring guide.
- The model-tier table is directional, not measured cost data.
- The skill text is written in Chinese.

## Attribution

The model-selection table, the haiku→sonnet→opus "pyramid" idea, the debate topology with an
append-only shared log, and the background-agent write-permission pitfall are translated or adapted
from [ZoranSpirkovski/creating-agent-teams](https://github.com/ZoranSpirkovski/creating-agent-teams)
(MIT). See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Part of [claude-skills](../../../../). MIT — see the repository root [`LICENSE`](../../../../LICENSE) — except `SKILL.md`, which remains under its original MIT license (see `THIRD_PARTY_NOTICES.md`).
