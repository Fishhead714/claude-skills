# release-hygiene

Checks to run before code written for private work is published.

| Skill | What it does |
|---|---|
| [`fingerprint-scan`](skills/fingerprint-scan) | Secret scanners find credentials, and denylists find names. Neither finds the *numbers* that identify private work: a real site area, a unit count, a company template's page size, a percentage computed from a private dimension, a surveyed coordinate. This skill matches every numeric literal in a release tree against a private facts ledger that you keep outside the repository. Matching covers unit conversion, rounding and declared ratios. It also flags real-looking coordinates and build artifacts that carry absolute paths. It ships with mutation tests: one planted leak per detector, each shown to be caught only by its own detector. `SKILL.md` adds the step no scanner can do: a read-through for *structural* fingerprints. |

The scanner is a single Python script (3.9+, standard library only) and works without Claude Code. See the skill's own `README.md` for the ledger format, the detectors and their limits.

## License

MIT — see the repository root [`LICENSE`](../../LICENSE).
