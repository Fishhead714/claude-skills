<!-- fingerprint-scan: ignore-file (quotes the synthetic example ledger on purpose) -->
# fingerprint-scan

Find the **numbers** that give away where your code came from, before you publish it.

When code written for private work is open-sourced, the usual gates are credential
scanners (gitleaks, trufflehog) and a denylist of names (client, project, codename).
Both look for *strings that are secret*. Neither notices:

- a real site area left in an example as a plain number, or the same area converted to m² in a test;
- a real count ("tested on N units") in a comment;
- a company template dimension, or the same dimension **rounded** to an integer;
- a percentage computed from a private dimension (value / private diameter × 100);
- an irregular, surveyed-looking coordinate (lat/lon or UTM) in a fixture;
- climate constants, distributions or profiles measured at one specific place;
- `__pycache__/*.pyc` files that embed the absolute path of the machine that built them.

None of these is a secret by itself. Together they identify a site, a client or an
employer. In practice they survive several review rounds because every review
checks for *names*. `fingerprint-scan` checks the numbers.

## What it catches (and what it does not)

| | secret scanners / denylists | fingerprint-scan |
|---|---|---|
| API keys, tokens, private keys | yes | no (use a secret scanner) |
| client/project names | denylist | no (use a denylist) |
| private quantities, in any unit, rounded or exact | no | **ledger** detector |
| ratios / percentages of private quantities | no | **derived** detector |
| private distributions (a run of values) | no | **ledger** (sequences) |
| coordinates inside private areas; precise real-looking coordinates | partly (regex) | **coords** detector (fences + precision) |
| "measured-looking" numbers in tests/examples | no | **irregular** detector (low, for review) |
| build artifacts, absolute paths in `.pyc`/binaries/text | partly | **artifacts** detector |
| *structural* fingerprints (e.g. fixtures that mirror one jurisdiction's rules) | no | no: needs a human read-through (see `SKILL.md`) |

## Quick start

Python 3.9+, standard library only. No install needed.

```bash
# 1. Write a private ledger OUTSIDE the repository (see examples/ledger.example.txt)
mkdir -p ~/.config/fingerprint-scan
cp examples/ledger.example.txt ~/.config/fingerprint-scan/ledger.txt   # then replace every value

# 2. Scan the tree you are about to publish
python scripts/fingerprint_scan.py path/to/export \
    --ledger ~/.config/fingerprint-scan/ledger.txt \
    --fences ~/.config/fingerprint-scan/fences.json \
    --fail-on medium            # exit 1 if anything MEDIUM or HIGH is found

# JSON for tooling, hide LOW notes
python scripts/fingerprint_scan.py path/to/export --ledger ... --format json --min-severity medium
```

Exit codes: `0` nothing at/above `--fail-on`, `1` findings at/above `--fail-on`, `2` usage/ledger error.
Running without `--ledger` prints a warning that a clean result is **not** evidence of absence.

Example output (illustrative: produced with a separate invented ledger, not the one in `examples/`;
run the command above on your own tree to see real output):

```
## src/a.py
- L1 **HIGH** ledger: `6830000` exact match: site_area = 6.83 km2 (as m2)
- L2 **MEDIUM** ledger: `19` rounded match: template_width = 19.3 cm
## tests/test_a.py
- L1 **HIGH** coords: `-33.4172, -22.8391` lat/lon pair inside private fence 'site-X'
- L2 **LOW** irregular: `5283.17` non-round literal in test/example; confirm it is synthetic
```

The report quotes ledger entry names and matched lines. Treat it as private and do not commit it.

## The ledger

One fact per line; `#` starts a comment. Also accepted as JSON (`{"facts": [...], "derive": [...], "sequences": [...]}`).

```
name = value [unit] [weak|strong] [base] [context=kw1,kw2] [tol=0.5%]
derive name_a / name_b          # also flags the percent form
derive name_a * name_b
name = [v1, v2, v3, ...] [min_run=4]   # a distribution or profile
```

- **Units** are converted within their dimension: length (mm, cm, m, km, in, ft, mi), area
  (mm², cm², m², ha, km², acre, ft²), mass, power, energy, speed, time, ratio (fraction, %, ‰),
  angle, temperature (°C, °F, K). Unknown units are matched as written.
- **Rounding**: a literal matches if the fact, rounded to the precision the literal is written
  with, equals it (`19.3` matches `19`, `19.3`, `193` mm, `0.193` m). Roundings must keep at least
  2 significant digits. Record facts at full private precision; they are treated as exact.
  Use `tol=` only for facts that are approximate themselves.
- **Weak facts**: values with at most 2 significant digits (and anything marked `weak`) only
  match when a context word is on the same or previous line: a token of the fact name, a
  `context=` keyword, or the unit written next to the number. Common numbers (0 to 16, one
  significant digit, powers of two, 90/180/360 and similar) follow the same rule. This is how
  a count of 37 can be in the ledger without flagging every `37` in the tree.
- **`base`** marks a private dimension that other numbers may have been divided by. The scanner
  flags a literal `x` (3+ significant digits) when `x × base` or `x × base / 100` equals another
  literal within 50 lines, for example a height and its "fraction of the private diameter".
- **`derive`** declares explicit ratios or products of two facts.

## Fences

A JSON file with `private` zones (coordinates inside are HIGH), `synthetic` zones (declared demo
areas where coordinates are allowed), and the same two lists for UTM boxes (`private_utm`,
`synthetic_utm`). Zones are `bbox: [min_lon, min_lat, max_lon, max_lat]` or `polygon: [[lon, lat], ...]`.
A GeoJSON FeatureCollection works too (`properties.kind` = `private` or `synthetic`; `properties.utm` for
UTM boxes). See `examples/fences.example.json`, where every zone is open ocean.

Without fences, coordinates are judged by precision only: a pair with 4 or more decimals that is
not in a synthetic zone is MEDIUM. So put demo data in a declared synthetic zone.

## Severity

- **HIGH**: exact or full-precision match of a fact, a run of a private sequence, a coordinate inside
  a private fence, an absolute user or build path inside a `.pyc`, binary or text file, the ledger file inside the tree.
- **MEDIUM**: rounded matches, weak facts with context, derived values, precise coordinates outside
  synthetic zones, irregular UTM-like pairs, build artifacts (`__pycache__`, `.DS_Store`, executed notebooks).
- **LOW**: review notes, e.g. coarse coincidences without context, conversions into imperial units
  without the unit written next to the number, irregular literals in test/example files, numbers inside
  identifiers, textbook constants.

Context lowers severity when missing. A ledger match whose literal has **3 or fewer significant digits** and has
no context (no unit next to it, no fact-name token or `context=` keyword on the same or previous line) is
reported **one level lower**: HIGH becomes MEDIUM, MEDIUM becomes LOW. Weak facts and common numbers (see
above) are not reported at all without context.

**Pragmas are limited on purpose.** The author of a pragma is the party the scan protects against: whoever
writes the pragma is the person who might be leaking. So an in-tree marker can never silence a private-fact match:

- `fingerprint-scan: ignore (reason)` at the end of a line removes *heuristic* findings on that line
  (unfenced coordinates, UTM pairs without a fence, irregular numbers). A ledger, derived, private-fence
  or absolute-path match on that line is only **downgraded to a visible LOW entry** that reads `SUPPRESSED (reason); was HIGH: ...`.
  If there is no reason in parentheses, the pragma is ignored for those matches and they keep full severity.
- `fingerprint-scan: ignore-file` in the first 10 lines of a file silences only the heuristic detectors for
  that file. Ledger, derived, private-fence and artifact findings are still reported at full severity.
- The report header counts suppressions and lists every file that carries `ignore-file`. Reviewers should
  read that list and the `SUPPRESSED` entries. A reason that names or hints at a private fact is itself a leak.

The ledger and fence files in use are never scanned against themselves. Inside the tree they are HIGH, unless they contain the marker `fingerprint-scan: synthetic-example`
(as `examples/` here does). Delete that marker when you copy the example to hold real values.

Numbers inside identifiers or file names (`py3x`, `utf-8`, `x86_64`, `abc-123`, `name_437`) are not
quantities. A ledger or derived match there is kept as a LOW "number inside identifier" note, because an
identifier can still carry a real value. Coordinate and irregular checks skip them. Dotted version strings
(`1.2.3`) are never read as numbers.

A number pair in which either value is a textbook constant (unit factors, square roots, physical constants)
is ignored as a coordinate. A lat/lon pair inside a comma-separated run of 4 or more numbers (constant tables,
data rows) is only a LOW note. Both rules give way to fences: a pair inside a private fence is always HIGH. UTM pairs outside
private fences are only considered when the easting is in the valid band (166000 to 834000).

## Mutation tests: prove the checker can see its target

A checker that reports all-green has proven nothing unless it can be shown to go red. The test
suite is built around that:

- `tests/test_mutants.py` builds a clean synthetic tree (it must produce zero MEDIUM/HIGH
  findings), then plants **one fingerprint per mutant**: unit-converted, rounded, thousands-separated,
  scientific-notation, weak-with-context, temperature in °F, percent as a fraction, sequence runs,
  derived ratios and percents, base co-occurrence, fenced lat/lon in both orders, hemisphere notation,
  keyed lat/lon on separate lines, polygon fences, UTM pairs, `.pyc` files with home, Windows and
  build paths, executed notebooks, and others. Each must be **killed** by its detector at the expected severity.
- **Isolation**: each mutant is re-run with its detector disabled and must then *survive*. This
  shows the expected detector did the work and not another one by accident.
- **Controls**: look-alikes (a weak count with no context, a version string, a placeholder home path,
  a coordinate in a synthetic zone, a pragma-suppressed line) must stay below MEDIUM.
- **Sabotage tests** (`tests/test_core.py`) break a capability (unit conversion, rounding, fences)
  and assert that the mutant harness notices, so the harness itself can fail.

```bash
python tests/test_mutants.py            # prints the killed/survived table
python -m unittest discover -s tests    # everything
```

## Limitations

- **Structural fingerprints are invisible to it.** Examples: test fixtures whose latitude bands pair
  one-to-one with the rule shapes of specific jurisdictions, a mechanism that only one jurisdiction's
  rule needs, or category lists copied from a local classification. Only a human read-through catches these.
- **It only finds what the ledger names.** A private number you did not think to record passes. The
  irregular detector is a heuristic safety net, limited to test/example paths and LOW severity.
- **Derived values** cover declared `derive` pairs and `base` co-occurrence only. A percentage whose
  numerator lives in another file, or a chain of two operations, is not found.
- **Rounding** means rounding to the written precision. Truncation (19.3 → 18), ranges ("about 30 to 40"),
  numbers spelled out in words, European decimal commas (`4,37`), space-grouped thousands (`4 370 000`),
  DMS coordinates (40°26'46") and numbers in images or PDFs are not recognised.
- **Coincidences happen.** Short facts and common units produce occasional false positives. The severity
  model sends most of them to LOW, but a person still has to triage the report.
- **Binary files** are only checked for absolute paths; their content is not decoded.
- It does not replace a secret scanner or a denylist. Run all three.
