#!/usr/bin/env python3
"""ossprobe — hard-gate feasibility check for open-source candidate projects.

Mechanises the checks in the oss-benchmark workflow that are needed every time and easy to miss
every time: repository activity, license, Python version constraints, hidden heavy accelerator
dependencies, and whether there is a scriptable entry point. Candidates that fail these gates are
not worth reading further.

Standard library only. The GitHub API is called anonymously (60 requests/hour); GITHUB_TOKEN or
GH_TOKEN is used automatically if set, to raise the limit.

Usage:
    ossprobe.py owner/name [owner/name ...] [--clone] [--target-python 3.12] [--json]
    ossprobe.py https://github.com/owner/name --clone --keep

--clone makes a shallow clone in a temp dir for static checks (dependencies / entry points /
GUI-only). Without --clone only API metadata is checked.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.github.com"

# Heavy accelerator dependencies that commonly fail at install time — typically because they
# compile CUDA code, pin narrow CUDA/driver/torch versions, or lag behind new GPU generations.
# Edit this table to match your own hardware and experience.
HEAVY_DEPS = {
    "flash-attn": "flash-attn builds from source and needs CUDA_HOME and a matching toolkit; check your GPU generation is supported",
    "flash_attn": "same as flash-attn",
    "vllm": "vLLM is picky about CUDA/driver versions and GPU generations",
    "deepspeed": "DeepSpeed compiles CUDA ops; environment-sensitive",
    "apex": "NVIDIA apex builds from source; a long-standing environment trap",
    "bitsandbytes": "bitsandbytes is CUDA-version sensitive; new GPU architectures are often supported late",
    "paddlepaddle": "PaddlePaddle ships its own CUDA builds; check support for your GPU/driver before relying on it",
    "paddleocr": "depends on PaddlePaddle, same caveat",
    "triton": "triton is tightly coupled to torch/CUDA versions; standalone installs conflict easily",
    "xformers": "xformers must match torch/CUDA versions, often needs a rebuild",
    "mamba-ssm": "compiles CUDA ops",
    "causal-conv1d": "compiles CUDA ops",
}

# GUI frameworks. GUI-only entry points = not scriptable: you can only click through it, or
# re-implement the algorithm yourself.
GUI_MARKERS = ["PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter", "wx", "kivy", "qgis.gui"]

# Licenses needing a human look. Common permissive licenses pass; copyleft and "unidentified" need review.
PERMISSIVE = {"MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "0BSD", "Unlicense", "MPL-2.0"}
COPYLEFT = {"GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0"}

STALE_RED_DAYS = 365
STALE_YELLOW_DAYS = 180


# ---------------------------------------------------------------- helpers


def parse_slug(s):
    """Accepts 'owner/name', a full URL, or a URL ending in .git."""
    s = s.strip().rstrip("/")
    m = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?$", s)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    if re.fullmatch(r"[\w.-]+/[\w.-]+", s):
        return s
    raise ValueError(f"not a repository identifier: {s!r} (need owner/name or a GitHub URL)")


def gh_get(path):
    """GET the GitHub API. Returns (data, error_str); 404 returns (None, None) meaning "no such resource"."""
    req = urllib.request.Request(
        API + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ossprobe",
        },
    )
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        if e.code in (403, 429):
            remaining = e.headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                reset = e.headers.get("X-RateLimit-Reset")
                when = ""
                if reset and reset.isdigit():
                    when = datetime.fromtimestamp(int(reset), timezone.utc).strftime(" (resets %H:%M UTC)")
                return None, f"GitHub API rate limit hit{when}; set GITHUB_TOKEN for a higher limit"
            return None, f"HTTP {e.code}: {e.reason}"
        return None, f"HTTP {e.code}: {e.reason}"
    except Exception as e:  # network down, timeout, broken JSON
        return None, f"{type(e).__name__}: {e}"


def days_since(iso):
    if not iso:
        return None
    try:
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - dt).days


def vtuple(s):
    parts = re.findall(r"\d+", s)
    return tuple(int(p) for p in parts[:3]) or (0,)


def spec_allows(spec, target):
    """Practical subset of PEP 440 requires-python: does target fall inside spec?

    Supports >= > <= < == != ~= joined by commas. Clauses it can't parse are let through rather
    than raising a false alarm.
    """
    if not spec:
        return True, ""
    t = vtuple(target)
    for clause in spec.split(","):
        clause = clause.strip()
        m = re.fullmatch(r"(>=|<=|==|!=|~=|>|<)\s*([\d.]+)\*?", clause)
        if not m:
            continue
        op, ver = m.group(1), m.group(2)
        v = vtuple(ver)
        n = len(v)
        tt = t[:n] + (0,) * max(0, n - len(t))  # compare at the declared precision: <3.14 must reject 3.14.1
        if op == ">=" and not tt >= v:
            return False, clause
        if op == ">" and not tt > v:
            return False, clause
        if op == "<=" and not tt <= v:
            return False, clause
        if op == "<" and not tt < v:
            return False, clause
        if op == "==" and tt != v:
            return False, clause
        if op == "!=" and tt == v:
            return False, clause
        if op == "~=":
            # ~=3.11 means >=3.11, ==3.* ; ~=3.11.2 means >=3.11.2, ==3.11.*
            if not tt >= v:
                return False, clause
            upper = v[:-1]
            if upper and t[: len(upper)] != upper:
                return False, clause
    return True, ""


# ---------------------------------------------------------------- clone-side checks


def shallow_clone(slug, dest):
    url = f"https://github.com/{slug}.git"
    p = subprocess.run(
        ["git", "clone", "--depth", "1", "--single-branch", "--quiet", url, dest],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if p.returncode != 0:
        return (p.stderr or p.stdout).strip()[:300]
    return None


def read_text(p, limit=400_000):
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def extract_requires_python(root):
    """Find requires-python in pyproject.toml / setup.py / setup.cfg. Returns (spec, where)."""
    py = root / "pyproject.toml"
    if py.is_file():
        try:
            import tomllib

            data = tomllib.loads(read_text(py))
            spec = (data.get("project") or {}).get("requires-python")
            if spec:
                return spec, "pyproject.toml"
            poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
            if isinstance(poetry.get("python"), str):
                return poetry["python"], "pyproject.toml [tool.poetry]"
        except Exception:
            m = re.search(r'requires-python\s*=\s*["\']([^"\']+)', read_text(py))
            if m:
                return m.group(1), "pyproject.toml (regex fallback)"
    for name in ("setup.py", "setup.cfg"):
        f = root / name
        if f.is_file():
            m = re.search(r'python_requires\s*=\s*["\']([^"\']+)', read_text(f))
            if m:
                return m.group(1), name
    return None, None


def collect_declared_deps(root):
    """Raw text of declared dependencies (pyproject/requirements/setup.py), for keyword matching."""
    chunks = []
    for pat in ("pyproject.toml", "setup.py", "setup.cfg", "requirements*.txt", "environment*.yml"):
        for f in sorted(root.glob(pat))[:10]:
            chunks.append(read_text(f, 100_000))
    reqdir = root / "requirements"
    if reqdir.is_dir():
        for f in sorted(reqdir.glob("*.txt"))[:10]:
            chunks.append(read_text(f, 100_000))
    return "\n".join(chunks)


def grep_source_imports(root, names, max_files=4000):
    """Find imports in .py sources. Projects that import a heavy library unconditionally in code
    while leaving it out of the declared dependencies do exist, so requirements files alone can't
    be trusted. Returns {name: 'path:line'}."""
    hits = {}
    # only spaces/tabs at line start — \s* would also eat newlines and report the wrong line number
    alt = "|".join(re.escape(n) for n in names)
    pattern = re.compile(
        r"^[ \t]*(?:from[ \t]+(" + alt + r")[\s.]|import[ \t]+(" + alt + r")[\s.,]?)",
        re.MULTILINE,
    )
    seen = 0
    for f in root.rglob("*.py"):
        if seen >= max_files:
            break
        parts = f.parts
        if any(p in (".git", "node_modules", "site-packages", ".venv", "venv") for p in parts):
            continue
        seen += 1
        text = read_text(f, 200_000)
        for m in pattern.finditer(text):
            name = m.group(1) or m.group(2)
            if name in hits:
                continue
            line = text.count("\n", 0, m.start()) + 1
            hits[name] = f"{f.relative_to(root)}:{line}"
    return hits


def find_entrypoints(root):
    """Can it be called from a script? Returns a list of evidence (empty = none found)."""
    ev = []
    py = root / "pyproject.toml"
    if py.is_file():
        text = read_text(py)
        if re.search(r"^\s*\[project\.scripts\]", text, re.MULTILINE):
            ev.append("pyproject [project.scripts]")
        if re.search(r"^\s*\[tool\.poetry\.scripts\]", text, re.MULTILINE):
            ev.append("pyproject [tool.poetry.scripts]")
    for name in ("setup.py", "setup.cfg"):
        f = root / name
        if f.is_file() and "console_scripts" in read_text(f):
            ev.append(f"{name} console_scripts")
    for f in list(root.rglob("__main__.py"))[:5]:
        ev.append(f"{f.relative_to(root)}")
    for f in list(root.glob("*.py")) + list(root.glob("*/*.py")):
        if f.name in ("cli.py", "main.py", "__main__.py", "run.py"):
            ev.append(str(f.relative_to(root)))
        if len(ev) > 8:
            break
    return sorted(set(ev))[:8]


def probe_clone(root, target_python):
    """Static checks on the clone. Returns a findings dict."""
    out = {}
    spec, src = extract_requires_python(root)
    out["requires_python"] = spec
    out["requires_python_src"] = src
    if spec and target_python:
        ok, clause = spec_allows(spec, target_python)
        out["python_ok"] = ok
        out["python_clash"] = clause
    declared = collect_declared_deps(root)
    dl = declared.lower()
    out["heavy_declared"] = sorted({d for d in HEAVY_DEPS if d.lower() in dl})
    mod_names = sorted({d.replace("-", "_") for d in HEAVY_DEPS})
    src_hits = grep_source_imports(root, mod_names)
    # imported in source but not declared: the real hidden trap
    declared_mods = {d.replace("-", "_") for d in out["heavy_declared"]}
    out["heavy_undeclared"] = {k: v for k, v in src_hits.items() if k not in declared_mods}
    out["entrypoints"] = find_entrypoints(root)
    gui_hits = grep_source_imports(root, GUI_MARKERS)
    out["gui"] = sorted(gui_hits)
    lic = next((p for p in root.iterdir() if p.is_file() and p.name.upper().startswith("LICEN")), None)
    out["license_file"] = lic.name if lic else None
    out["license_head"] = read_text(lic, 400).strip().splitlines()[0][:120] if lic else None
    py_files = 0
    for f in root.rglob("*.py"):
        if ".git" not in f.parts:
            py_files += 1
        if py_files > 20000:
            break
    out["py_files"] = py_files
    return out


# ---------------------------------------------------------------- verdict


def build_report(slug, target_python, do_clone, keep):
    rep = {"repo": slug, "flags": [], "notes": []}
    meta, err = gh_get(f"/repos/{slug}")
    if err:
        rep["error"] = err
        return rep
    if meta is None:
        rep["error"] = "repository does not exist or is private (GitHub returned 404)"
        return rep

    canonical = meta.get("full_name")
    if canonical and canonical.lower() != slug.lower():
        # GitHub answers renamed/transferred repositories with a 301 that urllib follows silently.
        # The ledger must record the canonical name, or the next check won't match it.
        rep["notes"].append(f"repository renamed/transferred: {slug} → {canonical} (record the latter in the ledger)")
        rep["canonical"] = canonical
        slug = canonical
        rep["repo"] = canonical

    rep["stars"] = meta.get("stargazers_count")
    rep["forks"] = meta.get("forks_count")
    rep["open_issues"] = meta.get("open_issues_count")
    rep["archived"] = bool(meta.get("archived"))
    rep["fork"] = bool(meta.get("fork"))
    rep["pushed_at"] = meta.get("pushed_at")
    rep["created_at"] = meta.get("created_at")
    rep["description"] = meta.get("description")
    rep["homepage"] = meta.get("homepage")
    lic = meta.get("license") or {}
    rep["license"] = lic.get("spdx_id")
    rep["stale_days"] = days_since(meta.get("pushed_at"))

    rel, _ = gh_get(f"/repos/{slug}/releases/latest")
    if rel:
        rep["latest_release"] = rel.get("tag_name")
        rep["latest_release_at"] = rel.get("published_at")

    if rep["archived"]:
        rep["flags"].append(("RED", "repository is archived (maintainer declared it unmaintained)"))
    d = rep["stale_days"]
    if d is not None:
        if d > STALE_RED_DAYS:
            rep["flags"].append(("RED", f"no push for {d} days (>{STALE_RED_DAYS})"))
        elif d > STALE_YELLOW_DAYS:
            rep["flags"].append(("YELLOW", f"quiet for {d} days (>{STALE_YELLOW_DAYS})"))
    if rep["fork"]:
        rep["flags"].append(("YELLOW", "this is a fork; check whether the upstream is the one to look at"))
    spdx = rep["license"]
    if not spdx or spdx in ("NOASSERTION", "NONE"):
        rep["flags"].append(("RED", f"GitHub could not identify the license ({spdx!r}) — read the LICENSE yourself; "
                                    "model weights may be licensed separately from code or carry user/revenue thresholds"))
    elif spdx in COPYLEFT:
        rep["flags"].append(("YELLOW", f"{spdx} is copyleft: usually fine for internal use; check before distributing or embedding"))
    elif spdx not in PERMISSIVE:
        rep["flags"].append(("YELLOW", f"license {spdx} is not in the common permissive list; take a look"))

    if do_clone:
        tmp = tempfile.mkdtemp(prefix="ossprobe-")
        dest = os.path.join(tmp, "repo")
        cerr = shallow_clone(slug, dest)
        if cerr:
            rep["flags"].append(("RED", f"clone failed: {cerr}"))
            shutil.rmtree(tmp, ignore_errors=True)
            return rep
        try:
            c = probe_clone(Path(dest), target_python)
            rep.update(c)
            if c.get("requires_python") and c.get("python_ok") is False:
                rep["flags"].append(
                    ("RED", f"requires-python {c['requires_python']} conflicts with target Python {target_python}"
                            f" (fails on {c['python_clash']}) — needs a separate venv")
                )
            for dep in c.get("heavy_declared", []):
                rep["flags"].append(("RED", f"heavy accelerator dependency {dep}: {HEAVY_DEPS[dep]}"))
            for mod, loc in (c.get("heavy_undeclared") or {}).items():
                key = mod if mod in HEAVY_DEPS else mod.replace("_", "-")
                why = HEAVY_DEPS.get(key, HEAVY_DEPS.get(mod, "heavy accelerator dependency"))
                rep["flags"].append(
                    ("RED", f"source imports {mod} ({loc}) but the dependency files don't declare it — {why}")
                )
            if not c.get("entrypoints"):
                if c.get("gui"):
                    # GUI-only entry = not scriptable: click through it, or re-implement the algorithm
                    rep["flags"].append(
                        ("RED", "no CLI / console_scripts / __main__ entry point, but GUI framework(s) found: "
                                + ",".join(c["gui"]) + " — probably click-only; "
                                "scripting it means re-implementing the algorithm")
                    )
                else:
                    # a pure library without a CLI is normal; just note it
                    rep["notes"].append("no CLI entry point: a pure library (import it)")
            if c.get("license_file") is None:
                rep["flags"].append(("YELLOW", "no LICENSE file in the repository root"))
        finally:
            if keep:
                rep["clone_path"] = dest
            else:
                shutil.rmtree(tmp, ignore_errors=True)
    return rep


def verdict(rep):
    if rep.get("error"):
        return "ERROR"
    levels = {lvl for lvl, _ in rep["flags"]}
    if "RED" in levels:
        return "RED"
    if "YELLOW" in levels:
        return "YELLOW"
    return "PASS"


def render(rep):
    v = verdict(rep)
    icon = {"PASS": "✅ PASS", "YELLOW": "⚠️  YELLOW", "RED": "⛔ RED", "ERROR": "❓ ERROR"}[v]
    lines = [f"{icon}  {rep['repo']}"]
    if rep.get("error"):
        lines.append(f"    ! {rep['error']}")
        return "\n".join(lines)
    bits = []
    if rep.get("stars") is not None:
        bits.append(f"★{rep['stars']}")
    if rep.get("license"):
        bits.append(rep["license"])
    if rep.get("stale_days") is not None:
        bits.append(f"last push {rep['stale_days']}d ago")
    if rep.get("latest_release"):
        bits.append(f"release {rep['latest_release']}")
    if rep.get("requires_python"):
        bits.append(f"py{rep['requires_python']}")
    if bits:
        lines.append("    " + " | ".join(bits))
    if rep.get("description"):
        lines.append(f"    {rep['description'][:110]}")
    for lvl, msg in rep["flags"]:
        lines.append(f"    [{lvl}] {msg}")
    for msg in rep.get("notes", []):
        lines.append(f"    · {msg}")
    if rep.get("entrypoints"):
        lines.append(f"    entry points: {', '.join(rep['entrypoints'][:4])}")
    if rep.get("clone_path"):
        lines.append(f"    clone kept at: {rep['clone_path']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="hard-gate feasibility check for open-source candidates")
    ap.add_argument("repos", nargs="+", help="owner/name or GitHub URL")
    ap.add_argument("--clone", action="store_true", help="shallow-clone for static checks (dependencies / entry points / GUI)")
    ap.add_argument("--keep", action="store_true", help="with --clone: keep the clone for reading code afterwards")
    ap.add_argument("--target-python", default=f"{sys.version_info[0]}.{sys.version_info[1]}",
                    help="Python version it must run on (default: the interpreter running this script)")
    ap.add_argument("--json", action="store_true", help="output JSON")
    args = ap.parse_args()

    reports = []
    for raw in args.repos:
        try:
            slug = parse_slug(raw)
        except ValueError as e:
            reports.append({"repo": raw, "error": str(e), "flags": []})
            continue
        reports.append(build_report(slug, args.target_python, args.clone, args.keep))

    if args.json:
        for r in reports:
            r["verdict"] = verdict(r)
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    else:
        for r in reports:
            print(render(r))
            print()
        tally = {}
        for r in reports:
            tally[verdict(r)] = tally.get(verdict(r), 0) + 1
        print("summary: " + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
        if not args.clone:
            print("note: without --clone only API metadata was checked; dependency / entry point / GUI gates were skipped.")

    return 1 if any(verdict(r) == "ERROR" for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
