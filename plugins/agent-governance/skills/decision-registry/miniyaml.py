"""A small, strict YAML-subset reader/writer for card frontmatter (stdlib only).

Why not PyYAML: the skill must run on a bare Python 3.9+ with no installs.
Why a *subset*: cards are short, hand-editable records. Supporting the full
YAML spec is not the goal; failing loudly on anything outside the subset is.
A parse error must name the card, never silently drop fields -- a card that
loses its `force` or `scope` quietly is worse than one that refuses to load.

Supported:
  - block mappings (nested by indentation), block sequences of scalars,
    sequences of mappings (`- key: value`)
  - flow sequences `[a, "b, c", 3]` and flow mappings `{k: v}` (nestable)
  - plain, single-quoted and double-quoted scalars; `|` literal block scalars
  - plain multi-line scalars (indented continuation lines are folded)
  - `# comments` (full-line, and trailing after a space or tab)

Scalar resolution follows the YAML 1.2 core schema, narrowed on purpose:
  null / ~ / empty -> None, true/false -> bool, integers/floats -> numbers,
  everything else -> str. Dates stay strings. `yes`/`no`/`on`/`off` stay
  strings. Numbers with a leading zero (`007`) stay strings.

Refused with YamlError: anchors/aliases, tags, multi-document, complex keys,
tabs used for indentation, nested block sequences (`- - a`), empty flow
elements (`[a,,b]`), `>` folded block scalars, mapping syntax on a plain
continuation line.

The writer (`dump_scalar`) and the reader are kept in agreement: anything the
reader would interpret specially is quoted by the writer. The round-trip is
tested over a grid of whitespace characters (including non-ASCII ones).
"""
from __future__ import annotations

import re

__all__ = ["YamlError", "loads", "dump_scalar", "dump_flow_list"]


class YamlError(ValueError):
    pass


_INT = re.compile(r"^[-+]?(0|[1-9][0-9]*)$")
_FLOAT = re.compile(r"^[-+]?(\.[0-9]+|(0|[1-9][0-9]*)(\.[0-9]*)?)([eE][-+]?[0-9]+)?$")
#: YAML comments start at '#' preceded by a space or tab (never other whitespace).
_COMMENT = re.compile(r"[ \t]#")


def _resolve_plain(s: str):
    t = s.strip(" \t")
    if t in ("", "~", "null", "Null", "NULL"):
        return None
    if t in ("true", "True", "TRUE"):
        return True
    if t in ("false", "False", "FALSE"):
        return False
    if _INT.match(t):
        return int(t)
    if _FLOAT.match(t) and any(ch.isdigit() for ch in t):
        return float(t)
    if t[:1] in ("&", "*", "!"):
        raise YamlError(f"anchors/aliases/tags are not supported: `{t[:30]}`")
    return t


# ---------------------------------------------------------------- quoted / flow

_ESC = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v",
        "f": "\f", "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\",
        "N": "\x85", "_": "\xa0", "L": "\u2028", "P": "\u2029"}
_HEX = {"x": 2, "u": 4, "U": 8}


def _read_double(s: str, i: int):
    """s[i] == '"'. Decodes YAML double-quoted escapes. Literal tabs are allowed
    (YAML permits them inside quoted scalars). Returns (value, index after quote)."""
    out = []
    j = i + 1
    while j < len(s):
        c = s[j]
        if c == '"':
            return "".join(out), j + 1
        if c == "\\":
            if j + 1 >= len(s):
                break
            e = s[j + 1]
            if e in _ESC:
                out.append(_ESC[e])
                j += 2
                continue
            if e in _HEX:
                n = _HEX[e]
                h = s[j + 2:j + 2 + n]
                if len(h) != n or not re.fullmatch(r"[0-9A-Fa-f]+", h):
                    raise YamlError(f"bad \\{e} escape in double-quoted string: {s[i:i + 40]}")
                out.append(chr(int(h, 16)))
                j += 2 + n
                continue
            raise YamlError(f"unknown escape `\\{e}` in double-quoted string: {s[i:i + 40]}")
        out.append(c)
        j += 1
    raise YamlError(f"unterminated double-quoted string: {s[i:i + 40]}")


