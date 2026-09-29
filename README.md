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

Each skill folder has its own `README.md` (human-facing) and `SKILL.md` (instructions Claude reads).

## License

MIT — see [`LICENSE`](LICENSE) — **except** files adapted from other projects. Any skill that contains such files has a `THIRD_PARTY_NOTICES.md` next to them naming the source, its license and copyright; those files stay under their original license (for example, the GlazeWM config template in `windows-desktop` is GPL-3.0-only). Each adapted file also says so in a header comment where the file format allows it.
