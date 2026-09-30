#!/usr/bin/env python3
"""Scaffold a new decision registry.

Creates schema.json, README.md, _templates/, empty constraints/ decisions/
stances/ _inbox/, and INDEX.json. With --with-examples, also writes three
obviously fictional example cards (company "Example Co.") so you can see a
clean registry pass audit before writing your own.

Refuses to touch a directory that already contains a schema.json.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

import add
import build_index
import registry as R

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"

IGNORE_TXT = """\
# Paths (relative to the scan root) that scan_candidates.py should never queue again.
# One per line. Lines starting with # are comments.
"""

EXAMPLES = {
    "constraints/C-001-prices-are-never-quoted-to-customers-without.md": """\
---
id: C-001
type: constraint
domain: internal
title: Prices are never quoted to customers without finance sign-off
force: binding
status: active
enforcement: resident
scope:
  regions: all
  projects: all
  activities: [customer-email, pricing]
source: Example Co. Sales Policy v3, section 4.2 (fictional)
source_tier: policy-document
acquisition: public_source
source_url: https://intranet.example.com/policies/sales-v3#4.2
verified: {today}
review_by: {review_policy}
consequence: Any draft that states a price to a customer is held until finance signs off; an agent drafting customer text must leave prices as placeholders
evidence: [notes/example-sales-policy-summary.md]
hard_value: {{}}
tags: [example, pricing]
---

## Boundary

No price, discount or rate is sent to a customer (written or verbal) unless
finance has signed it off. Drafts may contain `[PRICE - pending finance]`.

## Why resident

It applies to every piece of customer-facing text, and violating it produces
no error -- just an email that cannot be taken back. High cost x high chance of
being ignored, so it earns one of the resident slots.

## Still unclear

Nothing. (This is a fictional example card.)
""",
    "decisions/D-001-all-deliverables-use-metric-units.md": """\
---
id: D-001
type: decision
domain: internal
title: All deliverables use metric units
force: binding
status: active
enforcement: skill
scope:
  regions: all
  projects: all
  activities: [customer-email, release]
source: Example Co. engineering leads meeting (fictional)
source_tier: meeting-resolution
acquisition: human_only
asked: Minutes of the fictional engineering leads meeting; ask the meeting chair to re-confirm
decided_on: {today}
decided_by: Example Co. engineering leads
alternatives_rejected:
  - "Imperial for some customers: rejected, mixed units caused conversion errors"
  - "Dual units everywhere: rejected, doubles review effort"
verified: {today}
review_by: {review_meeting}
consequence: If someone proposes imperial or dual units again, point to this card; changing it requires a new decision card that supersedes this one
evidence: [notes/example-units-meeting.md]
supersedes:
superseded_by:
tags: [example, units]
---

## Decision

Every deliverable (reports, drawings, spreadsheets, customer documents) uses SI
units only.

## Rejected paths

- Imperial units for some customers -- mixed units caused conversion errors.
- Dual units everywhere -- doubles the review effort for little benefit.

## Open questions / reason for review

None. (This is a fictional example card.)
""",
    "stances/S-001-supplier-lead-time-is-about-12-weeks.md": """\
---
id: S-001
type: stance
domain: internal
title: Supplier lead time is about 12 weeks
force: guidance
status: active
enforcement: retrieved
confidence: medium
falsified_if: Two consecutive orders arrive in under 8 weeks, or the supplier states a different lead time in writing
scope:
  regions: all
  projects: all
  activities: [release, incident-response]
source: Inferred from the last three (fictional) Example Co. purchase orders
source_tier: my-inference
acquisition: human_only
asked: Purchasing lead (fictional), when the last order arrived
verified: {today}
review_by: {review_inference}
consequence: Release and spare-hardware plans assume ~12 weeks; if acted on and wrong, schedules slip or stock sits idle
evidence: [notes/example-purchase-orders.md]
tags: [example, lead-time]
---

## View

Lead time for the main (fictional) supplier is about 12 weeks.

## Support

Three past orders took 11, 12 and 13 weeks.

## What would overturn it

See `falsified_if` in the frontmatter. Because the source is `my-inference`,
this card cannot be `binding` (E003) and is reviewed every 3 months.
""",
}


def scaffold(target: Path, with_examples: bool) -> None:
    if (target / "schema.json").exists():
        raise SystemExit(f"error: {target} already contains schema.json; refusing to overwrite "
                         f"an existing registry")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ASSETS / "schema.json", target / "schema.json")
    shutil.copyfile(ASSETS / "README.md", target / "README.md")
    tdir = target / "_templates"
    tdir.mkdir(exist_ok=True)
    for t in sorted((ASSETS / "_templates").glob("*.md")):
        shutil.copyfile(t, tdir / t.name)
    for sub in list(R.SUBDIRS.values()) + ["_inbox"]:
        (target / sub).mkdir(exist_ok=True)
    ig = target / "_inbox" / "IGNORE.txt"
    if not ig.exists():
        ig.write_text(IGNORE_TXT, encoding="utf-8")

    if with_examples:
        schema = R.load_schema(target)
        today = date.today()
        rm = schema["review_months"]
        fill = {
            "today": today.isoformat(),
            "review_policy": add._months_later(today, rm["policy-document"]).isoformat(),
            "review_meeting": add._months_later(today, rm["meeting-resolution"]).isoformat(),
            "review_inference": add._months_later(today, rm["my-inference"]).isoformat(),
        }
        for rel, text in EXAMPLES.items():
            (target / rel).write_text(text.format(**fill), encoding="utf-8")
    build_index.write(target)


def main(argv=None) -> int:
    R.utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", nargs="?", default=R.REGISTRY_DIRNAME,
                    help=f"directory to create (default ./{R.REGISTRY_DIRNAME})")
    ap.add_argument("--with-examples", action="store_true",
                    help="also write three fictional example cards")
    a = ap.parse_args(argv)
    target = Path(a.path).expanduser().resolve()
    scaffold(target, a.with_examples)
    print(f"Created decision registry at {target}")
    if target.name != R.REGISTRY_DIRNAME:
        print(f"Note: the directory is not named `{R.REGISTRY_DIRNAME}`, so the walk-up search "
              f"will not find it. Use --registry {target} or set {R.ENV_VAR}={target}.")
    print("Next: edit `activities` in schema.json to match your work, then run audit.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