def _read_single(s: str, i: int):
    j = i + 1
    out = []
    while j < len(s):
        if s[j] == "'":
            if j + 1 < len(s) and s[j + 1] == "'":
                out.append("'")
                j += 2
                continue
            return "".join(out), j + 1
        out.append(s[j])
        j += 1
    raise YamlError(f"unterminated single-quoted string: {s[i:i + 40]}")


def _skip_ws(s, i):
    while i < len(s) and s[i] in " \t":
        i += 1
    return i


def _read_flow(s: str, i: int):
    """Parse a flow node starting at s[i]. Returns (value, next index)."""
    i = _skip_ws(s, i)
    if i >= len(s):
        raise YamlError("unexpected end of flow collection")
    ch = s[i]
    if ch == "[":
        out = []
        i = _skip_ws(s, i + 1)
        if i < len(s) and s[i] == "]":
            return out, i + 1
        while True:
            if i < len(s) and s[i] in ",]":
                raise YamlError(f"empty element in flow sequence: {s[:60]}")
            v, i = _read_flow(s, i)
            out.append(v)
            i = _skip_ws(s, i)
            if i < len(s) and s[i] == ",":
                i = _skip_ws(s, i + 1)
                if i < len(s) and s[i] == "]":  # a single trailing comma is legal YAML
                    return out, i + 1
                continue
            if i < len(s) and s[i] == "]":
                return out, i + 1
            raise YamlError(f"expected `,` or `]` in flow sequence: {s[:60]}")
    if ch == "{":
        out = {}
        i = _skip_ws(s, i + 1)
        if i < len(s) and s[i] == "}":
            return out, i + 1
        while True:
            if i < len(s) and s[i] in ",}":
                raise YamlError(f"empty entry in flow mapping: {s[:60]}")
            k, i = _read_flow_scalar(s, i, key=True)
            i = _skip_ws(s, i)
            if i >= len(s) or s[i] != ":":
                raise YamlError(f"expected `:` in flow mapping: {s[:60]}")
            v, i = _read_flow(s, i + 1)
            out[str(k)] = v
            i = _skip_ws(s, i)
            if i < len(s) and s[i] == ",":
                i = _skip_ws(s, i + 1)
                if i < len(s) and s[i] == "}":
                    return out, i + 1
                continue
            if i < len(s) and s[i] == "}":
                return out, i + 1
            raise YamlError(f"expected `,` or `}}` in flow mapping: {s[:60]}")
    return _read_flow_scalar(s, i)


def _read_flow_scalar(s: str, i: int, key: bool = False):
    i = _skip_ws(s, i)
    if i < len(s) and s[i] == '"':
        return _read_double(s, i)
    if i < len(s) and s[i] == "'":
        return _read_single(s, i)
    j = i
    while j < len(s):
        c = s[j]
        if c in ",]}":
            break
        if key and c == ":" and (j + 1 == len(s) or s[j + 1] in " \t,]}"):
            break
        if c == "#" and j > i and s[j - 1] in " \t":
            raise YamlError("comment inside a flow collection")
        j += 1
    return _resolve_plain(s[i:j]), j


def _strip_plain_comment(r: str):
    """Returns (text, had_comment)."""
    m = _COMMENT.search(r)
    return (r[:m.start()], True) if m else (r, False)


def _parse_inline(rest: str, where: str):
    """Parse the text after `key:` / `- ` on one line.
    Returns (value, empty, had_comment)."""
    r = rest.strip(" \t")
    if not r or r.startswith("#"):
        return None, True, bool(r)
    if r[0] in "[{":
        v, j = _read_flow(r, 0)
        tail = r[j:].strip(" \t")
        if tail and not tail.startswith("#"):
            raise YamlError(f"{where}: trailing text after flow collection: `{tail[:30]}`")
        return v, False, bool(tail)
    if r[0] == '"':
        v, j = _read_double(r, 0)
    elif r[0] == "'":
        v, j = _read_single(r, 0)
    else:
        plain, had = _strip_plain_comment(r)
        return _resolve_plain(plain), False, had
    tail = r[j:].strip(" \t")
    if tail and not tail.startswith("#"):
        raise YamlError(f"{where}: trailing text after quoted string: `{tail[:30]}`")
    return v, False, bool(tail)


