#!/usr/bin/env python3
"""fingerprint-scan: find numeric and structural fingerprints of private facts in a source tree.

Secret scanners look for credentials; denylists look for names. Neither sees a
private site area written as a plain number in a test, a template width rounded
to an integer in a comment, or a percentage computed from a private dimension.
This tool matches every numeric literal in a tree against a private *ledger* of
facts (with unit conversion, rounding and derived values), flags real-looking
coordinates, irregular "measured-looking" numbers in tests/examples, and build
artifacts that carry absolute user paths.

Python 3.9+, standard library only.

Exit codes: 0 = nothing at/above --fail-on, 1 = findings at/above --fail-on, 2 = usage error.
"""
from __future__ import annotations

import argparse
import bisect
import fnmatch
import functools
import json
import math
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

__version__ = "0.1.0"

SEVERITIES = ("low", "medium", "high")
SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}
DETECTORS = ("ledger", "derived", "coords", "irregular", "artifacts")
PRAGMA = "fingerprint-scan: ignore"
PRAGMA_RX = re.compile(r"fingerprint-scan: ignore(?!-file)(?:\s{0,3}\(([^()\n]{1,200})\))?")
FILE_PRAGMA = "fingerprint-scan: ignore-file"          # in the first 10 lines: silence heuristic detectors only
EXAMPLE_MARK = "fingerprint-scan: synthetic-example"   # a ledger/fence file that only holds invented values
MIN_SIG = 2                 # a rounded literal must keep at least this many significant digits
MAX_TEXT_BYTES = 5_000_000  # larger files are reported (low) and skipped
MAX_LINE_CHARS = 4_000      # longer lines (minified JSON, data dumps) are scanned in overlapping segments


# --------------------------------------------------------------------------- units
# canonical unit -> (dimension, a, b): base_value = value * a + b
UNITS: dict[str, tuple[str, float, float]] = {
    "mm": ("length", 1e-3, 0), "cm": ("length", 1e-2, 0), "m": ("length", 1.0, 0),
    "km": ("length", 1e3, 0), "in": ("length", 0.0254, 0), "ft": ("length", 0.3048, 0),
    "mi": ("length", 1609.344, 0),
    "mm2": ("area", 1e-6, 0), "cm2": ("area", 1e-4, 0), "m2": ("area", 1.0, 0), "ha": ("area", 1e4, 0),
    "km2": ("area", 1e6, 0), "acre": ("area", 4046.8564224, 0), "ft2": ("area", 0.09290304, 0),
    "g": ("mass", 1e-3, 0), "kg": ("mass", 1.0, 0), "t": ("mass", 1e3, 0),
    "w": ("power", 1.0, 0), "kw": ("power", 1e3, 0), "mw": ("power", 1e6, 0), "gw": ("power", 1e9, 0),
    "wh": ("energy", 1.0, 0), "kwh": ("energy", 1e3, 0), "mwh": ("energy", 1e6, 0), "gwh": ("energy", 1e9, 0),
    "m/s": ("speed", 1.0, 0), "km/h": ("speed", 1 / 3.6, 0), "mph": ("speed", 0.44704, 0),
    "kn": ("speed", 1852 / 3600, 0),
    "s": ("time", 1.0, 0), "min": ("time", 60.0, 0), "h": ("time", 3600.0, 0), "d": ("time", 86400.0, 0),
    "frac": ("ratio", 1.0, 0), "%": ("ratio", 0.01, 0), "permille": ("ratio", 0.001, 0),
    "deg": ("angle", 1.0, 0), "rad": ("angle", 180 / math.pi, 0),
    "c": ("temperature", 1.0, 0), "k": ("temperature", 1.0, -273.15), "f": ("temperature", 5 / 9, -160 / 9),
}

UNIT_ALIASES = {
    "millimeter": "mm", "millimetre": "mm", "centimeter": "cm", "centimetre": "cm", "meter": "m",
    "metre": "m", "meters": "m", "metres": "m", "kilometer": "km", "kilometre": "km", "inch": "in",
    "feet": "ft", "foot": "ft", "sqm": "m2", "sqkm": "km2", "hectare": "ha", "hectares": "ha",
    "acres": "acre", "sqft": "ft2", "tonne": "t", "tonnes": "t", "ton": "t", "kmh": "km/h", "kph": "km/h",
    "knot": "kn", "knots": "kn", "sec": "s", "second": "s", "seconds": "s", "hr": "h", "hour": "h",
    "hours": "h", "day": "d", "days": "d", "fraction": "frac", "ratio": "frac", "pct": "%",
    "percent": "%", "‰": "permille", "degc": "c", "°c": "c", "celsius": "c", "degf": "f", "°f": "f",
    "fahrenheit": "f", "kelvin": "k", "degree": "deg", "degrees": "deg", "°": "deg", "radian": "rad",
}

# words that, near a literal, show that it is expressed in that unit (context evidence)
UNIT_WORDS: dict[str, tuple[str, ...]] = {
    "mm": ("mm", "millimet"), "cm": ("cm", "centimet"), "m": ("m", "meter", "metre"),
    "km": ("km", "kilomet"), "in": ("inch",), "ft": ("ft", "feet", "foot"),
    "mm2": ("mm2", "mm²"), "cm2": ("cm2", "cm²"), "m2": ("m2", "m²", "sqm", "square met"),
    "ha": ("ha", "hectare"), "km2": ("km2", "km²", "sqkm", "sq km", "square kilomet"),
    "acre": ("acre",), "ft2": ("ft2", "sqft"),
    "kg": ("kg",), "t": ("tonne",), "w": ("watt",), "kw": ("kw",), "mw": ("mw",), "gw": ("gw",),
    "wh": ("wh",), "kwh": ("kwh",), "mwh": ("mwh",), "gwh": ("gwh",),
    "m/s": ("m/s",), "km/h": ("km/h", "kmh", "kph"), "mph": ("mph",), "kn": ("knot",),
    "min": ("min", "minute"), "h": ("hour", "hrs"), "s": ("sec",), "d": ("day",),
    "%": ("%", "percent", "pct"), "frac": ("fraction", "ratio", "share"), "permille": ("‰", "permille"),
    "deg": ("deg", "°"), "rad": ("rad",),
    "c": ("°c", "degc", "celsius", "deg c"), "f": ("°f", "degf", "fahrenheit"), "k": ("kelvin",),
}


def canon_unit(u: str) -> str:
    """Normalise a unit spelling. Unknown units are kept (lower-cased) as their own dimension."""
    s = u.strip().lower().replace("²", "2").replace("^2", "2").replace(" ", "")
    if s in ("", "count", "n", "pcs", "units", "unit", "x", "none", "-"):
        return "count"
    s = UNIT_ALIASES.get(s, s)
    if s.startswith("sq") and s[2:] in UNITS and UNITS[s[2:]][0] == "length":
        s = s[2:] + "2"
    return UNIT_ALIASES.get(s, s)


def convert_all(value: float, unit: str) -> list[tuple[str, float, float]]:
    """All representations of value (given in unit) in units of the same dimension.

    Returns (unit, converted_value, scale) where scale = d(converted)/d(value), used to scale precision.
    """
    if unit not in UNITS:
        return [(unit, value, 1.0)]
    dim, a, b = UNITS[unit]
    base = value * a + b
    out = []
    for u, (d2, a2, b2) in UNITS.items():
        if d2 == dim:
            out.append((u, (base - b2) / a2, a / a2))
    return out


# --------------------------------------------------------------------------- numeric literals
NUM_RX = re.compile(r"(?<![\w.])(-?)(\d{1,30}(?:\.\d{1,30})?|\.\d{1,30})(?:[eE]([+-]?\d{1,3}))?(?!\.?\d)")
GLUED_RX = re.compile(r"(?<=[A-Za-z_])(\d{1,30}(?:\.\d{1,30})?)(?!\.?\d)")
GROUPED_RX = re.compile(r"(?<![\w.,])(-?)(\d{1,3}(?:[,_]\d{3}){1,6})(\.\d{1,30})?(?!\d|[,_]\d|\.\d)")

