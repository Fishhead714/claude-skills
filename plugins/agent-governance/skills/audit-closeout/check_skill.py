#!/usr/bin/env python3
"""Self-check for an orchestration skill: does everything SKILL.md names actually exist here?

Why: an orchestration skill is mostly "dispatch X, run Y, read Z". A dangling reference only
blows up at run time, usually after work has already been dispatched.

What it checks
  MISSING  backticked kebab-case names (agents / skills / commands / plugins) not found in your
           Claude Code setup
  MISSING  backticked relative paths (containing "/" or ending .md/.py) that don't resolve
  MISSING  "three severities" / "four types" … in prose followed by a table with a different row count
  WARN     paragraphs that largely duplicate a canonical document (--canon), description too long

Usage
  python3 check_skill.py [SKILL.md] [--allow NAME ...] [--canon FILE]

  --allow   names that are built into your Claude Code and have no file on disk (e.g. loop).
            Every name you add here is exempt forever, so only add ones you have seen in your
            session's skill/command list.
  --canon   a document that is the authoritative source for some method; paragraphs of SKILL.md
            that repeat it (>50% character 8-gram overlap) are flagged, because two copies drift.

Exit code 1 if anything is MISSING. Standard library only.
"""
import argparse
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))   # <plugin>/skills/<skill>/ -> <plugin>
CLAUDE = os.path.expanduser("~/.claude")

NUM_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
COUNT_NOUNS = r"(kinds|types|tiers|levels|classes|categories|severities|grades|cases)"


def _names_in(pattern):
    out = set()
    for p in glob.glob(pattern, recursive=True):
        base = os.path.basename(p.rstrip("/"))
        out.add(base[:-3] if base.endswith(".md") else base)
    return out


def known_components(extra_roots):
    """Scan the environment instead of hard-coding a list: the environment is the authority."""
    roots = [CLAUDE, os.path.join(os.getcwd(), ".claude"), PLUGIN_ROOT] + extra_roots
    names = set()
    for r in roots:
        for kind in ("agents", "skills", "commands"):
            names |= _names_in(os.path.join(r, kind, "*"))
    # installed plugins and marketplaces: <...>/plugins/<plugin>/{agents,skills,commands}/*
    for base in glob.glob(os.path.join(CLAUDE, "plugins", "**", ".claude-plugin"), recursive=True):
        plugin_dir = os.path.dirname(base)
        names.add(os.path.basename(plugin_dir))
        for kind in ("agents", "skills", "commands"):
            names |= _names_in(os.path.join(plugin_dir, kind, "*"))
    # sibling plugins when this skill lives inside a checked-out marketplace
    market = os.path.dirname(PLUGIN_ROOT)
    for plugin_dir in glob.glob(os.path.join(market, "*")):
        if os.path.isdir(os.path.join(plugin_dir, ".claude-plugin")):
            names.add(os.path.basename(plugin_dir))
            for kind in ("agents", "skills", "commands"):
                names |= _names_in(os.path.join(plugin_dir, kind, "*"))
    return names


def strip_fences(text):
    """Remove ``` fences first: triple backticks break inline-backtick pairing."""
    return re.sub(r"```.*?```", "\n", text, flags=re.S)


def check_names(text, known, allow, missing):
    for tok in sorted(set(re.findall(r"`([a-z][a-z0-9-]{3,})`", strip_fences(text)))):
        if "-" not in tok or tok in known or tok in allow:
            continue
        missing.append(f"reference not found: `{tok}` is not an installed agent, skill, command or plugin "
                       f"(install it, reword it as a generic role, or --allow it if it is built in)")


def check_paths(text, skill_dir, missing):
    for raw in re.findall(r"`([^`\n]*(?:/|\.md|\.py)[^`\n]*)`", strip_fences(text)):
        s = raw.strip()
        if " " in s or "=" in s or "<" in s or s.startswith(("/", "~", "http")):
            continue
        p = s.replace("${CLAUDE_PLUGIN_ROOT}", PLUGIN_ROOT)
        if not os.path.isabs(p):
            if "/" not in p:
                if "*" in p or "YYYY" in p:
                    continue      # naming patterns like AUDIT-*.md, not files
                p = os.path.join(skill_dir, p)
            else:
                continue          # relative to some other project; can't resolve from here
        if "*" in p:
            if not glob.glob(p):
                missing.append(f"path pattern matches nothing: {s}")
        elif not os.path.exists(p):
            missing.append(f"path does not exist: {s} -> {p}")


def check_counts(text, missing):
    """A count written in prose must equal the rows of the table that immediately follows it.
    This is the number people forget to update when they add a table row, and it reads naturally."""
    for m in re.finditer(r"\b(" + "|".join(NUM_WORDS) + r")\s+" + COUNT_NOUNS + r"\b", text, re.I):
        tail = text[m.end():]
        tbl = re.search(r"\n\|.*\|\n\|[-:| ]+\|\n((?:\|.*\|\n)+)", "\n" + tail)
        if not tbl or tbl.start() > 400:
            continue
        rows = len([r for r in tbl.group(1).strip().splitlines() if r.startswith("|")])
        if rows != NUM_WORDS[m.group(1).lower()]:
            missing.append(f"count mismatch: prose says '{m.group(0)}', the table after it has {rows} rows")


def check_canon(body, canon_path, warn):
    src = open(canon_path, encoding="utf-8").read()

    def grams(x):
        x = re.sub(r"\s+", "", x)
        return {x[i:i + 8] for i in range(len(x) - 7)}

    src_g = grams(src)
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if len(re.sub(r"\s+", "", para)) < 40:
            continue
        g = grams(para)
        if g and len(g & src_g) / len(g) > 0.5:
            warn.append(f"{len(g & src_g) / len(g):.0%} overlap with {os.path.basename(canon_path)} "
                        f"(two copies drift): {para[:50]}…")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("skill_md", nargs="?", default=os.path.join(HERE, "SKILL.md"))
    ap.add_argument("--allow", nargs="*", default=[], help="built-in names with no file on disk")
    ap.add_argument("--canon", help="authoritative document the skill must not duplicate")
    ap.add_argument("--root", nargs="*", default=[], help="extra dirs containing agents/ skills/ commands/")
    args = ap.parse_args()

    text = open(args.skill_md, encoding="utf-8").read()
    body = text.split("---", 2)[-1] if text.startswith("---") else text
    missing, warn = [], []
    check_names(text, known_components(args.root), set(args.allow), missing)
    check_paths(text, os.path.dirname(os.path.abspath(args.skill_md)), missing)
    check_counts(text, missing)
    if args.canon:
        check_canon(body, args.canon, warn)
    fm = text.split("---")[1] if text.startswith("---") else ""
    d = re.search(r"description:\s*(.*)", fm)
    if d and len(d.group(1)) > 1400:
        warn.append(f"description is {len(d.group(1))} characters; it is always loaded into context, keep it short")

    for w in warn:
        print(f"WARN     {w}")
    for m in missing:
        print(f"MISSING  {m}")
    print(f"\n{len(missing)} MISSING / {len(warn)} WARN")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