# ---------------------------------------------------------------- block parser


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_blank(line: str) -> bool:
    s = line.strip(" \t")
    return not s or s.startswith("#")


def _is_seq_item(line: str) -> bool:
    s = line.lstrip(" ")
    return s == "-" or s.startswith("- ")


# key: plain (no ':' / '#'), or quoted; separator is ':' then space/tab or end of line
_KEY = re.compile(r"""^(?P<key>"[^"]*"|'[^']*'|[^ \t#'"\[\]{},][^:#]*?)[ \t]*:(?:[ \t]+(?P<rest>.*)|[ \t]*)$""")
_MAPPING_SYNTAX = re.compile(r":[ \t]|:$")


class _P:
    def __init__(self, text: str):
        self.lines = text.split("\n")
        for n, ln in enumerate(self.lines, 1):
            if "\t" in ln[:len(ln) - len(ln.lstrip(" \t"))]:
                raise YamlError(f"line {n}: tab used for indentation")
        self.n = len(self.lines)

    def next_content(self, i: int) -> int:
        while i < self.n and _is_blank(self.lines[i]):
            i += 1
        return i

    def block(self, i: int, indent: int):
        i = self.next_content(i)
        if i >= self.n:
            return None, i
        if _is_seq_item(self.lines[i]):
            return self.seq(i, _indent(self.lines[i]))
        return self.mapping(i, _indent(self.lines[i]))

    def mapping(self, i: int, indent: int):
        out: dict = {}
        while True:
            i = self.next_content(i)
            if i >= self.n:
                break
            line = self.lines[i]
            ind = _indent(line)
            if ind < indent:
                break
            if ind > indent:
                raise YamlError(f"line {i + 1}: unexpected indentation: `{line.strip()[:40]}`")
            if _is_seq_item(line):
                break
            s = line.strip(" ")
            m = _KEY.match(s)
            if not m:
                raise YamlError(f"line {i + 1}: expected `key: value`, got `{s[:40]}`")
            key = m.group("key")
            if key[:1] in "\"'":
                key = key[1:-1]
            key = key.strip(" \t")
            if key in out:
                raise YamlError(f"line {i + 1}: duplicate key `{key}`")
            rest = m.group("rest") or ""
            out[key], i = self.value(i, indent, rest, f"line {i + 1} `{key}`", in_seq=False)
        return out, i

    def seq(self, i: int, indent: int):
        out: list = []
        while True:
            i = self.next_content(i)
            if i >= self.n:
                break
            line = self.lines[i]
            ind = _indent(line)
            if ind != indent or not _is_seq_item(line):
                if ind > indent:
                    raise YamlError(f"line {i + 1}: unexpected indentation in sequence")
                break
            after = line[indent + 1:]
            rs = after.strip(" ")
            if rs == "-" or rs.startswith("- "):
                raise YamlError(f"line {i + 1}: nested block sequences are not supported; "
                                f"use a flow list `[a, b]`")
            if rs and rs[0] not in "\"'[{" and _KEY.match(rs):
                # `- key: value` -> mapping starting at the item's content column
                col = indent + 1 + (len(after) - len(after.lstrip(" ")))
                self.lines[i] = " " * col + rs
                v, i = self.mapping(i, col)
                out.append(v)
                continue
            v, i = self.value(i, indent, after, f"line {i + 1} sequence item", in_seq=True)
            out.append(v)
        return out, i

    def value(self, i: int, indent: int, rest: str, where: str, in_seq: bool):
        r = rest.strip(" \t")
        if r[:1] == ">" and re.fullmatch(r">[-+]?([ \t]+#.*)?", r):
            raise YamlError(f"{where}: `>` folded block scalars are not supported; use `|`")
        if r[:1] == "|" and re.fullmatch(r"\|[-+]?([ \t]+#.*)?", r):
            return self.block_scalar(i + 1, indent, r[1:2], where)
        v, empty, had_comment = _parse_inline(rest, where)
        j = self.next_content(i + 1)
        if empty:
            if j < self.n:
                ind = _indent(self.lines[j])
                nxt_seq = _is_seq_item(self.lines[j])
                if in_seq and ind > indent and nxt_seq:
                    raise YamlError(f"line {j + 1}: nested block sequences are not supported; "
                                    f"use a flow list `[a, b]`")
                if ind > indent or (ind == indent and nxt_seq and not in_seq):
                    return self.block(j, ind)
            return None, i + 1
        # plain multi-line scalar: fold deeper-indented continuation lines
        if isinstance(v, str) and r[:1] not in "\"'[{" and not had_comment:
            parts = [v]
            k = i + 1
            while k < self.n:
                ln = self.lines[k]
                if not ln.strip(" \t"):
                    k += 1
                    continue
                if _indent(ln) <= indent or ln.strip(" ").startswith("#"):
                    break
                txt, had = _strip_plain_comment(ln.strip(" "))
                txt = txt.strip(" \t")
                if _MAPPING_SYNTAX.search(txt):
                    raise YamlError(f"line {k + 1}: `key: value` syntax on a continuation line "
                                    f"of {where}; indent error or missing quotes")
                parts.append(txt)
                k += 1
                if had:  # a comment ends the plain scalar
                    break
            if len(parts) > 1:
                nk = self.next_content(k)
                if nk < self.n and _indent(self.lines[nk]) > indent:
                    raise YamlError(f"line {nk + 1}: text after a comment inside {where}")
                return " ".join(parts), k
        if j < self.n and _indent(self.lines[j]) > indent:
            raise YamlError(f"{where}: unexpected indented block after a scalar value")
        return v, i + 1

    def block_scalar(self, i: int, indent: int, chomp: str, where: str):
        body = []
        k = i
        block_ind = None
        while k < self.n:
            ln = self.lines[k]
            if ln.strip(" "):
                ind = _indent(ln)
                if ind <= indent:
                    break
                if block_ind is None:
                    block_ind = ind
                elif ind < block_ind:
                    raise YamlError(f"line {k + 1}: line in block scalar {where} is less "
                                    f"indented than its first line")
                body.append(ln[block_ind:])
            else:
                body.append("")
            k += 1
        # trailing blank lines belong to the chomping indicator, not to the next key
        if chomp != "+":
            while body and body[-1] == "":
                body.pop()
        text = "\n".join(body)
        if chomp != "-" and text:
            text += "\n"
        return text, k


