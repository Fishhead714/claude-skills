#!/usr/bin/env python3
"""Scan recently modified notes for things that look "already decided" and
queue them as candidates.

Detection is not enrollment. This script writes only `_inbox/QUEUE.md`, and
load_cards() only reads constraints/, decisions/ and stances/ -- so however
noisy the scan is, it cannot pollute the registry. Enrollment is always done
by a person (or an agent the person directs) via add.py.

Configuration lives in schema.json under `scan`:
  root            notes root, relative to the registry directory (default "..")
  include_dirs    only files under these dirs (relative to root); empty = all
  exclude_dirs    skip these dirs (relative to root)
  extensions      file extensions to read (default [".md"])
  lookback_days   only files modified within this many days
  signals_strong  phrases that admit a file to the queue (case-insensitive)
  signals_weak    phrases used only for ranking
  max_report      how many candidates to list

De-duplication: files already cited by a card's `evidence`, files listed in
`_inbox/IGNORE.txt`, and excluded dirs are skipped.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import registry as R


def _phrase_re(phrase: str):
    # word boundaries on the outer edges only, so "must not" does not hit "mustnot"
    # but multi-word phrases still match across a single space
    body = r"\s+".join(re.escape(w) for w in phrase.split())
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


def _rel_under(rel: str, dirs) -> bool:
    return any(rel == d.strip("/") or rel.startswith(d.strip("/") + "/") for d in dirs)


def changed_files(root: Path, cfg: dict, rd: Path) -> list:
    if not root.is_dir():
        # Never return [] here: that would make "could not scan" and "nothing
        # found" the same output, and overwrite the previous real queue with a
        # fake empty one.
        raise SystemExit(f"error: scan root does not exist: {root} -- scan aborted, "
                         f"QUEUE.md left untouched")
    cutoff = time.time() - float(cfg.get("lookback_days", 14)) * 86400
    exts = tuple(e.lower() for e in cfg.get("extensions") or [".md"])
    inc = cfg.get("include_dirs") or []
    exc = cfg.get("exclude_dirs") or []
    rd_res = rd.resolve()
    out = []
    try:
        for dirpath, dirnames, filenames in os.walk(root, onerror=_walk_error):
            d = Path(dirpath)
            if d.resolve() == rd_res:
                dirnames[:] = []  # never scan the registry itself
                continue
            dirnames[:] = sorted(n for n in dirnames if not n.startswith("."))
            for name in sorted(filenames):
                if not name.lower().endswith(exts):
                    continue
                p = d / name
                rel = p.relative_to(root).as_posix()
                if inc and not _rel_under(rel, inc):
                    continue
                if _rel_under(rel, exc):
                    continue
                try:
                    if p.stat().st_mtime < cutoff:
                        continue
                except OSError:
                    continue
                out.append(rel)
    except OSError as e:
        raise SystemExit(f"error: scanning {root} failed: {e} -- scan aborted, "
                         f"QUEUE.md left untouched")
    return out


def _walk_error(e: OSError):
    raise e


def main(argv=None) -> int:
    R.utf8_stdio()
    ap = argparse.ArgumentParser(description="Queue candidate decisions from recent notes "
                                             "(writes _inbox/QUEUE.md only)")
    R.add_registry_arg(ap)
    ap.add_argument("--root", help="override scan.root (absolute, or relative to cwd)")
    a = ap.parse_args(argv)
    rd = R.resolve_or_exit(a.registry)
    schema = R.load_schema(rd)
    cfg = schema.get("scan") or {}
    root = Path(a.root).resolve() if a.root else (rd / cfg.get("root", "..")).resolve()

    strong_sigs = [(s, _phrase_re(s)) for s in cfg.get("signals_strong") or []]
    weak_sigs = [(s, _phrase_re(s)) for s in cfg.get("signals_weak") or []]
    if not strong_sigs:
        raise SystemExit("error: schema.json scan.signals_strong is empty; nothing could "
                         "ever be admitted. Refusing to write an empty queue")

    try:
        cards = R.load_cards(rd)
    except R.CardError as e:
        raise SystemExit(f"error: a card cannot be read, fix it first: {e}")
    cited = set()
    for c in cards:
        for e in c.get("evidence") or []:
            cited.add(str(e).strip().replace("\\", "/"))

    ignore_p = rd / "_inbox" / "IGNORE.txt"
    ignored = set()
    if ignore_p.is_file():
        ignored = {l.strip().replace("\\", "/")
                   for l in ignore_p.read_text(encoding="utf-8").splitlines()
                   if l.strip() and not l.strip().startswith("#")}

    hits, skipped = [], 0
    for rel in changed_files(root, cfg, rd):
        if rel in cited or rel in ignored:
            continue
        p = root / rel
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            skipped += 1
            continue
        strong, weak, samples = set(), set(), []
        for ln in text.splitlines():
            s = ln.strip()
            if len(s) < 6 or s.startswith(("|", ">", "```")):
                continue
            hit_here = False
            for name, rx in strong_sigs:
                if rx.search(s):
                    strong.add(name)
                    hit_here = True
            for name, rx in weak_sigs:
                if rx.search(s):
                    weak.add(name)
            # only strong-signal lines are worth showing as samples
            if hit_here and len(samples) < 2 and s[:140] not in samples:
                samples.append(s[:140])
        # strong signals admit; weak signals only rank
        if strong:
            hits.append((rel, sorted(strong), sorted(weak), samples))

    hits.sort(key=lambda h: (-len(h[1]), -len(h[2]), h[0]))
    total = len(hits)
    hits = hits[: int(cfg.get("max_report", 12))]
    inbox = rd / "_inbox"
    inbox.mkdir(exist_ok=True)
    q = inbox / "QUEUE.md"
    lines = [
        "# Candidate queue (generated, do not edit)",
        "",
        f"Scanned {date.today().isoformat()} under `{root}`, lookback "
        f"{cfg.get('lookback_days', 14)} days: {total} files matched, top {len(hits)} "
        f"listed by number of strong signals."
        + (f" WARNING: {skipped} files could not be read and were not scanned." if skipped else ""),
        "",
        "**Nothing here is a boundary.** These are leads where a boundary might be hiding.",
        "Each entry has exactly two exits: create a card with `add.py new ...` (put this path",
        "in its `evidence` and it is skipped next time), or add the path to `IGNORE.txt`.",
        "",
    ]
    if not hits:
        lines.append("(No candidates this time.)")
    for rel, strong, weak, samples in hits:
        lines.append(f"## `{rel}`")
        lines.append(f"strong: {' / '.join(strong)}"
                     + (f"   (weak: {' / '.join(weak)})" if weak else ""))
        for s in samples:
            lines.append(f"> {s}")
        lines.append("")
    q.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(hits)} candidates ({total} matched) -> {q}"
          + (f"; {skipped} unreadable files skipped" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
