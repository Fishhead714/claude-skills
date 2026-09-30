# agent-governance

Keeping long-running AI agent work consistent with what has already been decided.

| Skill | What it does |
|---|---|
| [`decision-registry`](skills/decision-registry) | A file-based registry of constraints, decisions and stances. Each card records how bad a violation is (`force`) separately from what keeps it in the agent's context (`enforcement`). `check.py` lists the cards that apply before a task starts. `audit.py` rejects cards that claim more than their source supports: an inference marked binding, a binding rule that is only reachable by search, a stance with no condition that would overturn it, or more always-loaded cards than the quota allows. |

The scripts are plain Python (3.9+, standard library only) and work without Claude Code. See the skill's own `README.md` for the full model and a quick start.

## License

MIT — see the repository root [`LICENSE`](../../LICENSE).
