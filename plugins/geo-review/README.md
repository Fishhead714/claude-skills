# geo-review

| Agent | What it does |
|---|---|
| `geo-data-validator` | Independent check of geospatial and engineering results before they go into a report or to someone else: coordinate reference systems, units, time base, whether the data source really covers the area and period, orders of magnitude, and rows silently lost along the way. Read-only; reports as one Markdown table. |

It does not judge code style, policy wording or layout; use a code reviewer, a fact-checker or a deliverable checker for those (for example `code-reviewer`, `research-verifier` and `deliverable-critic` in the [`review-agents`](../review-agents) plugin).

## License

MIT — see the repository root [`LICENSE`](../../LICENSE).
