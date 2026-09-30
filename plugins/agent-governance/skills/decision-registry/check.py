#!/usr/bin/env python3
"""Before starting work: list the registered boundaries that apply.

Output is a compact list, not full text -- one entry per card; the body stays
in the card and is read on demand. Three states are reported separately, and
"nothing registered" is always said out loud: silence gets read as "there are
no boundaries".
"""
from __future__ import annotations

import argparse
import fnmatch
import sys

import registry as R

ORDER = {"binding": 0, "guidance": 1, "assumption": 2}


def line(c) -> str:
    return (f"  {c.get('id')}  [{c.get('force')}/{c.get('enforcement')}] "
            f"{c.get('title')}\n"
            f"        -> {c.get('consequence')}   (source: {c.get('source_tier')}"
            f" | verified: {str(c.get('verified'))[:10]} | {c['_path']})")


def main(argv=None) -> int:
    R.utf8_stdio()
    ap = argparse.ArgumentParser(
        description="List the registered boundaries that apply to an activity / project / region")
    ap.add_argument("--activity", help="standard activity name (see `activities` in schema.json)")
    ap.add_argument("--project")
    ap.add_argument("--region")
    R.add_registry_arg(ap)
    a = ap.parse_args(argv)

    rd = R.resolve_or_exit(a.registry)
    schema = R.load_schema(rd)
    if a.activity and a.activity not in schema["activities"]:
        print(f"Activity `{a.activity}` is not in the standard list: {schema['activities']}",
              file=sys.stderr)
        return 2

    try:
        cards = R.load_cards(rd)
    except R.CardError as e:
        print(f"A card in the registry cannot be read; the result would be incomplete, "
              f"aborting: {e}", file=sys.stderr)
        return 3

    try:
        return _report(a, rd, cards)
    except R.CardError as e:
        print(f"A card in the registry is malformed; the boundary list would be "
              f"incomplete, aborting: {e}", file=sys.stderr)
        print("   Do not act on this output until that card is fixed.", file=sys.stderr)
        return 3


def _report(a, rd, cards) -> int:
    # Filter values that never appear in any card: matching is case-sensitive,
    # so `emea` and `EMEA` would silently return two different lists.
    seen = {"regions": set(), "projects": set()}
    for c in cards:
        sc = R.scope_of(c)
        for dim in seen:
            if sc[dim] != "all":
                seen[dim].update(str(x) for x in sc[dim])
    unknown = []
    for dim, val in (("regions", a.region), ("projects", a.project)):
        if val and not any(fnmatch.fnmatchcase(str(val), pat) for pat in seen[dim]):
            unknown.append((dim, val, sorted(seen[dim])))

    hit = [c for c in cards if R.matches(c, region=a.region, project=a.project,
                                         activity=a.activity)]
    active = sorted([c for c in hit if c.get("status") == "active"],
                    key=lambda c: (ORDER.get(c.get("force"), 9), str(c.get("id"))))
    dead = [c for c in hit if c.get("status") != "active"]

    q = " / ".join(x for x in [a.activity, a.project, a.region] if x) or "all"
    print(f"# Applicable boundaries -- {q}\n(registry {rd}, {len(cards)} cards)\n")
    for dim, val, known in unknown:
        label = {"regions": "Region", "projects": "Project"}[dim]
        print(f"WARNING: {label} `{val}` never appears in the registry "
              f"(registered values: {known or 'none'}).")
        print(f"   Only cards with scope.{dim}=all are listed below. Under-reporting is "
              f"more dangerous than an empty list because it does not announce itself. "
              f"Check case and spelling.\n")

    binding = [c for c in active if c.get("force") == "binding"]
    other = [c for c in active if c.get("force") != "binding"]

    if binding:
        print(f"## binding ({len(binding)}) -- crossing one invalidates the plan")
        for c in binding:
            print(line(c))
    else:
        print("## binding (0)")
        print("  WARNING: no binding boundary is registered for this scope. That does not "
              "mean there are none -- only that nobody has registered one.")

    if other:
        print(f"\n## guidance / assumption ({len(other)})")
        for c in other:
            print(line(c))

    if dead:
        print(f"\n## no longer in force, for traceability only ({len(dead)}) -- do not act on these")
        for c in dead:
            print(f"  {c.get('id')}  [{c.get('status')}] {c.get('title')}"
                  f"{'  -> ' + str(c['superseded_by']) if c.get('superseded_by') else ''}")

    if not hit:
        print("\n(Nothing registered for this scope. Before proceeding, consider whether a "
              "card should be added.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
