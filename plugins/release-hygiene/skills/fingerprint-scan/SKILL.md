---
name: fingerprint-scan
description: Scan a source tree for numeric and structural fingerprints of private business facts before open-sourcing or publishing code, docs or examples derived from private or client work. Catches what secret scanners and denylists miss, such as real site areas, counts, template dimensions, coordinates, climate constants, percentages derived from a private dimension, private distributions, and build artifacts (__pycache__/.pyc with absolute paths). Unit conversion and rounding are handled. Use when the user says "check for leaked business numbers", "scan for fingerprints", "is this safe to open-source", "before we publish this repo", "strip project data from the examples", "did any real coordinates/areas slip into the tests", or is preparing a public release of work-derived code. Also includes a mandatory read-through protocol for structural fingerprints, which no scanner can see. Not for credentials (use a secret scanner) or for name/codename lists (use a denylist); run those as well.
---
<!-- fingerprint-scan: ignore-file (quotes the synthetic example ledger on purpose) -->

# fingerprint-scan

Credential scanners and denylists only stop **names**. Code taken from private work also carries
**numbers** that identify where it came from: a site area, a unit count, a template size, a surveyed
coordinate, a local climate constant, a ratio against a private dimension, or a build path inside a
`.pyc`. The shape of the code can identify it too, for example fixtures that mirror one jurisdiction's rules. This skill has
two parts, and both are mandatory before publishing:

1. **Automated scan** (`scripts/fingerprint_scan.py`) against a private ledger of facts.
2. **Read-through protocol** for structural fingerprints, which no scanner can find.

## When to use

- Before the first push of any repository, package, gist, article or example that was derived from
  private, client or employer work.
- After **every** round of fixes to such a tree (see "re-read after every fix round" below).
- When someone asks "is this safe to publish?" about work-derived code.

## Step 1: build the ledger (outside the repository)

Keep the ledger at a private path such as `~/.config/fingerprint-scan/ledger.txt`. **Never** put it,
its contents or the scan report into the tree, a commit message, a PR description or an issue.
The scanner raises HIGH if the ledger file is inside the scanned tree.

What counts as a fingerprint. Write down every one you can think of, at full private precision:

| kind | examples (write the private value) |
|---|---|
| areas | site / plot / boundary area, developable area |
| counts | number of units, buildings, parcels, sensors, test-layout size |
| dimensions | equipment size, template page or content-box width/height, margins |
| results | headline outputs of the private project (hours, yields, losses, prices) |
| coordinates | site centroids, reference points → put them in the **fences** file instead |
| climate / environment | site temperature, humidity, air density, probabilities measured at one place |
| derived | percentages or ratios against a private dimension → mark that dimension `base` |
| distributions | weekday or monthly profiles, any list of measured values → sequence entry |
| template sizes | company slide/report template dimensions, brand colour values if numeric |

Syntax (full reference in `README.md`, example in `examples/ledger.example.txt`):

```
site_area        = 6.83 km2                     # converted to m2, ha, acre ... automatically
unit_count       = 37 count  context=units      # <=2 significant digits: needs a context word
template_width   = 19.3 cm                      # also catches 19, 193 mm, 0.193 m
spool_diameter   = 52 cm base                   # flags x where x*52 (or x*52/100) is a nearby literal
derive template_width / template_height         # flags the ratio and its percent form
weekday_profile  = [2.6, 5.8, 7.1, 4.4, 3.9]    # flags any run of 4 consecutive matching literals
```

Only record values that are **distinctive**. Generic numbers such as 2, 10, 20 m or 0.6 match everywhere
and bury the real signal under hundreds of hits. Check those by hand: grep the private source for its
constants and compare them one by one. The scanner prints a note for facts that look generic.

Add `context=` keywords to short facts: the words that would sit next to that number in code
(for example `cure`, `fill`, `batch`). A fact with no context words can only be found when it is written in
full precision.

Fences file: `private` boxes or polygons around every real site (HIGH on any coordinate inside), plus
`synthetic` zones where demo coordinates are allowed. Put demo data in a synthetic zone (open ocean
works well). Precise coordinates anywhere else are MEDIUM.

## Step 2: run

