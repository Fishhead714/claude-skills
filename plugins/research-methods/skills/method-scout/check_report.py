#!/usr/bin/env python3
"""Required-items check for method-scout reports.

Usage: check_report.py <report.md> [...]     exit 0 = all pass, 1 = something missing

Checks only that required sections and frontmatter fields exist, that template placeholders
<<...>> are gone, and that the `review` field records both reviews. It cannot tell whether the
content is right — passing says nothing about correctness; that is what the reviewers are for.
Standard library only.
"""
import os
import re
import sys

REQUIRED_KEYS = ["title", "domain", "updated", "status", "review"]
# (label, regex): headings are matched by keyword, so you may add sections or renumber
REQUIRED_HEADINGS = [
    ("sub-question table", r"^##\s.*[Ss]ub-question"),
    ("conclusions first", r"^##\s.*[Cc]onclusions first"),
    ("method cards", r"^##\s.*[Mm]ethod cards"),
    ("unverified — do not cite", r"^##\s.*[Uu]nverified"),
    ("coverage gaps", r"^##\s.*[Gg]aps"),
    ("closing review record", r"^##\s.*[Rr]eview"),
    ("run log", r"^##\s.*[Rr]un log"),
]
REQUIRED_TEXT = [
    ("current baseline", r"[Cc]urrent baseline"),
    ("main-line break", r"[Mm]ain-line break"),
    ("stopping rule", r"[Ss]topping rule"),
    ("where originals are archived", r"[Oo]riginals archived"),
]


def check(path):
    text = open(path, encoding="utf-8").read()
    problems = []
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return ["no frontmatter"]
    fm = dict(re.findall(r"^(\w+):\s*(.*)$", m.group(1), re.M))
    for k in REQUIRED_KEYS:
        if not fm.get(k, "").strip():
            problems.append(f"frontmatter missing {k}")
    review = fm.get("review", "")
    if review:
        v = re.search(r"verifier:\s*([✓✗])", review)
        a = re.search(r"auditor:\s*([✓✗])(\s*\()?", review)
        if not v:
            problems.append("review does not say whether the verifier passed (✓/✗)")
        elif v.group(1) == "✗":
            problems.append("review has verifier ✗ — the fact-check is mandatory for every report")
        if not a:
            problems.append("review does not say whether the auditor passed (✓/✗)")
        elif a.group(1) == "✗" and not a.group(2):
            problems.append("review has auditor ✗ without a reason; format: auditor: ✗(reason)")
    for name, pat in REQUIRED_HEADINGS:
        if not re.search(pat, text, re.M):
            problems.append(f"missing section: {name}")
    for name, pat in REQUIRED_TEXT:
        if not re.search(pat, text):
            problems.append(f"body never states: {name}")
    # method cards: every card listed must exist in methods/, the sibling of reports/
    mc = re.search(r"[Mm]ethod cards added this round[:：]\s*(.+)", text)
    if not mc:
        problems.append('no "Method cards added this round:" line — methods not filed are lost '
                        'once the report is read (write "none" + reason if there are none)')
    elif not mc.group(1).strip().lower().startswith("none"):
        mdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(path))), "methods")
        names = re.findall(r"[\w\-]+\.md", mc.group(1))
        if not names:
            problems.append('"Method cards added this round" lists no .md file names')
        for n in names:
            if not os.path.isfile(os.path.join(mdir, n)):
                problems.append(f"listed method card does not exist: methods/{n}")
    left = re.findall(r"<<[^>]*>>", text)
    if left:
        problems.append(f"{len(left)} template placeholder(s) left, e.g. {left[0]}")
    return problems


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    bad = 0
    for p in sys.argv[1:]:
        probs = check(p)
        if probs:
            bad += 1
            print(f"✗ {p}")
            for x in probs:
                print(f"   - {x}")
        else:
            print(f"✓ {p} (required items present; content not checked)")
    sys.exit(1 if bad else 0)
