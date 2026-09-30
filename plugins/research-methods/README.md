# research-methods

Research workflows for Claude Code. They describe how to search, not what was found: no results
from the author's own research are included.

| Component | What it does |
|---|---|
| `dig-until-dry` (skill) | Repeated research rounds: after each round it writes the next sub-questions, checks every finding adversarially, and stops only when several rounds in a row turn up nothing new. Needs a Claude Code environment with the Workflow tool. |
| `method-scout` (skill) | Finds how the most expert people in a field actually approach a problem (theses, reviews, standards, practitioner disclosures) and grades the evidence. Ships a report template and a checker. |
| `oss-benchmark` (skill) | Searches GitHub for projects on a topic, extracts what matters, and compares them with your own project to produce a list of ideas worth adopting. |
| `agent-team-architect` (skill) | Decides whether a new agent is worth building, which team a skill or output belongs to, and which topology to use when dispatching work. Partly adapted from another project; see its `THIRD_PARTY_NOTICES.md`. |

Some of these skills are written in Chinese; Claude reads them either way.

## License

MIT — see the repository root [`LICENSE`](../../LICENSE), except files listed in a skill's `THIRD_PARTY_NOTICES.md`.