COMMON_VALUES = {0.25, 0.75, 1.5, 2.5, 12.5, 24, 30, 45, 60, 90, 120, 180, 270, 360, 365, 1000, 3600, 86400, 8760}


@dataclass
class Literal:
    raw: str
    value: float
    sig: int
    half: float          # half-width of the rounding interval implied by how it is written
    line: int
    start: int
    end: int
    glued: bool = False  # part of an identifier/filename token (py3x, utf-8, x86_64, abc-123, site_area_437)

    @property
    def common(self) -> bool:
        return is_common(self.value, self.sig)


def sig_and_decimals(mant: str, exp: int = 0) -> tuple[int, int]:
    """Significant digits and effective decimal places (negative = trailing zeros of an integer)."""
    mant = mant.lstrip("-").replace(",", "").replace("_", "")
    ip, dot, frac = mant.partition(".")
    digits = (ip + frac).lstrip("0")
    if dot:
        sig = len(digits)
        dec = len(frac)
    else:
        stripped = digits.rstrip("0")
        sig = len(stripped)
        dec = -(len(digits) - len(stripped)) if digits else 0
    return sig, dec - exp


def glued_before(line: str, start: int) -> bool:
    """True if the literal at `start` continues an identifier via '-' or '_' (utf-8, ubuntu-22.04, abc-123)."""
    return start >= 2 and line[start - 1] in "-_" and line[start - 2].isalnum()


def is_common(value: float, sig: int) -> bool:
    v = abs(value)
    if sig <= 1:
        return True
    if v.is_integer():
        if v <= 16:
            return True
        iv = int(v)
        if iv >= 32 and iv & (iv - 1) == 0:
            return True
    return any(math.isclose(v, c, rel_tol=1e-12) for c in COMMON_VALUES)


def extract_literals(line: str, lineno: int) -> list[Literal]:
    out: list[Literal] = []
    for m in NUM_RX.finditer(line):
        sign, mant, exp = m.group(1), m.group(2), m.group(3)
        e = int(exp) if exp else 0
        try:
            val = float(sign + mant + (("e" + exp) if exp else ""))
        except (ValueError, OverflowError):
            continue
        if not math.isfinite(val):
            continue
        sig, dec = sig_and_decimals(mant, e)
        out.append(Literal(m.group(0), val, sig, 0.5 * 10.0 ** (-dec), lineno, m.start(), m.end(),
                           glued_before(line, m.start())))
    # numbers glued directly to a letter or underscore (py3x, sha256, x86_64, site_area_437): still extracted,
    # because an identifier can carry a real value, but flagged so that they can only produce LOW notes
    for m in GLUED_RX.finditer(line):
        if m.start() >= 2 and line[m.start() - 1] in "eE" and (line[m.start() - 2].isdigit() or line[m.start() - 2] == "."):
            continue   # exponent of 1e6 / 2.5e10, already read as part of the number
        mant = m.group(1)
        sig, dec = sig_and_decimals(mant)
        out.append(Literal(mant, float(mant), sig, 0.5 * 10.0 ** (-dec), lineno, m.start(), m.end(), True))
    for m in GROUPED_RX.finditer(line):
        sign, body, frac = m.group(1), m.group(2), m.group(3) or ""
        mant = body.replace(",", "").replace("_", "") + frac
        val = float(sign + mant)
        sig, dec = sig_and_decimals(mant)
        out.append(Literal(m.group(0), val, sig, 0.5 * 10.0 ** (-dec), lineno, m.start(), m.end()))
    return out


# --------------------------------------------------------------------------- ledger
@dataclass
class Fact:
    name: str
    raw: str
    value: float
    unit: str
    sig: int
    half: float
    weak: bool
    base: bool
    tol: float
    keywords: list[str]


@dataclass
class Sequence:
    name: str
    raws: list
    values: list
    halves: list
    min_run: int


@dataclass
class Derive:
    a: str
    op: str
    b: str


@dataclass
class Ledger:
    facts: dict[str, Fact] = field(default_factory=dict)
    derives: list[Derive] = field(default_factory=list)
    sequences: list[Sequence] = field(default_factory=list)
    path: Optional[Path] = None
    synthetic_example: bool = False


def _keywords(name: str, extra: Iterable[str]) -> list[str]:
    toks = [t for t in re.split(r"[_\-\s.]+", name.lower()) if len(t) >= 3]
    return sorted(set(toks) | {e.strip().lower() for e in extra if e.strip()})


def _make_fact(name: str, raw: str, unit: str, flags: Iterable[str], context: Iterable[str], tol: float) -> Fact:
    raw_clean = raw.replace(",", "").replace("_", "")
    try:
        value = float(raw_clean)
    except ValueError:
        raise SystemExit(f"ledger: value of '{name}' is not a number: {raw!r}")
    m = re.fullmatch(r"-?(\d*\.?\d*)(?:[eE]([+-]?\d+))?", raw_clean)
    mant, exp = (m.group(1), int(m.group(2) or 0)) if m else (raw_clean, 0)
    sig, _ = sig_and_decimals(mant, exp)
    flags = {f.lower() for f in flags}
    weak = "weak" in flags or ("strong" not in flags and sig <= 2)
    # Ledger values are treated as exact (half = 0): record the private value at full precision and the
    # scanner catches every rounding of it. Use tol= for values that are themselves approximate.
    return Fact(name, raw, value, canon_unit(unit), max(sig, 1), 0.0, weak,
                "base" in flags, tol, _keywords(name, context))


def _make_sequence(name: str, raws: list, min_run: int = 4) -> Sequence:
    vals, halves = [], []
    for r in raws:
        r = str(r).strip()
        try:
            vals.append(float(r))
        except ValueError:
            raise SystemExit(f"ledger: sequence '{name}' has a non-number: {r!r}")
        halves.append(0.0)   # exact, like facts
    if len(vals) < 3:
        raise SystemExit(f"ledger: sequence '{name}' needs at least 3 values")
    return Sequence(name, [str(r).strip() for r in raws], vals, halves, min(min_run, len(vals)))


def _parse_tol(s: str) -> float:
    s = s.strip()
    return float(s[:-1]) / 100 if s.endswith("%") else float(s)