```bash
python scripts/fingerprint_scan.py <export-tree> \
    --ledger ~/.config/fingerprint-scan/ledger.txt \
    --fences ~/.config/fingerprint-scan/fences.json \
    --fail-on medium > /tmp/fingerprint-report.md; echo "exit=$?"
```

Scan the **exact tree that will be pushed** (the staging/export directory), not the private source.
Check the header line: if "text files scanned" is 0 or far lower than expected, the scan did not
see the tree. Treat that as a failure, not a pass. A run without `--ledger` warns that its result
proves nothing about business numbers.

## Step 3: triage

For each HIGH and MEDIUM finding:

1. **Real fingerprint** → replace it with an invented value that is obviously synthetic. Do not
   round, scale or offset the private one, because rounded and converted forms are still fingerprints.
   Recompute dependent test expectations from the new value.
2. **Coincidence** (a textbook constant or a public spec value) → leave it, add
   `# fingerprint-scan: ignore (<why>)` on that line. Keep the reason generic and never name the private fact.
   Pragmas are deliberately weak, because **the author of a pragma is the party the scan protects against**:
   - on a ledger, derived, private-fence or absolute-path match, a line pragma only downgrades it to a visible LOW
     `SUPPRESSED (reason)` entry, and without a reason it does nothing;
   - `ignore-file` (first 10 lines) silences only the heuristic detectors (unfenced coordinates, UTM without
     a fence, irregular numbers), never private-fact matches.
   **Reviewers:** read the pragma/ignore-file list in the report header and every `SUPPRESSED` entry before
   approving a release.
3. **Build artifact** → delete it (`__pycache__`, `.DS_Store`), clear notebook outputs, and add the
   pattern to `.gitignore`.

LOW findings are review notes. Read them all in test and example files, because that is where
measured-looking numbers hide. Re-run the scan until it exits 0.

## Step 4: read-through protocol (mandatory, cannot be automated)

The scanner only finds values you listed. **Structural fingerprints** are relationships, not values.
A person, or an independent reviewer agent with no access to the ledger, must read every file of
the export tree **including tests, fixtures, examples and comments** and ask:

- **Pairing**: do fixture inputs line up one-to-one with specific real places or jurisdictions?
  Example: three test cases whose latitude bands each match one country's rule shape.
- **Single-customer mechanisms**: is there a parameter, branch or penalty that only one jurisdiction's
  or client's rule would need? A generic engine should not have one-off hooks whose origin is obvious.
- **Local taxonomies**: category lists, class codes or labels copied from a local classification
  (land use, forest types, zoning) that identify the country or agency.
- **Hedged notes**: comments such as "negotiable", "pending approval" or "per the client" that reveal a real
  negotiation or status.
- **Distributions and defaults**: default profiles, colour ramps, test layouts or random seeds reused
  from an internal demo.
- **Numbers the ledger forgot**: any constant you cannot explain from public sources. Add it to
  the ledger, then fix it.
- **Provenance**: text or config copied from a third party (licence and attribution); this is a separate
  check but it turns up in the same read-through.

Rules for the read-through:

1. **Read test files too.** Past incidents: every leak found after a "clean" gate run was in tests,
   fixtures or comments.
2. **Re-read after every fix round.** Replacing one number can expose or create another (a
   rounded variant, a recomputed expectation, a new comment). Keep going until one full pass finds nothing.
3. Give the reviewer the exact tree that will be pushed. A sibling directory or the private source may differ.
4. Never paste ledger contents into a review request. Describe the kinds of facts instead.

## Step 5: before the push

- Scanner exits 0 at `--fail-on medium` on the final tree.
- The last read-through pass after the last fix found nothing.
- No `__pycache__`, `.pyc`, `.DS_Store` or executed notebooks in the tree (`git status --ignored` on the export).
- The report and ledger are not in the tree and not in any commit.

## Maintaining the scanner

Any change to a detector must keep `python tests/test_mutants.py` fully green. That means a clean baseline,
every mutant killed, every mutant surviving when its own detector is disabled, and all controls clean.
When a new kind of leak is found in real use, add a mutant for it **before** fixing the detector,
and watch it survive first.
