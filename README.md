# claude-skills

A small collection of [Claude Code](https://docs.claude.com/en/docs/claude-code) plugins — skills and agents extracted from day-to-day engineering work, cleaned up for general use.

## Install

```
/plugin marketplace add Fishhead714/claude-skills
/plugin install <plugin-name>@fishhead714-skills
```

## Plugins

| Plugin | What it does |
|---|---|
| [`windows-desktop`](plugins/windows-desktop) | One-script GlazeWM + YASB tiling desktop for Windows (`skills/glazewm-desktop`), usable with or without Claude Code |
| [`review-agents`](plugins/review-agents) | Seven read-only reviewer agents to dispatch before something ships: `code-reviewer`, `secrets-auditor`, `research-verifier`, `argument-auditor` (does the report's line of argument hold), `code-evidence` (is a claim about the code true, file:line only), `deliverable-critic` (layout, fabrication and readability of a deck or report), `infra-diagnostician` (automations that went silent) |
| [`agent-governance`](plugins/agent-governance) | Registry of things already decided, so agents stop re-opening them (`skills/decision-registry`): each rule is rated by how bad a violation is and by what keeps it in the agent's context, and an audit refuses combinations such as "binding, but only if a search happens to find it" |
| [`release-hygiene`](plugins/release-hygiene) | Pre-release scan for leaked *numbers* (`skills/fingerprint-scan`): matches every literal against a private facts ledger kept outside the repo, with unit conversion, rounding and derived ratios, plus real coordinates and build artifacts. Ships with mutation tests that prove each detector can see what it is meant to catch |
| [`skill-quality`](plugins/skill-quality) | `skill-optimizer` improves a skill by looping over an adversarial test battery until the full regression passes repeatedly; `skill-optimization-judge` grades the outputs blind |
| [`research-methods`](plugins/research-methods) | `dig-until-dry` (research rounds until nothing new turns up), `method-scout` (how the most expert people in a field actually do it), `oss-benchmark` (compare open-source projects with your own), `agent-team-architect` (whether to build an agent and how to organise a team) |
| [`geo-review`](plugins/geo-review) | `geo-data-validator`: independent pre-delivery check of geospatial and engineering numbers — CRS, units, time base, real data coverage, magnitude sanity, silent data loss |

Each plugin folder has its own `README.md`. Skills also ship a `SKILL.md` (the instructions Claude reads); agents live in the plugin's `agents/` folder.

## Background

Once AI agents were doing real engineering work for me, I kept hitting the same failures: reviews
that only checked what they were asked, decisions re-opened in every new session, private numbers
slipping into code meant for publication. Each plugin here is the fix I ended up building for one of
those, extracted from a private workspace and cleaned up for general use.

## License

MIT — see [`LICENSE`](LICENSE) — **except** files adapted from other projects. Any skill that contains such files has a `THIRD_PARTY_NOTICES.md` next to them naming the source, its license and copyright; those files stay under their original license (for example, the GlazeWM config template in `windows-desktop` is GPL-3.0-only). Each adapted file also says so in a header comment where the file format allows it.