def load_ledger(path: Path) -> Ledger:
    text = path.read_text(encoding="utf-8-sig")
    led = Ledger(path=path, synthetic_example=EXAMPLE_MARK in text)
    if text.lstrip().startswith("{"):
        data = json.loads(text)
        for f in data.get("facts", []):
            fa = _make_fact(f["name"], str(f["value"]), f.get("unit", ""), f.get("flags", []),
                            f.get("context", []), _parse_tol(str(f.get("tol", 0))))
            led.facts[fa.name] = fa
        for d in data.get("derive", []):
            led.derives.append(Derive(d["a"], d.get("op", "/"), d["b"]))
        for q in data.get("sequences", []):
            led.sequences.append(_make_sequence(q["name"], q["values"], int(q.get("min_run", 4))))
    else:
        for n, raw in enumerate(text.splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line.lower().startswith("derive "):
                m = re.fullmatch(r"derive\s+(\S+)\s*([/*])\s*(\S+)", line, re.I)
                if not m:
                    raise SystemExit(f"ledger line {n}: expected 'derive a / b' or 'derive a * b'")
                led.derives.append(Derive(m.group(1), m.group(2), m.group(3)))
                continue
            m = re.fullmatch(r"([A-Za-z][\w.-]*)\s*=\s*\[([^\]]{1,4000})\]\s*(?:min_run=(\d+))?", line)
            if m:
                led.sequences.append(_make_sequence(m.group(1), m.group(2).split(","), int(m.group(3) or 4)))
                continue
            m = re.fullmatch(r"([A-Za-z][\w.-]*)\s*=\s*(-?[\d.,_]+(?:[eE][+-]?\d+)?)\s*(.*)", line)
            if not m:
                raise SystemExit(f"ledger line {n}: expected 'name = value [unit] [flags]'")
            name, val, rest = m.groups()
            unit, flags, context, tol = "", [], [], 0.0
            for tok in rest.split():
                tl = tok.lower()
                if tl in ("weak", "strong", "base"):
                    flags.append(tl)
                elif tl.startswith("context="):
                    context += tok.split("=", 1)[1].split(",")
                elif tl.startswith("tol="):
                    tol = _parse_tol(tok.split("=", 1)[1])
                elif not unit:
                    unit = tok
                else:
                    raise SystemExit(f"ledger line {n}: unexpected token {tok!r}")
            fa = _make_fact(name, val, unit, flags, context, tol)
            led.facts[fa.name] = fa
    for d in led.derives:
        for nm in (d.a, d.b):
            if nm not in led.facts:
                raise SystemExit(f"ledger: derive refers to unknown fact '{nm}'")
    return led


@dataclass
class Candidate:
    value: float
    half: float
    sig: int
    how: str
    facts: tuple
    keywords: list


def ledger_candidates(led: Ledger) -> list[Candidate]:
    out = []
    for f in led.facts.values():
        for u, v, scale in convert_all(f.value, f.unit):
            how = f"{f.name} = {f.raw} {f.unit if f.unit != 'count' else ''}".rstrip()
            if u != f.unit:
                how += f" (as {u})"
            out.append(Candidate(v, f.half * abs(scale) + f.tol * abs(v), f.sig, how, (f.name, u), f.keywords))
    return out


def derived_candidates(led: Ledger) -> list[Candidate]:
    out = []
    for d in led.derives:
        a, b = led.facts[d.a], led.facts[d.b]
        pairs = [(a.value, b.value, "")]
        if a.unit in UNITS and b.unit in UNITS and UNITS[a.unit][2] == 0 and UNITS[b.unit][2] == 0:
            sa, sb = a.value * UNITS[a.unit][1], b.value * UNITS[b.unit][1]
            pairs.append((sa, sb, " in base units"))
        rel = (a.half / abs(a.value) if a.value else 0) + (b.half / abs(b.value) if b.value else 0)
        seen = set()
        for va, vb, note in pairs:
            if d.op == "/":
                if vb == 0:
                    continue
                forms = [(va / vb, "ratio"), (va / vb * 100, "percent")]
            else:
                forms = [(va * vb, "product")]
            for v, kind in forms:
                key = round(v, 12)
                if key in seen or v == 0:
                    continue
                seen.add(key)
                out.append(Candidate(v, abs(v) * rel, min(a.sig, b.sig),
                                     f"{kind} {d.a} {d.op} {d.b}{note}", (d.a, d.b),
                                     sorted(set(a.keywords) | set(b.keywords))))
    return out


# --------------------------------------------------------------------------- findings
@dataclass
class Finding:
    path: str
    line: int
    detector: str
    severity: str
    value: str
    detail: str
    excerpt: str = ""


def _down(sev: str) -> str:
    return SEVERITIES[max(SEV_RANK[sev] - 1, 0)]


IMPERIAL = {"in", "ft", "ft2", "acre", "mi", "mph", "kn"}
CONTEXT_CHARS = 160   # context is looked for within this many chars of the literal (and the previous line's tail)


@functools.lru_cache(maxsize=4096)
def _kw_rx(words: tuple) -> Optional[re.Pattern]:
    words = [w for w in words if w]
    if not words:
        return None
    return re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + ")")


@functools.lru_cache(maxsize=512)
def _unit_rx(unit: str) -> tuple:
    words = UNIT_WORDS.get(unit, ())
    adj = words + ((unit,) if len(unit) <= 2 else ())
    adj_rx = re.compile(r"\s?(?:" + "|".join(re.escape(w) for w in adj) + r")(?![a-z0-9])") if adj else None
    longw = [w for w in words if len(w) >= 2]
    any_rx = re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(w) for w in longw) + r")(?![a-z0-9])") if longw else None
    return adj_rx, any_rx


def has_unit_context(line: str, prev: str, lit: Literal, unit: Optional[str]) -> bool:
    return has_context(line, prev, lit, (), unit)


def has_context(line: str, prev: str, lit: Literal, keywords, unit: Optional[str]) -> bool:
    """Evidence near the literal: the unit written right after it, a unit word, or a keyword.
    Bounded to a window around the literal so that long lines stay linear."""
    near = line[max(0, lit.start - CONTEXT_CHARS):lit.end + CONTEXT_CHARS]
    low = (prev[-CONTEXT_CHARS:] + "\n" + near).lower()
    if unit:
        adj_rx, any_rx = _unit_rx(unit)
        if adj_rx and adj_rx.match(line[lit.end:lit.end + 16].lower()):
            return True
        if any_rx and any_rx.search(low):
            return True
    rx = _kw_rx(tuple(keywords))
    return bool(rx and rx.search(low))


def classify(lit: Literal, c: Candidate) -> Optional[str]:
    lv, cv = abs(lit.value), abs(c.value)
    diff = abs(lv - cv)
    if diff <= 1e-9 * max(cv, 1e-300):
        return "exact"
    if diff <= c.half + lit.half + 1e-12 * cv:
        return "precise" if lit.sig >= c.sig else "rounded"
    return None


