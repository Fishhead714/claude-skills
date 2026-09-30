"""Registry location and card loading for decision-registry.

Two principles:
  1. Single source of truth. A card's frontmatter is the truth; INDEX.json is
     a derived artifact.
  2. If something cannot be found or read, raise. Never fall back to defaults
     or an empty list -- a silent fallback makes the caller believe it got the
     complete list of boundaries, and "no results" gets read as "no boundaries".
"""
from __future__ import annotations

import datetime
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

import miniyaml

#: Directory name searched for when walking up from the current directory.
REGISTRY_DIRNAME = "decision-registry"
#: Environment variable that points at a registry directory.
ENV_VAR = "DECISION_REGISTRY"

SUBDIRS = {"constraint": "constraints", "decision": "decisions", "stance": "stances"}
SCOPE_DIMS = ("regions", "projects", "activities")


def utf8_stdio() -> None:
    """Card titles may contain any script. Don't let a legacy Windows console
    code page turn a registry listing into a UnicodeEncodeError halfway through."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def add_registry_arg(parser) -> None:
    parser.add_argument(
        "--registry",
        help=f"path to the registry directory (overrides ${ENV_VAR} and the "
             f"walk-up search for a `{REGISTRY_DIRNAME}/` directory)")


class RegistryNotFound(FileNotFoundError):
    pass


def registry_dir(explicit: "str | os.PathLike | None" = None) -> Path:
    """Resolve the registry directory.

    Order: explicit --registry  >  $DECISION_REGISTRY  >  walk up from cwd looking
    for a directory named `decision-registry/` that contains schema.json.
    Not found -> RegistryNotFound. There is deliberately no fallback.
    """
    for label, val in (("--registry", explicit), (ENV_VAR, os.environ.get(ENV_VAR))):
        if val:
            p = Path(val).expanduser().resolve()
            if not p.is_dir():
                raise RegistryNotFound(f"{label} points to a directory that does not exist: {p}")
            if not (p / "schema.json").is_file():
                raise RegistryNotFound(f"{label} points to {p}, which has no schema.json "
                                       f"(not a registry; create one with init.py)")
            return p
    here = Path.cwd().resolve()
    for base in [here, *here.parents]:
        if base.name == REGISTRY_DIRNAME and (base / "schema.json").is_file():
            return base
        cand = base / REGISTRY_DIRNAME
        if (cand / "schema.json").is_file():
            return cand
    raise RegistryNotFound(
        f"No decision registry found. Pass --registry, set ${ENV_VAR}, or run from "
        f"inside a directory tree that contains `{REGISTRY_DIRNAME}/schema.json` "
        f"(create one with init.py). Refusing to continue with an empty list: "
        f"an empty answer would read as 'there are no boundaries'.")


def resolve_or_exit(explicit=None) -> Path:
    try:
        return registry_dir(explicit)
    except RegistryNotFound as e:
        raise SystemExit(f"error: {e}")


ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_iso_date(v):
    """Strict YYYY-MM-DD -> date, else None. Not date.fromisoformat alone: what it
    accepts differs between Python versions (3.11+ also takes `20260105`)."""
    if isinstance(v, datetime.date):
        return v if not isinstance(v, datetime.datetime) else v.date()
    s = str(v).strip() if v is not None else ""
    if not ISO_DATE.match(s):
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def load_schema(rd: Path) -> dict:
    p = rd / "schema.json"
    if not p.is_file():
        raise FileNotFoundError(f"registry has no schema.json: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


class CardError(ValueError):
    """A card itself is malformed. Carries the card name -- without it, a crash
    in audit cannot be traced back to a card."""

    def __init__(self, name: str, msg: str):
        self.card_name, self.msg = name, msg
        super().__init__(f"{name}: {msg}")


def _split_frontmatter(text: str, path: Path):
    """Split on *whole-line* `---`.

    Splitting on the substring "\\n---" has two traps: a markdown horizontal
    rule in the body silently truncates the body, and it also defeats the
    "unclosed frontmatter" check. So the delimiter is anchored to full lines,
    and a markdown heading inside the frontmatter range is treated as proof
    that the frontmatter was never closed.
    """
    text = text.lstrip("\ufeff")
    lines = text.replace("\r\n", "\n").split("\n")
    # Delimiters must start at column 0: an indented `---` is content (e.g. a
    # line inside a `|` block scalar), not the end of the frontmatter.
    if not lines or lines[0].rstrip() != "---":
        raise CardError(path.name, "missing YAML frontmatter (first line is not ---)")
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip() == "---"), None)
    if end is None:
        raise CardError(path.name, "frontmatter not closed (no second --- line)")
    block = lines[1:end]
    for ln in block:
        # `##`..`######` headings only: a single `#` at column 0 is a legal YAML
        # comment (the templates use them), so it cannot be treated as a heading.
        if re.match(r"^#{2,6}\s+\S", ln):
            raise CardError(path.name,
                            f"markdown heading `{ln.strip()[:30]}` inside the frontmatter "
                            f"range -- the frontmatter was most likely never closed and a "
                            f"body horizontal rule is acting as the closing delimiter. "
                            f"The YAML reader would swallow it silently, so it is refused")
    try:
        fm = miniyaml.loads("\n".join(block))
    except miniyaml.YamlError as e:
        raise CardError(path.name, f"frontmatter could not be parsed: {e}") from e
    return fm, "\n".join(lines[end + 1:])


def load_cards(rd: Path) -> list:
    """Return every card. `_templates/` and `_inbox/` are never read."""
    cards: list = []
    for sub in SUBDIRS.values():
        d = rd / sub
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            fm, body = _split_frontmatter(p.read_text(encoding="utf-8"), p)
            fm["_path"] = p.relative_to(rd).as_posix()
            fm["_file"] = p.name
            fm["_subdir"] = sub
            fm["_body"] = body
            cards.append(fm)
    return cards


def _as_list(v):
    """A scope dimension may be `all`, a single value, or a list."""
    if v is None:
        return "all"
    if isinstance(v, str):
        return "all" if v.strip().lower() == "all" else [v]
    if isinstance(v, list):
        return v
    return [v]


def scope_of(card: dict) -> dict:
    sc = card.get("scope")
    if sc is None:
        sc = {}
    if not isinstance(sc, dict):
        raise CardError(card.get("_file") or str(card.get("id")),
                        f"scope must be a mapping of {'/'.join(SCOPE_DIMS)}, "
                        f"got {type(sc).__name__}: {sc!r}")
    unknown = sorted(str(k) for k in sc if k not in SCOPE_DIMS)
    if unknown:
        # A typo'd dimension (`region:` for `regions:`) would otherwise be ignored,
        # and the missing real dimension defaults to `all` -- silently widening scope.
        raise CardError(card.get("_file") or str(card.get("id")),
                        f"unknown scope key(s) {unknown}; allowed: {list(SCOPE_DIMS)}")
    return {k: _as_list(sc.get(k)) for k in SCOPE_DIMS}


def _dim_match(want, have) -> bool:
    """have == 'all' matches everything; want None means 'do not filter'."""
    if have == "all" or want is None:
        return True
    return any(fnmatch.fnmatchcase(str(want), str(h)) for h in have)


def matches(card: dict, *, region=None, project=None, activity=None) -> bool:
    sc = scope_of(card)
    return (_dim_match(region, sc["regions"])
            and _dim_match(project, sc["projects"])
            and _dim_match(activity, sc["activities"]))


def dims_overlap(a: dict, b: dict) -> bool:
    """Do two cards' scopes intersect (all three dimensions must intersect)?"""
    sa, sb = scope_of(a), scope_of(b)
    for k in SCOPE_DIMS:
        x, y = sa[k], sb[k]
        if x == "all" or y == "all":
            continue
        if not any(fnmatch.fnmatchcase(str(i), str(j)) or fnmatch.fnmatchcase(str(j), str(i))
                   for i in x for j in y):
            return False
    return True


def json_safe(v):
    """Convert non-JSON-native values to strings (dates, in case a card was
    produced by a full YAML library). Without this, one bare date would make
    build_index crash while audit keeps asking you to rebuild the index."""
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [json_safe(x) for x in v]
    return v


def index_record(card: dict) -> dict:
    """One INDEX.json entry. Machine-checkable fields only; bodies stay out."""
    rec = {
        "id": card.get("id"),
        "type": card.get("type"),
        "domain": card.get("domain"),
        "title": card.get("title"),
        "force": card.get("force"),
        "status": card.get("status"),
        "enforcement": card.get("enforcement"),
        "scope": scope_of(card),
        "source_tier": card.get("source_tier"),
        "acquisition": card.get("acquisition"),
        "verified": str(card.get("verified") or ""),
        "review_by": str(card.get("review_by") or ""),
        "consequence": card.get("consequence"),
        "path": card["_path"],
    }
    for opt in ("confidence", "falsified_if", "hard_value", "supersedes", "superseded_by",
                "applicability", "source_url", "archive_ref", "asked", "reacquire"):
        if card.get(opt):
            rec[opt] = card[opt]
    return json_safe(rec)