def loads(text: str) -> dict:
    """Parse a frontmatter block. Returns a dict (empty text -> {})."""
    if not text.strip():
        return {}
    p = _P(text)
    i = p.next_content(0)
    if i < p.n and _indent(p.lines[i]) != 0:
        raise YamlError("top level must start at column 0")
    v, j = p.block(0, 0)
    j = p.next_content(j)
    if j < p.n:
        raise YamlError(f"line {j + 1}: could not parse `{p.lines[j].strip()[:40]}`")
    if not isinstance(v, dict):
        raise YamlError("top level is not a mapping")
    return v


# ---------------------------------------------------------------- writer

_UNSAFE_START = set("-?:,[]{}#&*!|>'\"%@`~")


def _json_like_double(s: str) -> str:
    out = ['"']
    for c in s:
        if c == '"':
            out.append('\\"')
        elif c == "\\":
            out.append("\\\\")
        elif c == "\n":
            out.append("\\n")
        elif c == "\t":
            out.append("\\t")
        elif c == "\r":
            out.append("\\r")
        elif ord(c) < 0x20 or c in "\x7f\x85\u2028\u2029":
            out.append(f"\\u{ord(c):04x}")
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


def dump_scalar(v, flow: bool = False) -> str:
    """Render one scalar so that `loads` gives back exactly the same value.

    Never build frontmatter with bare f-strings: a value starting with `[` or
    containing `: ` or ` #` would write a card that only explodes on the next
    load, after it is already on disk. Belt and braces: quote whenever *any*
    whitespace character (not only ASCII space) touches '#' or ':'.
    """
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    plain_ok = (
        s
        and s == s.strip()
        and s.isprintable()
        and s[0] not in _UNSAFE_START
        and not re.search(r"\s#|:\s|:$", s)
        and _resolve_plain(s) == s
        and not (flow and any(c in s for c in ",[]{}"))
    )
    return s if plain_ok else _json_like_double(s)


def dump_flow_list(vals) -> str:
    return "[" + ", ".join(dump_scalar(v, flow=True) for v in vals) + "]"
