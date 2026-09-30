# oss-benchmark

A Claude Code skill for answering "is there an open-source project that does this part better than mine — and is it actually worth bringing over?"

## The problem

"Look on GitHub for something better" usually ends with a list sorted by stars, a few README benchmark numbers repeated as facts, and a recommendation to adopt a project nobody installed. The failure modes are predictable: the top-starred repositories are often abandoned; the living project may be a mirror or a renamed namesake; dependency files look clean while the source imports a heavy GPU library unconditionally; official benchmarks collapse on your own data; a tie on quality hides a latency that is unacceptable in practice; and the same refuted candidate gets evaluated again three months later.

The skill fixes the order of work:

1. **Pin your own baseline first** — read your project's actual code and define a measurable metric.
2. **Check the ledger** of past evaluations before searching.
3. **Search several channels** (by stars, by recent activity, upstream organisations/awesome-lists, web search for names only).
4. **Mechanical hard gates** with `ossprobe.py`: archived/stale, license (including unidentifiable ones), `requires-python` conflicts, undeclared heavy accelerator imports, GUI-only projects.
5. **Read only the relevant mechanism**, every observation with `file:line`.
6. **Measure head to head** on your own data, quality *and* latency. Unmeasured = `pending`, never `adopted`.
7. **Report a ranked list of borrowable points** (evidence × inverse porting cost), plus an "existing capability check" — often the best finding is something you already have but never wired up.
8. **Record every verdict**, including rejections, in an append-only JSONL ledger.

## Files

| File | What it is |
|---|---|
| `SKILL.md` | The procedure Claude follows, with a report template and a table of common failure modes |
| `ossprobe.py` | Hard-gate checker: GitHub API metadata + optional shallow clone for static checks. Standard library only; uses `git` for `--clone`; honours `GITHUB_TOKEN` |
| `ledger.py` | Evaluation ledger (`check` / `add` / `list` / `render`). JSONL is the source of truth; `LEDGER.md` is a generated view. Refuses vague reasons and refuses to write over a corrupt ledger |

Both scripts run without Claude Code:

```bash
python3 ossprobe.py pallets/click owner/other-repo --clone --target-python 3.12
OSS_BENCHMARK_DIR=./oss-benchmark python3 ledger.py check "cli parsing"
```

## Usage

Install the plugin, optionally set `OSS_BENCHMARK_DIR` (default: `./oss-benchmark` in the working directory), then ask e.g. "benchmark my `report-builder` tool against open-source alternatives for PDF table extraction".

## Limits

- Channels A/B search Python repositories by default (`language:python`); edit the query for other languages.
- `ossprobe.py`'s heavy-dependency table and staleness thresholds (180/365 days) reflect one setup's experience; adjust them for your hardware.
- The anonymous GitHub API allows 60 requests per hour; each candidate uses two.
- The skill recommends; it does not change your code. It also does not replace a license review by someone qualified when you plan to redistribute.

Part of [claude-skills](../../../../). MIT — see the repository root [`LICENSE`](../../../../LICENSE).
