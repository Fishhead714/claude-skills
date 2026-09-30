# skill-quality

Improving a Claude Code skill with evidence instead of impressions.

| Component | What it does |
|---|---|
| `skill-optimizer` (agent) | Sets a target for an existing skill, builds an adversarial test battery, and loops fix → full regression until the whole battery passes several runs in a row. It edits files, so give it a clearly scoped target. |
| `skill-optimization-judge` (agent) | Grades the outputs of a pure-prompt skill blind: it sees only the rubric, the inputs and the outputs, never how they were produced. Dispatch it from the main session, not from the optimizer, so the judgement stays independent. |

## License

MIT — see the repository root [`LICENSE`](../../LICENSE).
