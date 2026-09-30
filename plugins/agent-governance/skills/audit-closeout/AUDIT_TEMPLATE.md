# Audit round N (YYYY-MM-DD) · verdict: <PASS / FAIL / not converged>

<!-- Template. Copy to AUDIT-YYYY-MM-DD.md in the audited object's directory.
     Later rounds APPEND a new "# Audit round" section; never rewrite earlier rounds. -->

**Excluded from this round:** <e.g. A1–A13, B1–B6 from AUDIT-YYYY-MM-DD.md — or "none, first audit">

**How it was audited** (object type per SKILL.md §2):
- <reviewer role> — <scope: files / modules / scenarios> — evidence form: <…>
- <reviewer role> — …
- Main-thread review of reviewer conclusions: <which conclusions were accepted / rejected, and why>

---

## Critical

### C-1 · <one-line defect>

- **Symptom:** <what goes wrong, observed how>
- **Root cause:** <why> (`path/to/file.py:123`)
- **Reproduction:** <smallest input or command + actual vs expected output>
- **Blast radius:** <which deliverables / numbers / users are affected>
- **Fix:** <what changed> — root cause / containment only
- **Regression assertion:** <test name or command that fails on the old code>
- **Status:** open / fixed (round k) / containment only

## Medium

### M-1 · …

## Low / latent

### L-1 · …

---

## Convergence log

| Round | Full regression result | Run by | Clean? |
|---|---|---|---|
| 1 | <n pass / m fail> | <fixer / independent> | no |
| 2 | … | independent | yes |

## Checked and confirmed fine (don't re-investigate)

- <item> — <how it was checked>

## Could not verify

- <item> — <why not; what would be needed>

## Excluded from this round

- <item> — <reason>
