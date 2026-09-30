#!/usr/bin/env python3
"""Health check for the decision registry. Any ERROR -> exit code 1; WARN only -> 0.

The ERROR-level lints are the point of the whole thing -- especially E003,
E004 and E007: a card's claimed force must not be detached from how it is
guaranteed to reach context, an inference must never become a hard boundary,
and the always-loaded (resident) layer must not grow without limit.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import build_index
import registry as R


class Report:
    def __init__(self):
        self.errors: list = []
        self.warns: list = []

    def err(self, code, msg):
        self.errors.append(f"[{code}] {msg}")

    def warn(self, code, msg):
        self.warns.append(f"[{code}] {msg}")


def _d(v):
    """A malformed date returns None instead of raising, so audit reports a lint
    instead of crashing -- a crash would hide every ERROR/WARN collected so far."""
    if not v:
        return None
    return R.parse_iso_date(v)


def _archive_roots(rd: Path, schema: dict) -> list:
    rels = schema.get("archive_roots") or [".."]
    return [(rd / r).resolve() for r in rels]


def _check_archive(rep: Report, c, f, acq, rd, schema) -> None:
    """held_copy: confirm the archived original can be located.

    Uses `return`, never `continue` in the caller's loop: skipping out of the
    main loop would silently skip every later lint for this card.
    """
    if acq != "held_copy":
        return
    ref = str(c.get("archive_ref") or "")
    if not ref or ref.startswith(("http://", "https://")):
        rep.warn("W006", f"{f}: acquisition=held_copy but archive_ref cannot be checked (`{ref}`)")
        return
    norm = ref.replace("\\", "/")
    if "/" not in norm:
        rep.warn("W006", f"{f}: archive_ref `{ref}` has no directory component; "
                         f"cannot locate the archive tree")
        return
    p = Path(ref)
    if p.is_absolute():
        roots, rel = [Path(p.anchor)], Path(*p.parts[1:]).as_posix()
    else:
        roots, rel = _archive_roots(rd, schema), norm
    anchor = rel.split("/")[0]
    if any((r / rel).exists() for r in roots):
        return
    if any((r / anchor).exists() for r in roots):
        rep.err("E010", f"{f}: the archive tree exists but the file is missing: "
                        f"nothing at `{rel}` under {anchor}/")
    else:
        rep.warn("W004", f"{f}: archive tree `{anchor}/` is not present on this machine; "
                         f"archive_ref cannot be checked (this is not the same as 'lost')")


def lint(rd: Path) -> Report:
    rep = Report()
    schema = R.load_schema(rd)
    enums = schema["enums"]
    req = schema["required_fields"]
    try:
        cards = R.load_cards(rd)
    except R.CardError as e:
        rep.err("E015", f"a card cannot be read, the whole registry is unusable: {e}. "
                        f"check.py is unusable for everyone until it is fixed")
        rep.cards, rep.residents, rep.quota = [], [], schema["limits"]["resident_quota"]
        return rep
    by_id: dict = {}

    for c in cards:
        f = c["_file"]
        cid = c.get("id")

        # E001 required fields + enum values
        for k in req["_all"] + req.get(str(c.get("type") or ""), []):
            if c.get(k) in (None, "", [], {}):
                rep.err("E001", f"{f}: missing required field `{k}`")
        for k, allowed in enums.items():
            v = c.get(k)
            if v is not None and v not in allowed:
                rep.err("E001", f"{f}: `{k}` value `{v}` is not in the enum {allowed}")

        # E002 id vs file name / duplicate id / directory placement
        if not cid:
            rep.err("E002", f"{f}: no id")
        else:
            cid = str(cid)
            if not f.startswith(cid + "-"):
                rep.err("E002", f"{f}: file name prefix does not match id `{cid}`")
            if cid in by_id:
                rep.err("E002", f"{f}: id `{cid}` duplicates {by_id[cid]['_file']}")
            by_id[cid] = c
        want_dir = R.SUBDIRS.get(str(c.get("type") or ""))
        if want_dir and c["_subdir"] != want_dir:
            rep.err("E002", f"{f}: type={c.get('type')} belongs in {want_dir}/, "
                            f"found in {c['_subdir']}/")

        # E003 / E004 -- illegal combinations. The rules live in schema.json.
        for rule in schema.get("illegal_combinations", []):
            when_ok = all(c.get(k) == v for k, v in rule["when"].items())
            hit = all(c.get(k) == v for k, v in rule["forbid"].items())
            if when_ok and hit:
                w = ", ".join(f"{k}={v}" for k, v in rule["when"].items())
                b = ", ".join(f"{k}={v}" for k, v in rule["forbid"].items())
                rep.err(rule["code"], f"{f}: {w} cannot be combined with {b} -- {rule['why']}")

        # E011 internal and external authority ladders must not be mixed
        dom, tier = c.get("domain"), c.get("source_tier")
        allowed = schema.get("source_tier_by_domain", {}).get(dom)
        if allowed and tier and tier not in allowed:
            rep.err("E011", f"{f}: domain={dom} cannot use source_tier=`{tier}`; allowed: {allowed}")

        # E012 a text existing is not a boundary applying
        if dom == "external" and c.get("force") == "binding" and not c.get("applicability"):
            rep.err("E012", f"{f}: domain=external + force=binding requires `applicability` "
                            f"(why it applies to us and where that ends). If you cannot fill it "
                            f"in, applicability is unconfirmed, so it cannot be binding")

        # E014 scope structure and values. `[all]` instead of bare `all` makes the
        # card silently vanish from queries (fnmatch treats 'all' as a literal),
        # and silence reads as "no boundaries".
        try:
            sc = R.scope_of(c)
        except R.CardError as e:
            rep.err("E014", f"{f}: {e.msg}")
            sc = None
        if sc:
            for dim, vals in sc.items():
                if vals != "all" and any(str(v).strip().lower() == "all" for v in vals):
                    rep.err("E014", f"{f}: scope.{dim} lists `all` inside a list; the wildcard "
                                    f"must be a bare `{dim}: all`, otherwise the card silently "
                                    f"disappears from queries on that dimension")
            for a in (sc["activities"] if sc["activities"] != "all" else []):
                if a not in schema["activities"]:
                    rep.err("E014", f"{f}: scope.activities contains `{a}`, which is not in the "
                                    f"standard list; no --activity query will ever match it")

        # E009 acquisition companion field -- missing means "no way to re-verify"
        acq = c.get("acquisition")
        need = schema.get("acquisition_requires", {}).get(acq)
        if need and not c.get(need):
            rep.err("E009", f"{f}: acquisition={acq} requires `{need}` "
                            f"(how this will be re-verified)")

        _check_archive(rep, c, f, acq, rd, schema)

        # E005 a stance must state what would overturn it
        if c.get("type") == "stance" and not c.get("falsified_if"):
            rep.err("E005", f"{f}: stance without `falsified_if` -- a view nothing can "
                            f"overturn is dogma")

        # W005 binding with a broken trace. The rule itself still holds, so not an
        # ERROR -- but this is the priority queue for re-tracing and must be visible.
        if acq == "unrecorded" and c.get("force") == "binding":
            rep.warn("W005", f"{f}: binding but the trace is broken (unrecorded); re-acquire "
                             f"first: {c.get('reacquire') or 'no reacquire given'}")

        if not c.get("evidence"):
            rep.warn("W003", f"{f}: no `evidence`; the reasoning cannot be traced later")

        # E013 date format -- report it, do not silently treat it as "no review date"
        for k in ("verified", "review_by", "decided_on"):
            v = c.get(k)
            if v and _d(v) is None:
                rep.err("E013", f"{f}: `{k}: {v}` is not an ISO date (YYYY-MM-DD)")

        rb = _d(c.get("review_by"))
        if rb and rb < date.today() and c.get("status") == "active":
            rep.warn("W001", f"{f}: review_by {rb} is {(date.today() - rb).days} days overdue")

    # E006 supersede chain, checked from both sides. One side only would miss the
    # more common slip: "edited the new card, forgot the old one". Non-scalar
    # values are reported separately instead of raising TypeError on `in by_id`.
    for c in cards:
        for k in ("supersedes", "superseded_by"):
            tgt = c.get(k)
            if not tgt:
                continue
            if not isinstance(tgt, str):
                rep.err("E006", f"{c['_file']}: `{k}` must be a single card id, got "
                                f"{type(tgt).__name__}: {tgt!r}. To replace several cards, "
                                f"write one new card per replaced card")
                continue
            if tgt not in by_id:
                rep.err("E006", f"{c['_file']}: `{k}: {tgt}` points to a card that does not exist")
        if c.get("superseded_by") and c.get("status") != "superseded":
            rep.err("E006", f"{c['_file']}: has superseded_by but status is still "
                            f"`{c.get('status')}`")
        succ = c.get("superseded_by")
        if isinstance(succ, str) and succ in by_id and by_id[succ].get("supersedes") != c.get("id"):
            rep.err("E006", f"{c['_file']}: superseded_by {succ}, but {succ} has supersedes "
                            f"`{by_id[succ].get('supersedes')}`; the link is not closed both ways")
        sup = c.get("supersedes")
        if isinstance(sup, str) and sup in by_id:
            old = by_id[sup]
            if old.get("status") == "active":
                rep.err("E006", f"{c['_file']}: claims to supersede {sup}, but {sup} is still "
                                f"active -- both would be listed as current boundaries")
            if old.get("superseded_by") != c.get("id"):
                rep.err("E006", f"{c['_file']}: claims to supersede {sup}, but {sup} has "
                                f"superseded_by `{old.get('superseded_by')}`; the link is not "
                                f"closed both ways")

    # E007 resident quota
    quota = schema["limits"]["resident_quota"]
    residents = [c for c in cards
                 if c.get("enforcement") == "resident" and c.get("status") == "active"]
    if len(residents) > quota:
        names = ", ".join(str(c.get("id")) for c in residents)
        rep.err("E007", f"resident layer over quota: {len(residents)}/{quota} -- {names}. "
                        f"To add one, demote one first; a bloated resident layer means "
                        f"nothing is really resident")

    # E008 INDEX.json in sync with the cards
    idx_path = rd / "INDEX.json"
    if not idx_path.is_file():
        rep.err("E008", "INDEX.json is missing; run build_index.py")
    else:
        try:
            on_disk = json.loads(idx_path.read_text(encoding="utf-8")).get("cards")
        except ValueError:
            on_disk = None
        try:
            rebuilt = build_index.build(rd)["cards"]
        except R.CardError as e:
            rep.err("E014", f"{e.card_name}: {e.msg} (INDEX cannot be rebuilt)")
            rebuilt = None
        if rebuilt is not None and on_disk != rebuilt:
            rep.err("E008", "INDEX.json is out of sync with the cards; run build_index.py")

    # W002 two active binding cards with overlapping scope disagree on a threshold
    def metrics(c):
        hv = c.get("hard_value") or {}
        out = {}
        if isinstance(hv, dict):
            for t in hv.get("trigger_any", []) or []:
                if isinstance(t, dict) and t.get("metric"):
                    out[t["metric"]] = (t.get("op"), t.get("value"), t.get("unit"))
        return out

    act = [c for c in cards if c.get("status") == "active" and c.get("force") == "binding"]
    for i, a in enumerate(act):
        for b in act[i + 1:]:
            ma, mb = metrics(a), metrics(b)
            common = set(ma) & set(mb)
            try:
                overlap = bool(common) and R.dims_overlap(a, b)
            except R.CardError:
                continue  # already reported as E014
            if not overlap:
                continue
            for m in sorted(common):
                if ma[m] != mb[m]:
                    rep.warn("W002", f"{a.get('id')} and {b.get('id')} overlap in scope but "
                                     f"disagree on `{m}`: {ma[m]} vs {mb[m]}")

    rep.cards, rep.residents, rep.quota = cards, residents, quota
    return rep


def main(argv=None) -> int:
    R.utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    R.add_registry_arg(ap)
    a = ap.parse_args(argv)
    rd = R.resolve_or_exit(a.registry)
    rep = lint(rd)
    print(f"Registry: {rd}")
    print(f"{len(rep.cards)} cards (resident {len(rep.residents)}/{rep.quota})\n")
    for line in rep.errors:
        print("ERROR " + line)
    for line in rep.warns:
        print("WARN  " + line)
    if not rep.errors and not rep.warns:
        print("Clean.")
    elif not rep.errors:
        print(f"\nNo ERROR, {len(rep.warns)} WARN.")
    else:
        print(f"\n{len(rep.errors)} ERROR, {len(rep.warns)} WARN.")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
