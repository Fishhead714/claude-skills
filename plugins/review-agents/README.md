# review-agents

Three independent reviewer agents for Claude Code. Each one assumes the work in front of it is wrong until it has traced evidence otherwise, and each has an explicit anti-hallucination rule: state the concrete failure, try to refute yourself, then rate your confidence.

| Agent | Reviews | Catches |
|---|---|---|
| `code-reviewer` | a diff / PR / changed files | correctness bugs, security issues, needless complexity, inefficiency, missing tests |
| `secrets-auditor` | a diff or repo tree | credentials a regex-based pre-commit hook would miss, plus the gaps in that hook |
| `research-verifier` | a research or policy draft | claims resting on search snippets, sources older than the event they report, "proposed" upgraded to "approved", single-source numbers |

They were written to be dispatched as sub-agents before something ships, and are most useful when the main session is told to use them proactively. All three are read-only (no edit or write tools) and report as a single Markdown table.

## Names

`code-reviewer` shares its name with agents in Anthropic's official [`pr-review-toolkit`](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/pr-review-toolkit) and `feature-dev` plugins. It was written independently and takes a different approach (a priority-ordered checklist and a refute-before-reporting rule instead of guideline compliance with numeric confidence scores). Plugin agents are namespaced, so both can be installed side by side.

## License

MIT — see the repository root [`LICENSE`](../../LICENSE).
