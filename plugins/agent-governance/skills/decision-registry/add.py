#!/usr/bin/env python3
"""Create / re-verify / supersede cards -- the only supported way to enroll.

Copying a template by hand goes wrong, and the worst failure is not an audit
error but a card that passes audit with a wrong field. So enrollment goes
through here, and these rules are enforced at *creation* time, not left to audit:
  - source / source_tier / consequence are required ("no traceable source, no card")
  - a stance needs falsified_if, a decision needs decided_by
  - illegal combinations from schema.json are refused (E003, E004, ...)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date

import build_index
import miniyaml
import registry as R

PREFIX = {"constraint": "C", "decision": "D", "stance": "S"}
DEFAULT_FORCE = {"constraint": "binding", "decision": "binding", "stance": "guidance"}
COMPANIONS = ("source_url", "archive_ref", "asked", "reacquire")


def _months_later(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year = d.year + y
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    day = min(d.day, [31, 29 if leap else 28, 31, 30, 31, 30,
                      31, 31, 30, 31, 30, 31][m])
    return date(year, m + 1, day)


def next_id(cards, typ: str) -> str:
    pre = PREFIX[typ]
    used = []
    for c in cards:
        m = re.fullmatch(rf"{pre}-(\d+)", str(c.get("id") or ""))
        if m:
            used.append(int(m.group(1)))
    return f"{pre}-{max(used, default=0) + 1:03d}"


def slug(title: str, limit: int = 40) -> str:
    s = re.sub(r"[^\w]+", "-", title, flags=re.UNICODE).strip("-_").lower()
    return s[:limit].rstrip("-_") or "untitled"


def check_illegal(schema: dict, fields: dict) -> None:
    for rule in schema.get("illegal_combinations", []):
        if all(fields.get(k) == v for k, v in rule["when"].items()) and \
           all(fields.get(k) == v for k, v in rule["forbid"].items()):
            w = ", ".join(f"{k}={v}" for k, v in rule["when"].items())
            b = ", ".join(f"{k}={v}" for k, v in rule["forbid"].items())
            raise SystemExit(f"Refused [{rule['code']}]: {w} cannot be combined with {b}\n"
                             f"  {rule['why']}")


yq = miniyaml.dump_scalar


def _scope_dim(vals) -> str:
    if not vals or vals == ["all"]:
        return "all"
    # Dump the whole flow list at once: in a flow sequence the comma is a
    # separator, so `a,b` must be quoted there even though it is plain-safe
    # in block context. Otherwise it is silently split into two values.
    return miniyaml.dump_flow_list([str(v) for v in vals])


def render(f: dict, typ: str) -> str:
    head = [
        f"id: {f['id']}", f"type: {typ}", f"domain: {f['domain']}",
        f"title: {yq(f['title'])}", f"force: {f['force']}", f"status: {f['status']}",
        f"enforcement: {f['enforcement']}",
    ]
    if typ == "stance":
        head += [f"confidence: {yq(f['confidence'])}", f"falsified_if: {yq(f['falsified_if'])}"]
    head += [
        "scope:",
        f"  regions: {_scope_dim(f['regions'])}",
        f"  projects: {_scope_dim(f['projects'])}",
        f"  activities: {_scope_dim(f['activities'])}",
        f"source: {yq(f['source'])}", f"source_tier: {f['source_tier']}",
    ]
    if f.get("applicability"):
        head.append(f"applicability: {yq(f['applicability'])}")
    head.append(f"acquisition: {f['acquisition']}")
    need = f["_need"]
    head.append(f"{need}: {yq(f[need])}")
    if typ == "decision":
        head += [f"decided_on: {yq(f['decided_on'])}", f"decided_by: {yq(f['decided_by'])}",
                 "alternatives_rejected: []"]
    head += [
        f"verified: {f['verified']}", f"review_by: {f['review_by']}",
        f"consequence: {yq(f['consequence'])}", "evidence: []",
    ]
    if typ == "constraint":
        head.append("hard_value: {}")
    if f.get("supersedes"):
        head.append(f"supersedes: {yq(f['supersedes'])}")
    head.append("tags: []")

    body = {
        "constraint": "## Boundary\n\n(to fill in)\n\n## Still unclear\n\n"
                      "(Be honest. Write \"nothing\" if nothing.)\n",
        "decision": "## Decision\n\n(to fill in)\n\n## Rejected paths\n\n"
                    "(A decision card without this section is useless six months later.)\n\n"
                    "## Open questions / reason for review\n\n",
        "stance": "## View\n\n(to fill in)\n\n## Support\n\n## What would overturn it\n\n"
                  "See `falsified_if` in the frontmatter.\n",
    }[typ]
    return "---\n" + "\n".join(head) + "\n---\n\n" + body


def _fm_end(lines, what: str) -> int:
    # column-0 delimiters only, same rule as registry._split_frontmatter
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip() == "---"), None)
    if end is None or not lines or lines[0].rstrip() != "---":
        raise SystemExit(f"error: {what}: frontmatter is not closed; cannot rewrite it "
                         f"automatically. Fix the card by hand first.")
    return end


def set_fm(text: str, key: str, value: str, what: str = "card") -> str:
    """Replace/insert one *scalar* frontmatter field (not for block fields like scope)."""
    lines = text.split("\n")
    end = _fm_end(lines, what)
    for i in range(1, end):
        if re.match(rf"^{re.escape(key)}:", lines[i]):
            # Swallow continuation lines (indented or blank). Replacing only the
            # first line would leave the old value's tail glued to the new one.
            j = i + 1
            while j < end and (lines[j] == "" or lines[j][:1].isspace()):
                j += 1
            lines[i:j] = [f"{key}: {value}"]
            return "\n".join(lines)
    lines.insert(end, f"{key}: {value}")
    return "\n".join(lines)


def drop_fm(text: str, key: str, what: str = "card") -> str:
    lines = text.split("\n")
    end = _fm_end(lines, what)
    for i in range(1, end):
        if re.match(rf"^{re.escape(key)}:", lines[i]):
            j = i + 1
            while j < end and (lines[j] == "" or lines[j][:1].isspace()):
                j += 1
            del lines[i:j]
            return "\n".join(lines)
    return text


def log_change(text: str, entry: str) -> str:
    if "\n## Change log\n" in text:
        return text.rstrip() + f"\n{entry}\n"
    return text.rstrip() + f"\n\n## Change log\n\n{entry}\n"


def add_common(p) -> None:
    p.add_argument("--title", required=True)
    p.add_argument("--source", required=True,
                   help="where this comes from. If you cannot trace it, do not create the card")
    p.add_argument("--source-tier", required=True,
                   help="see `source_tier_by_domain` in schema.json")
    p.add_argument("--consequence", required=True, help="what happens if it is crossed, one line")
    p.add_argument("--force", help="binding | guidance | assumption (default depends on type)")
    p.add_argument("--enforcement", default="skill")
    p.add_argument("--domain", default="internal")
    p.add_argument("--acquisition", required=True,
                   help="how this will be re-verified: public_source | held_copy | "
                        "human_only | unrecorded")
    p.add_argument("--source-url", help="required when acquisition=public_source")
    p.add_argument("--archive-ref", help="required when acquisition=held_copy")
    p.add_argument("--asked", help="required when acquisition=human_only: who / when / where")
    p.add_argument("--reacquire",
                   help="required when acquisition=unrecorded: how to obtain the original again")
    p.add_argument("--applicability",
                   help="required when domain=external and force=binding: why it applies to us "
                        "and where its applicability ends")
    p.add_argument("--regions", nargs="*")
    p.add_argument("--projects", nargs="*")
    p.add_argument("--activities", nargs="*")
    p.add_argument("--falsified-if", help="required for stance")
    p.add_argument("--confidence", default="medium")
    p.add_argument("--decided-by", help="required for decision")
    p.add_argument("--decided-on", help="YYYY-MM-DD, default today")


def build_fields(a, typ, schema, cards, supersedes=None) -> dict:
    today = date.today()
    tier = a.source_tier
    if tier not in schema["enums"]["source_tier"]:
        raise SystemExit(f"source_tier `{tier}` is not in the enum: {schema['enums']['source_tier']}")
    months = schema["review_months"].get(tier, 12)
    for v in a.activities or []:
        if v not in schema["activities"]:
            raise SystemExit(f"Activity `{v}` is not in the standard list: {schema['activities']}")
    f = {
        "id": next_id(cards, typ), "title": a.title, "domain": a.domain,
        "force": a.force or DEFAULT_FORCE[typ], "status": "active",
        "enforcement": a.enforcement, "regions": a.regions,
        "projects": a.projects, "activities": a.activities,
        "source": a.source, "source_tier": tier,
        "verified": today.isoformat(),
        "review_by": _months_later(today, months).isoformat(),
        "consequence": a.consequence, "confidence": a.confidence,
        "falsified_if": a.falsified_if, "decided_by": a.decided_by,
        "decided_on": a.decided_on or today.isoformat(),
        "supersedes": supersedes, "acquisition": a.acquisition,
        "source_url": a.source_url, "archive_ref": a.archive_ref, "asked": a.asked,
        "reacquire": a.reacquire, "applicability": a.applicability,
    }
    if f["acquisition"] not in schema["enums"]["acquisition"]:
        raise SystemExit(f"acquisition `{f['acquisition']}` is not in the enum: "
                         f"{schema['enums']['acquisition']}")
    need = schema["acquisition_requires"][f["acquisition"]]
    if not f.get(need):
        raise SystemExit(f"acquisition={f['acquisition']} requires --{need.replace('_', '-')}"
                         f" -- without saying how it will be re-verified, this card is dead "
                         f"on its review date")
    f["_need"] = need
    if typ == "stance" and not f["falsified_if"]:
        raise SystemExit("A stance requires --falsified-if -- a view nothing can overturn is dogma")
    if typ == "decision" and not f["decided_by"]:
        raise SystemExit("A decision requires --decided-by")
    if typ == "stance" and f["confidence"] not in schema["enums"]["confidence"]:
        raise SystemExit(f"confidence `{f['confidence']}` is not in the enum: "
                         f"{schema['enums']['confidence']}")
    for k in ("decided_on", "verified", "review_by"):
        v = f.get(k)
        if v and R.parse_iso_date(v) is None:
            raise SystemExit(f"{k} `{v}` is not an ISO date (YYYY-MM-DD). Refused before "
                             f"writing: a bad date on disk would break every later read")
    for k in ("force", "enforcement", "domain"):
        if f[k] not in schema["enums"][k]:
            raise SystemExit(f"{k} `{f[k]}` is not in the enum: {schema['enums'][k]}")
    allowed = schema.get("source_tier_by_domain", {}).get(f["domain"])
    if allowed and tier not in allowed:
        raise SystemExit(f"domain={f['domain']} cannot use source_tier=`{tier}`; allowed: {allowed}")
    if f["domain"] == "external" and f["force"] == "binding" and not f["applicability"]:
        raise SystemExit("domain=external + force=binding requires --applicability -- a text "
                         "existing is not the same as it applying; if you cannot fill this in, "
                         "applicability is not confirmed yet")
    check_illegal(schema, f)
    return f


def card_path(rd, typ, fields):
    return rd / R.SUBDIRS[typ] / f"{fields['id']}-{slug(fields['title'])}.md"


def cmd_new(a, rd, schema, cards) -> int:
    f = build_fields(a, a.type, schema, cards)
    path = card_path(rd, a.type, f)
    if path.exists():
        raise SystemExit(f"Already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(f, a.type), encoding="utf-8")
    build_index.write(rd)
    print(f"Created {f['id']} -> {path}")
    print(f"Review by {f['review_by']} (source_tier={f['source_tier']} -> "
          f"{schema['review_months'].get(f['source_tier'], 12)} months)")
    print("Next: fill in the body and evidence, then run audit.py")
    return 0


def cmd_verify(a, rd, schema, by_id) -> int:
    c = by_id.get(a.id)
    if c is None:
        raise SystemExit(f"No card with id {a.id}")
    p = rd / c["_path"]
    t = p.read_text(encoding="utf-8")
    tier = a.source_tier or c.get("source_tier")
    if tier not in schema["enums"]["source_tier"]:
        raise SystemExit(f"source_tier `{tier}` is not in the enum")
    # verify is a modification path: it must pass the same gates as `new`.
    # Otherwise a card could be turned into a state `new` refuses, and check.py
    # would keep serving it as a live boundary until the next audit.
    probe = dict(c)
    probe["source_tier"] = tier
    if a.acquisition:
        probe["acquisition"] = a.acquisition
    check_illegal(schema, probe)
    allowed = schema.get("source_tier_by_domain", {}).get(probe.get("domain"))
    if allowed and tier not in allowed:
        raise SystemExit(f"domain={probe.get('domain')} cannot use source_tier=`{tier}`; "
                         f"allowed: {allowed}")

    today = date.today()
    rb = _months_later(today, schema["review_months"].get(tier, 12))
    t = set_fm(t, "verified", today.isoformat(), c["_file"])
    t = set_fm(t, "review_by", rb.isoformat(), c["_file"])
    if a.source_tier:
        t = set_fm(t, "source_tier", tier, c["_file"])

    given = {"archive_ref": a.archive_ref, "source_url": a.source_url,
             "asked": a.asked, "reacquire": a.reacquire}
    if a.acquisition:
        if a.acquisition not in schema["enums"]["acquisition"]:
            raise SystemExit(f"acquisition `{a.acquisition}` is not in the enum")
        need = schema["acquisition_requires"][a.acquisition]
        if not given[need]:
            raise SystemExit(f"Moving to {a.acquisition} requires --{need.replace('_', '-')}")
        extra = [k for k, v in given.items() if v and k != need]
        if extra:
            raise SystemExit(f"acquisition={a.acquisition} goes with `{need}`, but {extra} "
                             f"were also given -- that would leave a self-contradicting card")
        t = set_fm(t, "acquisition", a.acquisition, c["_file"])
        t = set_fm(t, need, yq(given[need]), c["_file"])
        # Drop the previous tier's companion field; otherwise a card could claim
        # both "original on file" and "trace is broken, re-acquire it", and E009
        # only checks that the required one is present.
        for k in COMPANIONS:
            if k != need:
                t = drop_fm(t, k, c["_file"])
    else:
        for k in COMPANIONS:
            if given[k]:
                t = set_fm(t, k, yq(given[k]), c["_file"])
    note = f" ({a.note})" if a.note else ""
    t = log_change(t, f"- {today.isoformat()} re-verified, source_tier={tier}, "
                      f"review extended to {rb.isoformat()}{note}")
    p.write_text(t, encoding="utf-8")
    build_index.write(rd)
    print(f"{a.id} re-verified -> verified={today} review_by={rb}")
    return 0


def cmd_supersede(a, rd, schema, cards, by_id) -> int:
    old = by_id.get(a.id)
    if old is None:
        raise SystemExit(f"No card with id {a.id}")
    if old.get("status") != "active":
        raise SystemExit(f"{a.id} is `{old.get('status')}`, not active; supersede the card "
                         f"that replaced it instead ({old.get('superseded_by') or 'none recorded'})")
    typ = old.get("type")
    f = build_fields(a, typ, schema, cards, supersedes=a.id)
    path = card_path(rd, typ, f)
    if path.exists():
        raise SystemExit(f"Already exists: {path}")
    # All or nothing. Both cards are fully written to temp files first; then
    # the new card is moved into place, then the old card. If the second move
    # fails, the first is rolled back, so two contradicting active cards never
    # coexist and the old card is never half-written.
    op = rd / old["_path"]
    t = op.read_text(encoding="utf-8")
    t = set_fm(t, "status", "superseded", old["_file"])
    t = set_fm(t, "superseded_by", f["id"], old["_file"])
    t = log_change(t, f"- {date.today().isoformat()} superseded by {f['id']}")
    new_tmp = path.with_name(path.name + ".tmp")
    old_tmp = op.with_name(op.name + ".tmp")
    try:
        new_tmp.write_text(render(f, typ), encoding="utf-8")
        old_tmp.write_text(t, encoding="utf-8")
        os.replace(new_tmp, path)
        try:
            os.replace(old_tmp, op)
        except BaseException:
            path.unlink()
            raise
    finally:
        for tmp in (new_tmp, old_tmp):
            if tmp.exists():
                tmp.unlink()
    build_index.write(rd)
    print(f"{f['id']} supersedes {a.id}")
    print(f"  new card {path}")
    print(f"  old card {op} -> status=superseded, superseded_by={f['id']}")
    return 0


def main(argv=None) -> int:
    R.utf8_stdio()
    ap = argparse.ArgumentParser(description="Enroll cards in the decision registry")
    R.add_registry_arg(ap)
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True

    p_new = sub.add_parser("new", help="create a card")
    p_new.add_argument("type", choices=list(PREFIX))
    add_common(p_new)

    p_v = sub.add_parser("verify", help="re-verify: refresh `verified` and reset `review_by` "
                                        "from source_tier")
    p_v.add_argument("id")
    p_v.add_argument("--source-tier", help="update source_tier if verification changed it")
    p_v.add_argument("--note", default="")
    p_v.add_argument("--acquisition", help="upgrade after re-tracing, e.g. unrecorded -> held_copy")
    p_v.add_argument("--archive-ref")
    p_v.add_argument("--source-url")
    p_v.add_argument("--asked")
    p_v.add_argument("--reacquire")

    p_s = sub.add_parser("supersede", help="replace a card with a new one; links both ways")
    p_s.add_argument("id")
    add_common(p_s)

    a = ap.parse_args(argv)
    rd = R.resolve_or_exit(a.registry)
    schema = R.load_schema(rd)
    try:
        cards = R.load_cards(rd)
    except R.CardError as e:
        raise SystemExit(f"error: a card cannot be read, fix it first: {e}")
    by_id = {str(c.get("id")): c for c in cards}

    if a.cmd == "new":
        return cmd_new(a, rd, schema, cards)
    if a.cmd == "verify":
        return cmd_verify(a, rd, schema, by_id)
    return cmd_supersede(a, rd, schema, cards, by_id)


if __name__ == "__main__":
    sys.exit(main())
