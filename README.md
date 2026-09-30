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
| [`review-agents`](plugins/review-agents) | Three read-only reviewer agents — `code-reviewer`, `secrets-auditor`, `research-verifier` — to dispatch before something ships |
| [`agent-governance`](plugins/agent-governance) | Registry of things already decided, so agents stop re-opening them (`skills/decision-registry`): each rule is rated by how bad a violation is and by what keeps it in the agent's context, and an audit refuses combinations such as "binding, but only if a search happens to find it" |
| [`release-hygiene`](plugins/release-hygiene) | Pre-release scan for leaked *numbers* (`skills/fingerprint-scan`): matches every literal against a private facts ledger kept outside the repo, with unit conversion, rounding and derived ratios, plus real coordinates and build artifacts. Ships with mutation tests that prove each detector can see what it is meant to catch |

Each plugin folder has its own `README.md`. Skills also ship a `SKILL.md` (the instructions Claude reads); agents live in the plugin's `agents/` folder.

## License

MIT — see [`LICENSE`](LICENSE) — **except** files adapted from other projects. Any skill that contains such files has a `THIRD_PARTY_NOTICES.md` next to them naming the source, its license and copyright; those files stay under their original license (for example, the GlazeWM config template in `windows-desktop` is GPL-3.0-only). Each adapted file also says so in a header comment where the file format allows it.