class Scanner:
    def __init__(self, ledger: Optional[Ledger], fences: Optional[dict], disabled: Iterable[str] = (),
                 tree: Optional[Path] = None):
        self.ledger = ledger
        self.fences = fences or {"private": [], "private_utm": [], "synthetic": []}
        self.disabled = set(disabled)
        self.tree = tree
        self.lc = ledger_candidates(ledger) if ledger else []
        self.lc_sorted = sorted(self.lc, key=lambda c: abs(c.value))
        self.lc_keys = [abs(c.value) for c in self.lc_sorted]
        self.max_half = max((c.half + 1e-12 * abs(c.value) for c in self.lc), default=0.0)
        self.dc = derived_candidates(ledger) if ledger else []
        self.bases = [f for f in ledger.facts.values() if f.base] if ledger else []
        self.facts_by_name = ledger.facts if ledger else {}
        self.stats = {"text_files": 0, "binary_files": 0, "skipped_large": 0, "suppressed": 0, "long_lines": 0,
                      "ignored_files": []}

    def on(self, det: str) -> bool:
        return det not in self.disabled

    # ---- detector 1: ledger ------------------------------------------------
    def ledger_hits(self, path: str, lines: list[str], lits: list[list[Literal]]) -> list[Finding]:
        out = []
        for i, row in enumerate(lits):
            for lit in row:
                if lit.value == 0:
                    continue
                lv = abs(lit.value)
                win = lit.half + self.max_half + 1e-9 * lv
                lo = bisect.bisect_left(self.lc_keys, lv - win)
                hi = bisect.bisect_right(self.lc_keys, lv + win)
                best: Optional[tuple] = None
                for c in self.lc_sorted[lo:hi]:
                    kind = classify(lit, c)
                    if not kind:
                        continue
                    fact = self.facts_by_name[c.facts[0]]
                    ctx = has_context(lines[i], lines[i - 1] if i else "", lit, c.keywords, c.facts[1])
                    sev = None
                    if kind == "rounded" and lit.sig < MIN_SIG:
                        continue
                    if fact.weak:
                        if ctx:
                            sev = "medium" if kind != "rounded" else "low"
                    elif lit.common:
                        if ctx:
                            sev = "medium"
                    else:
                        sev = "high" if kind != "rounded" else "medium"
                        if not ctx and lit.sig <= 3:
                            sev = _down(sev)
                    # conversions into exotic units, or coarse roundings of a conversion, coincide easily:
                    # without the unit written next to the number they are only worth a LOW review note
                    converted = c.facts[1] != fact.unit
                    if sev and converted and (c.facts[1] in IMPERIAL or (kind == "rounded" and lit.sig <= 2)) \
                            and not has_unit_context(lines[i], lines[i - 1] if i else "", lit, c.facts[1]):
                        sev = "low"
                    if sev and is_known_constant(lit):
                        sev = "low"   # also a textbook constant (luma weights, g, pi ...): review, don't block
                    if sev and lit.glued:
                        sev = "low"   # number inside identifier: review (site_area_437 can be real), don't block
                    if sev and (best is None or SEV_RANK[sev] > SEV_RANK[best[0]]):
                        best = (sev, kind, c)
                if best:
                    sev, kind, c = best
                    note = " (number inside identifier)" if lit.glued else ""
                    out.append(Finding(path, i + 1, "ledger", sev, lit.raw, f"{kind} match: {c.how}{note}", lines[i]))
        return out

    def sequence_hits(self, path: str, lines: list[str], lits: list[list[Literal]]) -> list[Finding]:
        """A run of >= min_run consecutive literals equal (at their precision) to a slice of a ledger sequence."""
        out = []
        flat = [l for row in lits for l in row if not l.glued and (l.raw.lstrip("-")[:1].isdigit() or l.raw.startswith("."))]
        for q in self.ledger.sequences:
            k = q.min_run
            hit_at = set()
            for p in range(len(flat) - k + 1):
                for j in range(len(q.values) - k + 1):
                    if all(abs(abs(flat[p + t].value) - abs(q.values[j + t])) <= flat[p + t].half + q.halves[j + t]
                           + 1e-9 * abs(q.values[j + t]) and flat[p + t].sig >= 1 for t in range(k)):
                        ln = flat[p].line
                        if ln not in hit_at:
                            hit_at.add(ln)
                            vals = ", ".join(flat[p + t].raw for t in range(k))
                            out.append(Finding(path, ln, "ledger", "high", vals,
                                               f"run of {k} values matches sequence {q.name}[{j}:{j + k}]",
                                               lines[ln - 1]))
                        break
        return out

    # ---- detector 2: derived -----------------------------------------------
    def derived_hits(self, path: str, lines: list[str], lits: list[list[Literal]]) -> list[Finding]:
        out = []
        flat = [lit for row in lits for lit in row if lit.value != 0]
        for lit in flat:
            if lit.common or lit.sig < 3:   # 2-digit literals match some ratio far too often
                continue
            line = lines[lit.line - 1]
            prev = lines[lit.line - 2] if lit.line > 1 else ""
            for c in self.dc:
                if classify(lit, c):
                    ctx = has_context(line, prev, lit, tuple(c.keywords) + ("percent", "ratio", "fraction"), None) \
                        or "%" in line[lit.end:lit.end + 3]
                    sev = "high" if (lit.sig >= 3 and ctx) else "medium"
                    if lit.glued:
                        sev = "low"
                    out.append(Finding(path, lit.line, "derived", sev, lit.raw,
                                       f"= {c.how}" + (" (number inside identifier)" if lit.glued else ""), line))
                    break
        # base co-occurrence: x ~= y / base or 100*y / base with y another literal nearby
        if self.bases:
            ys = sorted((abs(l.value), l.line, l.raw) for l in flat if not l.common and l.sig >= MIN_SIG and not l.glued)
            keys = [y[0] for y in ys]
            for lit in flat:
                if lit.glued or lit.common or lit.sig < 3 or (lit.sig == 3 and lit.raw.rstrip("0")[-1:] in "05"):
                    continue   # 3-digit values ending in 0/5 (1.25, 2.50) are usually chosen, not derived
                x = abs(lit.value)
                hit = None
                for b in self.bases:
                    for mult, form in ((1.0, "ratio"), (0.01, "percent")):
                        target = x * mult * b.value
                        # only the literal's own rounding: the author divided by the exact private value
                        t = lit.half * mult * b.value + b.tol * target + 1e-9 * target
                        for k in range(bisect.bisect_left(keys, target - t), bisect.bisect_right(keys, target + t)):
                            yv, yline, yraw = ys[k]
                            if abs(yline - lit.line) <= 50 and not math.isclose(yv, x) \
                                    and not math.isclose(yv, abs(b.value)):
                                hit = (b, form, yraw, yline)
                                break
                        if hit:
                            break
                    if hit:
                        break
                if hit:
                    b, form, yraw, yline = hit
                    out.append(Finding(path, lit.line, "derived", "medium", lit.raw,
                                       f"{form} of {yraw} (line {yline}) relative to base {b.name}",
                                       lines[lit.line - 1]))
        return out

    # ---- detector 3: coordinates -------------------------------------------
    LATLON_RX = re.compile(r"(?<![\w.])(-?\d{1,3}\.\d{3,15})(?:\s{0,3}[,;]\s{0,3}|\s{1,3})(-?\d{1,3}\.\d{3,15})(?![\d.])")
    HEMI_RX = re.compile(r"(?<![\w.])(\d{1,2}\.\d{3,15})\s?°?\s?([NSns])[\s,;]{1,4}(\d{1,3}\.\d{3,15})\s?°?\s?([EWew])(?![a-z])")
    KEY_LAT = re.compile(r"(?<![a-z])(?:lat|latitude|lat_deg)\w{0,20}[\"']?\s{0,3}[:=]\s{0,3}[\"']?(-?\d{1,2}\.\d{1,15})", re.I)
    KEY_LON = re.compile(r"(?<![a-z])(?:lon|lng|long|longitude|lon_deg)\w{0,20}[\"']?\s{0,3}[:=]\s{0,3}[\"']?(-?\d{1,3}\.\d{1,15})", re.I)
    UTM_RX = re.compile(r"(?<![\w.])(\d{6}(?:\.\d{1,6})?)(?:\s{0,3}[,;]\s{0,3}|\s{1,3})(\d{6,7}(?:\.\d{1,6})?)(?![\w.])")
    KEY_E = re.compile(r"(?<![a-z])(?:easting|utm_?e|utm_?x|east)\w{0,20}[\"']?\s{0,3}[:=]\s{0,3}[\"']?(\d{6}(?:\.\d{1,6})?)(?![\d.])", re.I)
    KEY_N = re.compile(r"(?<![a-z])(?:northing|utm_?n|utm_?y|north)\w{0,20}[\"']?\s{0,3}[:=]\s{0,3}[\"']?(\d{6,7}(?:\.\d{1,6})?)(?![\d.])", re.I)

    def _geo_verdict(self, lat: float, lon: float, dec: int, weak: bool = False) -> Optional[tuple[str, str]]:
        """weak=True: the pair sits in a long number list, so without a fence hit it is only a LOW note.
        A pair inside a private fence is HIGH whatever surrounds it."""
        name = zone_hit(lat, lon, self.fences.get("private", []))
        if name:
            return "high", f"inside private fence '{name}'"
        if zone_hit(lat, lon, self.fences.get("synthetic", [])):
            return None
        if abs(lat) < 1 and abs(lon) < 1:
            return None
        if dec >= 4 and not weak:
            return "medium", "high-precision coordinate outside any declared synthetic zone"
        return "low", "coordinate-like pair outside any declared synthetic zone" + (" (in a number list)" if weak else "")

    def coord_hits(self, path: str, lines: list[str]) -> list[Finding]:
        out: list[Finding] = []
        seen_lines: set = set()

        def add(i, sev, raw, detail):
            out.append(Finding(path, i + 1, "coords", sev, raw, detail, lines[i]))
            seen_lines.add(i)

        for i, line in enumerate(lines):
            for m in self.HEMI_RX.finditer(line):
                lat = float(m.group(1)) * (-1 if m.group(2).lower() == "s" else 1)
                lon = float(m.group(3)) * (-1 if m.group(4).lower() == "w" else 1)
                dec = min(len(m.group(1).split(".")[1]), len(m.group(3).split(".")[1]))
                v = self._geo_verdict(lat, lon, dec)
                if v:
                    add(i, v[0], m.group(0), "lat/lon " + v[1])
            for m in self.LATLON_RX.finditer(line):
                if glued_before(line, m.start()):
                    continue   # ubuntu-22.04 style identifier, not a coordinate
                a, b = float(m.group(1)), float(m.group(2))
                dec = min(len(m.group(1).split(".")[1]), len(m.group(2).split(".")[1]))
                weak = in_number_run(line, m.start(), m.end())
                known = raw_is_constant(m.group(1)) or raw_is_constant(m.group(2))
                verdicts = []
                if abs(a) <= 90 and abs(b) <= 180:
                    verdicts.append(self._geo_verdict(a, b, dec, weak))
                if abs(b) <= 90 and abs(a) <= 180:
                    verdicts.append(self._geo_verdict(b, a, dec, weak))
                if known:   # a textbook constant is not a coordinate, unless it falls inside a private fence
                    verdicts = [v for v in verdicts if v and v[0] == "high"] or [None]
                if not verdicts or any(v is None for v in verdicts):
                    continue  # impossible as coordinates, or inside a synthetic zone in some order
                v = max(verdicts, key=lambda x: SEV_RANK[x[0]])
                add(i, v[0], m.group(0), "lat/lon pair " + v[1])
            for m in self.UTM_RX.finditer(line):
                if glued_before(line, m.start()):
                    continue
                e, n = float(m.group(1)), float(m.group(2))
                v = self._utm_verdict(e, n, weak=in_number_run(line, m.start(), m.end())
                                      or raw_is_constant(m.group(1)) or raw_is_constant(m.group(2)))
                if v:
                    add(i, v[0], m.group(0), "easting/northing " + v[1])
        # keyed values on nearby lines (lat = ..., lon = ...)
        out += self._keyed_pairs(path, lines, self.KEY_LAT, self.KEY_LON, seen_lines, geo=True)
        out += self._keyed_pairs(path, lines, self.KEY_E, self.KEY_N, seen_lines, geo=False)
        return out

    def _utm_verdict(self, e: float, n: float, weak: bool = False) -> Optional[tuple[str, str]]:
        for z in self.fences.get("private_utm", []):
            if z["easting"][0] <= e <= z["easting"][1] and z["northing"][0] <= n <= z["northing"][1]:
                return "high", f"inside private UTM fence '{z['name']}'"
        # outside private fences: only a plausible UTM easting (the valid band is about 166000-834000 m)
        if not (UTM_E_MIN <= e <= UTM_E_MAX and 0 <= n <= 10000000) or weak:
            return None
        for z in self.fences.get("synthetic_utm", []):
            if z["easting"][0] <= e <= z["easting"][1] and z["northing"][0] <= n <= z["northing"][1]:
                return None
        if is_patterned(str(int(e))) and is_patterned(str(int(n))):
            return None
        if e % 100 or n % 100:
            return "medium", "irregular UTM-like pair (looks surveyed, not chosen)"
        return "low", "round UTM-like pair"

    def _keyed_pairs(self, path, lines, rx_a, rx_b, seen_lines, geo: bool) -> list[Finding]:
        out = []
        As = [(i, m) for i, l in enumerate(lines) for m in rx_a.finditer(l)]
        Bs = [(i, m) for i, l in enumerate(lines) for m in rx_b.finditer(l)]
        used_b = set()
        for i, ma in As:
            best = None
            for j, mb in Bs:
                if abs(i - j) <= 5 and (j, mb.start()) not in used_b and (best is None or abs(i - j) < abs(i - best[0])):
                    best = (j, mb)
            a_raw = ma.group(1)
            if best is None:
                if not geo and i not in seen_lines:
                    v = self._single_utm(float(a_raw))
                    if v:
                        out.append(Finding(path, i + 1, "coords", v, a_raw, "keyed easting value", lines[i]))
                continue
            j, mb = best
            used_b.add((j, mb.start()))
            if i in seen_lines and j in seen_lines:
                continue
            b_raw = mb.group(1)
            if geo:
                dec = min(len(a_raw.partition(".")[2]), len(b_raw.partition(".")[2]))
                v = self._geo_verdict(float(a_raw), float(b_raw), dec)
                detail = "keyed lat/lon " + (v[1] if v else "")
            else:
                v = self._utm_verdict(float(a_raw), float(b_raw))
                detail = "keyed easting/northing " + (v[1] if v else "")
            if v:
                out.append(Finding(path, i + 1, "coords", v[0], f"{a_raw}, {b_raw}", detail, lines[i]))
        if not geo:
            paired = {j for (j, _) in used_b}
            for j, mb in Bs:
                if (j, mb.start()) not in used_b and j not in seen_lines and j not in paired:
                    v = self._single_utm(float(mb.group(1)), northing=True)
                    if v:
                        out.append(Finding(path, j + 1, "coords", v, mb.group(1), "keyed northing value", lines[j]))
        return out

    @staticmethod
    def _single_utm(v: float, northing: bool = False) -> Optional[str]:
        if is_patterned(str(int(v))) or (not northing and not UTM_E_MIN <= v <= UTM_E_MAX):
            return None
        return "medium" if v % 100 else "low"

    # ---- detector 4: irregular literals in tests / examples ------------------
    def irregular_hits(self, path: str, lines: list[str], lits: list[list[Literal]]) -> list[Finding]:
        if not is_test_like(path):
            return []
        out = []
        for row in lits:
            for lit in row:
                if not lit.glued and looks_measured(lit):
                    out.append(Finding(path, lit.line, "irregular", "low", lit.raw,
                                       "non-round literal in test/example; confirm it is synthetic",
                                       lines[lit.line - 1]))
        return out

    # ---- per-file driver -----------------------------------------------------
    def scan_text(self, path: str, text: str, heuristics_off: bool = False) -> list[Finding]:
        """heuristics_off: the file carries the ignore-file pragma. It silences only the heuristic detectors
        (unfenced coordinates, UTM without a fence, irregular); private-fact matches always report."""
        orig = text.splitlines()
        lines, line_of = [], []          # segments and the original line number of each
        for k, l in enumerate(orig):
            if len(l) > MAX_LINE_CHARS:
                self.stats["long_lines"] += 1
                for seg in split_long_line(l):
                    lines.append(seg)
                    line_of.append(k + 1)
            else:
                lines.append(l)
                line_of.append(k + 1)
        out = self._scan_lines(path, lines)
        pragmas = {}
        for k, l in enumerate(orig):
            ms = list(PRAGMA_RX.finditer(l))
            if ms:
                pragmas[k + 1] = (ms[-1].group(1) or "").strip()   # the last pragma on the line counts
        kept = []
        for f in out:
            if 0 < f.line <= len(lines):
                f.line = line_of[f.line - 1]
            protected = is_protected(f)
            if heuristics_off and not protected and f.detector in ("coords", "irregular"):
                self.stats["suppressed"] += 1
                continue
            if f.line in pragmas:
                reason = pragmas[f.line]
                if not protected:
                    self.stats["suppressed"] += 1
                    continue
                # A private-fact match is never removed: with a reason it is downgraded to a visible LOW entry,
                # without one the pragma is ignored. The author of a pragma is the party the scan protects against.
                if reason:
                    self.stats["suppressed"] += 1
                    f.detail = f"SUPPRESSED ({reason}); was {f.severity.upper()}: {f.detail}"
                    f.severity = "low"
                else:
                    f.detail += " [pragma ignored: a reason in parentheses is required for this kind of match]"
            kept.append(f)
        return dedupe(kept)

    def _scan_lines(self, path: str, lines: list[str]) -> list[Finding]:
        lits = [extract_literals(l, i + 1) for i, l in enumerate(lines)]
        out: list[Finding] = []
        if self.on("ledger") and self.lc:
            out += self.ledger_hits(path, lines, lits)
        if self.on("ledger") and self.ledger and self.ledger.sequences:
            out += self.sequence_hits(path, lines, lits)
        if self.on("derived") and (self.dc or self.bases):
            out += self.derived_hits(path, lines, lits)
        if self.on("coords"):
            out += self.coord_hits(path, lines)
        if self.on("irregular"):
            out += self.irregular_hits(path, lines, lits)
        if self.on("artifacts"):
            for i, l in enumerate(lines):
                for m in ABS_PATH_TXT.finditer(l):
                    if not _placeholder(m.group(0)):
                        out.append(Finding(path, i + 1, "artifacts", "high", mask_path(m.group(0)),
                                           "absolute user path in text", l))
        return out


# --------------------------------------------------------------------------- helpers
UTM_E_MIN, UTM_E_MAX = 166000, 834000
_NUM_BEFORE = re.compile(r"-?\d{1,20}(?:\.\d{1,20})?(?:[eE][+-]?\d{1,3})?\s{0,3}[,;]\s{0,3}$")
_NUM_AFTER = re.compile(r"^\s{0,3}[,;]\s{0,3}-?\d{1,20}(?:\.\d{1,20})?(?:[eE][+-]?\d{1,3})?")


def in_number_run(line: str, start: int, end: int, min_run: int = 4) -> bool:
    """True when the matched pair is part of a comma/semicolon-separated run of >= min_run numbers
    (a constants table or data row, not a coordinate pair)."""
    extra, s, e = 0, start, end
    while extra < min_run - 2:
        m = _NUM_BEFORE.search(line[max(0, s - 60):s])
        if not m:
            break
        s -= len(m.group(0))
        extra += 1
    while extra < min_run - 2:
        m = _NUM_AFTER.match(line[e:e + 60])
        if not m:
            break
        e += len(m.group(0))
        extra += 1
    return extra >= min_run - 2


def raw_is_constant(raw: str) -> bool:
    lits = extract_literals(raw.strip(), 1)
    return bool(lits) and is_known_constant(lits[0])


_SEP = re.compile(r"[\s,;\]\[{}()]")


def split_long_line(line: str, size: int = MAX_LINE_CHARS, overlap: int = 200) -> list[str]:
    """Split at separators into segments of about `size` chars; each segment re-reads the last ~`overlap`
    chars of the previous one (snapped to a separator) so pairs straddling a cut are still seen whole."""
    segs, start, n = [], 0, len(line)
    while start < n:
        end = min(start + size, n)
        if end < n:
            cut = max(line.rfind(c, start + size // 2, end) for c in " ,;]}")
            end = cut + 1 if cut > start else end
        back = max(start - overlap, 0)
        if back > 0:
            m = _SEP.search(line, back, start + 1)
            back = m.end() if m else start
        segs.append(line[back:end])
        start = end
    return segs


def zone_hit(lat: float, lon: float, zones: list) -> Optional[str]:
    for z in zones:
        if "bbox" in z:
            x0, y0, x1, y1 = z["bbox"]
            if x0 <= lon <= x1 and y0 <= lat <= y1:
                return z.get("name", "unnamed")
        for ring in z.get("polygons", []):
            if point_in_ring(lon, lat, ring):
                return z.get("name", "unnamed")
    return None


def point_in_ring(x: float, y: float, ring: list) -> bool:
    inside = False
    n = len(ring)
    for k in range(n):
        x1, y1 = ring[k][0], ring[k][1]
        x2, y2 = ring[(k + 1) % n][0], ring[(k + 1) % n][1]
        if (y1 > y) != (y2 > y):
            xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xin:
                inside = not inside
    return inside


def load_fences(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    out = {"private": [], "private_utm": [], "synthetic": [], "synthetic_utm": []}
    if data.get("type") == "FeatureCollection":
        for feat in data.get("features", []):
            props = feat.get("properties") or {}
            kind = props.get("kind", "private")
            if kind not in ("private", "synthetic"):
                raise SystemExit(f"fences: kind must be 'private' or 'synthetic', got {kind!r}")
            name = props.get("name", "unnamed")
            if "utm" in props:
                out[kind + "_utm"].append({"name": name, **props["utm"]})
            geom = feat.get("geometry")
            if not geom:
                continue
            polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]] \
                if geom["type"] == "Polygon" else None
            if polys is None:
                raise SystemExit(f"fences: unsupported geometry {geom['type']} (use Polygon/MultiPolygon)")
            out[kind].append({"name": name, "polygons": [p[0] for p in polys]})
        validate_fences(out)
        return out
    for kind in out:
        for z in data.get(kind, []):
            z = dict(z)
            if "polygon" in z:
                z["polygons"] = [z.pop("polygon")]
            out[kind].append(z)
    validate_fences(out)
    return out


def validate_fences(f: dict) -> None:
    """A malformed zone would silently never match; refuse it instead."""
    for kind in ("private", "synthetic"):
        for z in f[kind]:
            name = z.get("name", "unnamed")
            if "bbox" not in z and not z.get("polygons"):
                raise SystemExit(f"fences: {kind} zone '{name}' has neither bbox nor polygon")
            if "bbox" in z:
                bb = z["bbox"]
                if len(bb) != 4 or bb[0] > bb[2] or bb[1] > bb[3]:
                    raise SystemExit(f"fences: {kind} zone '{name}' bbox must be [min_lon, min_lat, max_lon, max_lat]")
            for ring in z.get("polygons", []):
                if len(ring) < 3:
                    raise SystemExit(f"fences: {kind} zone '{name}' polygon needs at least 3 points")
    for kind in ("private_utm", "synthetic_utm"):
        for z in f[kind]:
            name = z.get("name", "unnamed")
            for axis in ("easting", "northing"):
                r = z.get(axis)
                if not r or len(r) != 2 or r[0] > r[1]:
                    raise SystemExit(f"fences: {kind} zone '{name}' needs {axis} as [min, max]")


def is_patterned(d: str) -> bool:
    """Digit strings that look chosen by a human: runs, repeats, single digit followed by zeros."""
    d = d.lstrip("-").replace(".", "").lstrip("0").rstrip("0")
    if len(d) <= 2:
        return True
    if len(set(d)) <= 2:
        return True
    steps = {(int(d[k + 1]) - int(d[k])) % 10 for k in range(len(d) - 1)}
    if len(steps) == 1:
        return True
    for p in range(1, len(d) // 2 + 1):
        if len(d) % p == 0 and d[:p] * (len(d) // p) == d:
            return True
    return False


KNOWN_CONSTANTS = (math.pi, math.e, math.sqrt(2), math.sqrt(3), math.sqrt(0.5), math.log(2), math.log(10),
                   180 / math.pi, math.pi / 180, 0.3048, 25.4, 1.609344, 9.80665, 9.81, 6371.0, 6371000.0,
                   6378137.0, 6378.137, 273.15, 101325.0, 1.225, 4046.8564224, 0.0174533, 57.2958,
                   299792458.0, 6.02214076e23, 1.380649e-23, 8.314462618, 0.08314, 1.4142, 1.7321,
                   2.2046226, 0.45359237, 3.28084, 0.621371, 1.852, 0.514444, 3.6, 1.8, 0.2126, 0.7152, 0.0722,
                   0.299, 0.587, 0.114, 111320.0, 111319.49, 111000.0, 0.9996, 1.4826, 0.6745, 1.96, 2.576, 1.645)


def is_known_constant(lit: Literal) -> bool:
    v = abs(lit.value)
    return any(math.isclose(v, c, rel_tol=5 * 10.0 ** (-max(lit.sig, 1))) for c in KNOWN_CONSTANTS) \
        if lit.sig >= 3 else False


def is_epsg(v: int) -> bool:
    """Common EPSG codes (WGS84, web mercator, ETRS89, UTM north/south zones) are identifiers, not data."""
    return v in (4326, 3857, 4258, 4269, 900913, 3395) or 32601 <= v <= 32660 or 32701 <= v <= 32760


def is_yyyymmdd(v: int) -> bool:
    y, md = divmod(v, 10000)
    m, d = divmod(md, 100)
    return 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31


def looks_measured(lit: Literal) -> bool:
    mant = lit.raw.lstrip("-").split("e")[0].split("E")[0].replace(",", "").replace("_", "")
    digits = mant.replace(".", "").lstrip("0").rstrip("0")
    if len(digits) < 4 or len(set(digits)) < 3:
        return False
    v = abs(lit.value)
    if v.is_integer() and (1900 <= v <= 2100 or v % 100 == 0 or is_epsg(int(v)) or is_yyyymmdd(int(v))):
        return False
    if is_patterned(digits) or is_common(v, lit.sig):
        return False
    for c in KNOWN_CONSTANTS:
        if math.isclose(v, c, rel_tol=5 * 10.0 ** (-len(digits))):
            return False
    return True


TEST_DIRS = {"test", "tests", "testing", "testdata", "test_data", "example", "examples", "fixture",
             "fixtures", "demo", "demos", "sample", "samples", "spec", "specs", "__tests__"}
TEST_FILES = ("test_*", "*_test.*", "*_tests.*", "*.test.*", "*_spec.*", "*.spec.*", "conftest.py",
              "example*", "sample*", "demo*", "fixture*")


def is_test_like(rel: str) -> bool:
    parts = Path(rel).parts
    if any(p.lower() in TEST_DIRS for p in parts[:-1]):
        return True
    return any(fnmatch.fnmatch(parts[-1].lower(), pat) for pat in TEST_FILES)


ABS_PATH_TXT = re.compile(r"(?<![\w.])(?:/home/[A-Za-z0-9_][\w.-]{0,63}|/Users/[A-Za-z0-9_][\w.-]{0,63}"
                          r"|[A-Za-z]:\\{1,2}Users\\{1,2}[A-Za-z0-9_][\w.-]{0,63})")
ABS_PATH_BIN = re.compile(rb"(?:/home/[A-Za-z0-9_][\w.-]{0,63}|/Users/[A-Za-z0-9_][\w.-]{0,63}"
                          rb"|[A-Za-z]:\\{1,2}Users\\{1,2}[A-Za-z0-9_][\w.-]{0,63})")
# compiled Python stores the absolute source path (co_filename) of the machine that built it
# No lookbehind: in marshal output the string follows a length prefix (1 or 4 bytes) that is often itself a
# word character, so the start is validated by find_build_path() instead.
ABS_SRC_PATH_BIN = re.compile(rb"(?:/(?:[\w.-]{1,64}/){1,24}[\w.-]{1,64}\.pyw?"
                              rb"|[A-Za-z]:\\(?:[\w .-]{1,64}\\){1,24}[\w.-]{1,64}\.pyw?)(?![\w])")
_PATH_BYTES = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-/\\: ")


def find_build_path(b: bytes) -> Optional[str]:
    """First absolute source path stored in compiled bytecode (co_filename), or None.
    A match counts when it starts the string: either the preceding byte is not a path character, or the
    1-byte / 4-byte marshal length prefix before it equals the length of the matched path."""
    for m in ABS_SRC_PATH_BIN.finditer(b):
        i, n = m.start(), len(m.group(0))
        if i == 0 or b[i - 1] not in _PATH_BYTES or b[i - 1] == n \
                or (i >= 4 and int.from_bytes(b[i - 4:i], "little") == n):
            return m.group(0).decode("latin-1")
    return None
PLACEHOLDER_USERS = {"user", "username", "you", "your", "yourname", "your-name", "your_name", "me", "name",
                     "example", "someone", "runner", "public", "default", "shared", "all", "foo", "alice-example"}


def _placeholder(p: str) -> bool:
    user = re.split(r"[/\\]+", p.rstrip("/\\"))[-1].lower()
    return user in PLACEHOLDER_USERS


def mask_path(p: str) -> str:
    parts = re.split(r"([/\\]+)", p)
    user = parts[-1]
    parts[-1] = (user[:1] + "***") if user else user
    return "".join(parts)


ARTIFACT_DIRS = {"__pycache__": "medium", ".ipynb_checkpoints": "medium", ".pytest_cache": "medium",
                 ".mypy_cache": "low", ".ruff_cache": "low", ".tox": "low", ".nox": "low", ".venv": "medium",
                 "venv": "medium", "node_modules": "low", ".idea": "low", ".vscode": "low"}
ARTIFACT_FILES = {"*.pyc": "medium", "*.pyo": "medium", ".DS_Store": "medium", "Thumbs.db": "medium",
                  "desktop.ini": "low", "*.swp": "medium", "*.swo": "medium", "*~": "low", ".coverage": "medium",
                  "*.orig": "low", "*.rej": "low", "*.log": "low", "*.egg-info": "low", "npm-debug.log*": "low",
                  "*.sqlite-journal": "low"}


# --------------------------------------------------------------------------- tree walk
def iter_files(root: Path, excludes: list[str]):
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if d != ".git")
        for fn in sorted(fns):
            p = Path(dp) / fn
            rel = p.relative_to(root).as_posix()
            if any(fnmatch.fnmatch(rel, e) for e in excludes):
                continue
            yield p, rel


def decode(b: bytes) -> Optional[str]:
    if b.startswith(b"\xff\xfe") or b.startswith(b"\xfe\xff"):
        try:
            return b.decode("utf-16")
        except UnicodeDecodeError:
            return None
    if b"\x00" in b[:8192]:
        return None
    return b.decode("utf-8", errors="replace").lstrip("﻿")


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def scan_tree(root: Path, ledger: Optional[Ledger], fences: Optional[dict], disabled: Iterable[str] = (),
              excludes: Optional[list] = None, fences_path: Optional[Path] = None) -> tuple[list[Finding], dict]:
    sc = Scanner(ledger, fences, disabled, root)
    findings: list[Finding] = []
    excludes = excludes or []
    # The ledger and fence files in use are never scanned against themselves. Inside the tree they are HIGH,
    # unless they carry the synthetic-example marker (e.g. this package's own examples/).
    own_inputs = set()
    if ledger and ledger.path and _inside(ledger.path, root):
        own_inputs.add(ledger.path.resolve())
        if sc.on("ledger") and not ledger.synthetic_example:
            findings.append(Finding(ledger.path.resolve().relative_to(root.resolve()).as_posix(), 0, "ledger", "high",
                                    "", "the private ledger itself is inside the scanned tree"))
    if fences_path and _inside(fences_path, root):
        own_inputs.add(fences_path.resolve())
        if sc.on("coords") and EXAMPLE_MARK not in fences_path.read_text(encoding="utf-8-sig"):
            findings.append(Finding(fences_path.resolve().relative_to(root.resolve()).as_posix(), 0, "coords", "high",
                                    "", "the private fence file itself is inside the scanned tree"))
    flagged_dirs = set()
    for p, rel in iter_files(root, excludes):
        parts = Path(rel).parts
        if sc.on("artifacts"):
            for k, part in enumerate(parts[:-1]):
                sev = ARTIFACT_DIRS.get(part) or (ARTIFACT_DIRS["__pycache__"] if part.endswith(".egg-info") else None)
                d = "/".join(parts[:k + 1])
                if sev and d not in flagged_dirs:
                    flagged_dirs.add(d)
                    findings.append(Finding(d + "/", 0, "artifacts", sev, "", "build/editor artifact directory"))
            for pat, sev in ARTIFACT_FILES.items():
                if fnmatch.fnmatch(parts[-1], pat):
                    findings.append(Finding(rel, 0, "artifacts", sev, "", f"build/editor artifact ({pat})"))
                    break
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size > MAX_TEXT_BYTES:
            sc.stats["skipped_large"] += 1
            findings.append(Finding(rel, 0, "artifacts", "low", "", f"not scanned: {size} bytes > {MAX_TEXT_BYTES}"))
            continue
        try:
            b = p.read_bytes()
        except OSError as e:
            findings.append(Finding(rel, 0, "artifacts", "low", "", f"unreadable: {e}"))
            continue
        text = decode(b)
        if text is None:
            sc.stats["binary_files"] += 1
            if sc.on("artifacts"):
                seen = set()
                for m in ABS_PATH_BIN.finditer(b):
                    s = m.group(0).decode("latin-1")
                    if not _placeholder(s) and s not in seen:
                        seen.add(s)
                        findings.append(Finding(rel, 0, "artifacts", "high", mask_path(s),
                                                "absolute user path embedded in binary file"))
                if not seen and rel.endswith((".pyc", ".pyo")):
                    s = find_build_path(b)
                    if s:
                        top = re.split(r"[/\\]+", s.strip("/\\"))[0]
                        findings.append(Finding(rel, 0, "artifacts", "high", f"{s[:1] if s[0] in '/' else ''}{top}/...",
                                                "absolute build path (co_filename) embedded in compiled file"))
            continue
        sc.stats["text_files"] += 1
        if rel.endswith(".ipynb") and sc.on("artifacts"):
            findings += notebook_findings(rel, text)
        if p.resolve() in own_inputs:
            sc.stats["ignored_files"].append(rel + " (ledger/fence input)")
            continue
        heur_off = FILE_PRAGMA in "\n".join(text.splitlines()[:10])
        if heur_off:
            sc.stats["ignored_files"].append(rel + " (ignore-file pragma: heuristics only)")
        findings += sc.scan_text(rel, text, heuristics_off=heur_off)
    findings = dedupe(findings)
    findings.sort(key=lambda f: (f.path, f.line, -SEV_RANK[f.severity], f.detector))
    return findings, sc.stats


def notebook_findings(rel: str, text: str) -> list[Finding]:
    try:
        nb = json.loads(text)
    except ValueError:
        return []
    n_out = sum(1 for c in nb.get("cells", []) if c.get("outputs") or c.get("execution_count") is not None)
    if n_out:
        return [Finding(rel, 0, "artifacts", "medium", "", f"notebook has {n_out} executed cell(s) with "
                        "outputs/execution counts; clear them before publishing")]
    return []


def is_protected(f: Finding) -> bool:
    """Findings a pragma may not remove: private facts (ledger, derived, coordinates inside a private fence)
    and artifacts (absolute user paths)."""
    return f.detector in ("ledger", "derived", "artifacts") or (f.detector == "coords" and "inside private" in f.detail)


def dedupe(fs: list[Finding]) -> list[Finding]:
    seen, out = set(), []
    for f in fs:
        key = (f.path, f.line, f.detector, f.value, f.detail)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


# --------------------------------------------------------------------------- output
def render_md(fs: list[Finding], stats: dict, root: Path, notes: list[str]) -> str:
    counts = {s: sum(1 for f in fs if f.severity == s) for s in SEVERITIES}
    out = ["# fingerprint-scan report", "",
           f"- tree: `{root}`",
           f"- text files scanned: {stats['text_files']}, binary files: {stats['binary_files']}, "
           f"skipped (too large): {stats['skipped_large']}, suppressed by pragma: {stats['suppressed']}",
           f"- files with pragmas or skipped as scan inputs ({len(stats['ignored_files'])}): "
           + (", ".join(f"`{x}`" for x in stats["ignored_files"]) or "none"),
           f"- findings: HIGH {counts['high']} / MEDIUM {counts['medium']} / LOW {counts['low']}", ""]
    for n in notes:
        out.append(f"> {n}")
    if notes:
        out.append("")
    by_file: dict[str, list[Finding]] = {}
    for f in fs:
        by_file.setdefault(f.path, []).append(f)
    for path in sorted(by_file, key=lambda p: (-max(SEV_RANK[f.severity] for f in by_file[p]), p)):
        out.append(f"## {path}")
        for f in by_file[path]:
            loc = f"L{f.line}" if f.line else "file"
            val = f" `{f.value}`" if f.value else ""
            ex = f.excerpt.strip()
            ex = (ex[:117] + "...") if len(ex) > 120 else ex
            out.append(f"- {loc} **{f.severity.upper()}** {f.detector}:{val} {f.detail}"
                       + (f"  \n  `{ex}`" if ex else ""))
        out.append("")
    return "\n".join(out)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Scan a tree for numeric/structural fingerprints of private facts.")
    ap.add_argument("tree", type=Path)
    ap.add_argument("--ledger", type=Path, help="private facts ledger (keep it OUTSIDE the tree)")
    ap.add_argument("--fences", type=Path, help="private/synthetic geo fences (JSON or GeoJSON)")
    ap.add_argument("--format", choices=("md", "json"), default="md")
    ap.add_argument("--fail-on", choices=SEVERITIES, default="medium")
    ap.add_argument("--min-severity", choices=SEVERITIES, default="low", help="hide findings below this")
    ap.add_argument("--disable", action="append", default=[], choices=DETECTORS, help="turn a detector off")
    ap.add_argument("--exclude", action="append", default=[], help="glob on tree-relative paths to skip")
    ap.add_argument("--version", action="version", version=__version__)
    a = ap.parse_args(argv)
    if not a.tree.is_dir():
        print(f"error: not a directory: {a.tree}", file=sys.stderr)
        return 2
    notes = []
    try:
        ledger = load_ledger(a.ledger) if a.ledger else None
        fences = load_fences(a.fences) if a.fences else None
    except (OSError, ValueError, KeyError, SystemExit) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if ledger is None:
        notes.append("WARNING: no --ledger given; the ledger and derived detectors are inactive. "
                     "A clean result is NOT evidence that business numbers are absent.")
    if ledger is not None:
        generic = [f.name for f in ledger.facts.values() if f.sig <= 1 or (f.weak and not f.keywords)]
        if generic:
            notes.append("note: ledger facts with 1 significant digit or no context words are generic and mostly "
                         "produce noise; prefer distinctive values and add context= keywords: " + ", ".join(generic))
    if ledger is not None and ledger.synthetic_example:
        notes.append(f"note: the ledger is marked '{EXAMPLE_MARK}', so it may sit inside the tree. "
                     "If it holds real values, delete that marker line.")
    if ledger is not None and not ledger.facts and not ledger.sequences:
        notes.append("WARNING: the ledger has no facts; ledger/derived detectors saw nothing to look for.")
    if fences is None:
        notes.append("note: no --fences given; coordinates are judged by precision only (no HIGH geo findings).")
    fs, stats = scan_tree(a.tree, ledger, fences, a.disable, a.exclude, a.fences)
    if stats["text_files"] == 0:
        notes.append("WARNING: zero text files were scanned; check the path and --exclude globs.")
    if stats["long_lines"]:
        notes.append(f"note: {stats['long_lines']} line(s) longer than {MAX_LINE_CHARS} chars were scanned "
                     "in overlapping segments; file:line points at the long line.")
    for n in notes:
        print(n, file=sys.stderr)
    shown = [f for f in fs if SEV_RANK[f.severity] >= SEV_RANK[a.min_severity]]
    if a.format == "json":
        print(json.dumps({"tree": str(a.tree), "stats": stats, "notes": notes,
                          "findings": [asdict(f) for f in shown]}, ensure_ascii=False, indent=2))
    else:
        print(render_md(shown, stats, a.tree, notes))
    return 1 if any(SEV_RANK[f.severity] >= SEV_RANK[a.fail_on] for f in fs) else 0


if __name__ == "__main__":
    sys.exit(main())
