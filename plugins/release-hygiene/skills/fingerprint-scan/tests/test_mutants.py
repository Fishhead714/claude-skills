#!/usr/bin/env python3
# fingerprint-scan: ignore-file (mutation fixtures deliberately contain the synthetic example values)
"""Mutation tests: a checker must be able to see what it is meant to catch.

1. A clean synthetic baseline tree must produce zero HIGH/MEDIUM findings.
2. Each mutant plants exactly one fingerprint into a copy of the baseline; the
   expected detector must report it at (or above) the expected severity ("killed").
3. Isolation: with that detector disabled, the same mutant must survive, i.e. it
   was not killed by some other detector by accident. Otherwise the detector
   under test is not proven to be the one doing the work.
4. Controls: look-alikes that must NOT be flagged at MEDIUM or above.

Run:  python tests/test_mutants.py      (prints the killed/survived table)
  or  python -m unittest discover -s tests
"""
from __future__ import annotations

import json
import py_compile
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(PKG / "scripts"))
import fingerprint_scan as fs  # noqa: E402

LEDGER = PKG / "examples" / "ledger.example.txt"
FENCES = PKG / "examples" / "fences.example.json"
SEP = "/"
HOME_PATH = SEP.join(["", "home", "alice", "work", "site.py"])   # built at runtime: this file stays clean
MAC_PATH = SEP.join(["", "Users", "bob", "data", "run.csv"])
WIN_PATH = "\\".join(["C:", "Users", "carol", "proj", "mod.py"])

# --------------------------------------------------------------------------- baseline
BASELINE = {
    "README.md": (
        "# toy-geometry\n\nSmall helpers for boxes and grids. Default spacing is 50 m and the grid step is 10.\n"
        "Install into your own environment, e.g. /home/<user>/venv or " + SEP.join(["", "home", "user", "project"]) + ".\n"
        "Demo coordinates live in declared synthetic zones only.\n"),
    "src/geometry.py": (
        '"""Toy geometry helpers used as a clean baseline."""\n'
        "import math\n\n"
        "DEFAULT_SPACING = 50.0\nGRID_STEP = 10\nTOLERANCE = 1e-6\nMAX_RETRIES = 23\n\n\n"
        "def area_of_box(width, height):\n    return width * height\n\n\n"
        "def scale(values, factor=1.5):\n    return [v * factor for v in values]\n\n\n"
        "def to_percent(x):\n    return round(100 * x, 2)\n\n\n"
        "def circle_area(r):\n    return math.pi * r ** 2\n"),
    "src/demo_points.py": (
        "# synthetic demo points (inside the declared mid-ocean demo zone)\n"
        "POINTS = [(-5.2500, -144.0000), (-5.5000, -146.0000)]\n"
        "ORIGIN = (0.2500, -0.5000)\n"),
    "tests/test_geometry.py": (
        "from geometry import area_of_box, scale\n\n\n"
        "def test_area():\n    assert area_of_box(20, 40) == 800\n    assert area_of_box(0.5, 4) == 2.0\n\n\n"
        "def test_scale():\n    assert scale([2, 4]) == [3.0, 6.0]\n\n\n"
        "def test_null_island_points():\n    pts = [(0.1234, 0.5678), (-0.4321, 0.8765)]\n    assert len(pts) == 2\n"),
    "examples/config.json": json.dumps({"grid_step": 10, "spacing_m": 50,
                                        "origin": {"lat": 0.25, "lon": -0.5},
                                        "utm_origin": [500200, 5000400]}, indent=2) + "\n",
    "examples/sample.csv": "id,value\n1,10\n2,20\n3,40\n",
    "notebooks/clean.ipynb": json.dumps({"cells": [{"cell_type": "code", "execution_count": None, "metadata": {},
                                                    "outputs": [], "source": ["print(1 + 1)"]}],
                                         "metadata": {}, "nbformat": 4, "nbformat_minor": 5}) + "\n",
}

BUILD_PATH = SEP.join(["", "srv", "build", "projx", "b.py"])
LONG_BUILD_PATH = SEP.join(["", "srv", "build", "p" * 40, "module_name.py"])
assert 65 <= len(LONG_BUILD_PATH) <= 90, len(LONG_BUILD_PATH)


def real_pyc(dfile: str) -> bytes:
    """Genuine py_compile output whose co_filename is the given absolute path."""
    with tempfile.TemporaryDirectory() as td:
        src, out = Path(td) / "m.py", Path(td) / "m.pyc"
        src.write_text("X = 1\n", encoding="utf-8")
        py_compile.compile(str(src), cfile=str(out), dfile=dfile, doraise=True)
        return out.read_bytes()


PYC_HEADER = b"\x6f\x0d\x0d\x0a\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xe3\x00\x00\x00"

# --------------------------------------------------------------------------- mutants
# (name, detector, minimum severity, {path: content}); content is appended to an existing file or creates it
MUTANTS = [
    ("ledger_exact_as_written", "ledger", "high", {"src/site.py": "SITE_AREA_KM2 = 4.37\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_unit_converted_m2", "ledger", "high", {"src/site.py": "footprint = 4370000  # m2\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_unit_converted_ha", "ledger", "high", {"docs/notes.md": "The block covers 437 ha.\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_unit_converted_mm", "ledger", "high", {"docs/notes.md": "Content box is 217 mm wide.\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_unit_converted_inch", "ledger", "high", {"docs/notes.md": "About 8.54 in across.\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_thousands_separator", "ledger", "high", {"docs/notes.md": "Footprint: 4,370,000 m² in total.\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_standalone_after_identifier", "ledger", "high", {"src/site.py": "SITE_AREA_M2 = 4370000\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_scientific_no_context", "ledger", "medium", {"src/site.py": "k = 4.37e6\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_rounded_to_integer", "ledger", "medium", {"src/layout.py": "WIDTH_CM = 22\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_rounded_one_decimal", "ledger", "medium", {"docs/notes.md": "roughly 4.4 km2 of land\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_rounded_small_int", "ledger", "medium", {"src/layout.py": "GAP = 11  # cm\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_weak_with_context", "ledger", "medium", {"docs/notes.md": "Tested on a layout of 23 units.\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_temperature_F", "ledger", "medium", {"src/process.py": "CURE_F = 343.4  # degF\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_percent_as_fraction", "ledger", "medium", {"src/process.py": "fill = 0.64\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_sequence", "ledger", "high", {"tests/test_profile.py": "SHARES = [8.2, 6.5, 5.3, 2.9]\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_copy_in_tree", "ledger", "high", {"private/notes.txt": LEDGER.read_text(encoding="utf-8")}),
    # the ledger actually used for the scan sits inside the tree (content matches are ignored for this row
    # by giving the file no numbers; the finding must come from the path check)
    ("ledger_path_inside_tree", "ledger", "high", {"private/ledger.txt": "# empty on purpose\n",
                                                   "__ledger__": "private/ledger.txt"}),
    # an in-tree pragma must never silence a private-fact match
    ("ledger_in_ignore_file_test", "ledger", "high",
     {"tests/test_area.py": "# fingerprint-scan: ignore-file (synthetic)\nAREA_KM2 = 4.37\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("ledger_line_pragma_without_reason", "ledger", "high", {"src/site.py": "AREA_KM2 = 4.37  # fingerprint-scan: ignore\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("derived_ratio", "derived", "medium", {"src/layout.py": "ASPECT = 1.212\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("derived_percent", "derived", "medium", {"src/layout.py": "aspect_pct = 121.2\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("derived_base_cooccurrence", "derived", "medium", {"src/cable.py": "CABLE_LENGTH = 62.0\nCABLE_TURNS = 1.319\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("derived_base_percent", "derived", "medium", {"src/cable.py": "CABLE_LENGTH = 62.0\nCABLE_PCT = 131.9\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("coords_fenced_latlon", "coords", "high", {"src/sites.py": "SITE = (-31.1537, -20.5118)\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("coords_fenced_lonlat", "coords", "high", {"src/sites.py": "SITE = [-20.5118, -31.1537]\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("coords_fenced_keyed", "coords", "high", {"src/sites.py": "lat = -31.1537\nlon = -20.5118\n"}),
    ("coords_fenced_hemisphere", "coords", "high", {"docs/notes.md": "Located at 31.1537 S, 20.5118 W.\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("coords_fenced_polygon", "coords", "high", {"src/sites.py": "P = (-35.2046, -27.0113)\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("coords_fenced_in_number_run", "coords", "high",
     {"data/rows.csv": "7.5, 3.25, -31.1537, -20.5118, 12.75, 0.5\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("coords_fenced_in_ignore_file", "coords", "high",
     {"tests/test_sites.py": "# fingerprint-scan: ignore-file (synthetic)\nSITE = (-31.1537, -20.5118)\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("coords_unfenced_precise", "coords", "medium", {"src/sites.py": "P = (-47.3821, -38.6154)\n"}),
    ("coords_utm_fenced", "coords", "high", {"src/sites.py": "XY = (515432.7, 4273310.2)\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("coords_utm_keyed_single", "coords", "medium", {"src/sites.py": "easting = 614927\n"}),
    ("irregular_in_test", "irregular", "low", {"tests/test_fixture.py": "expected = 7391.46\n"}),
    # REAL bytecode from py_compile (co_filename follows a marshal length prefix): these are the ones that count
    ("artifact_pyc_home_path", "artifacts", "high", {"src/__pycache__/site.cpython-311.pyc": real_pyc(HOME_PATH)}),
    ("artifact_pyc_windows_path", "artifacts", "high", {"src/__pycache__/mod.cpython-311.pyc": real_pyc(WIN_PATH)}),
    ("artifact_pyc_build_path", "artifacts", "high", {"src/__pycache__/b.cpython-311.pyc": real_pyc(BUILD_PATH)}),
    # a path length of 65-90 makes the 1-byte length prefix an ASCII letter (a "word" character)
    ("artifact_pyc_build_path_letter_prefix", "artifacts", "high",
     {"src/__pycache__/c.cpython-311.pyc": real_pyc(LONG_BUILD_PATH)}),
    ("artifact_pyc_home_path_synthetic_bytes", "artifacts", "high",
     {"src/__pycache__/s.cpython-311.pyc": PYC_HEADER + HOME_PATH.encode() + b"\x00"}),
    ("artifact_text_abs_path_bare_pragma", "artifacts", "high",
     {"src/p.py": 'P = "' + SEP.join(["", "home", "zed", "y"]) + '"  # fingerprint-scan: ignore\n'}),
    ("artifact_pycache_dir", "artifacts", "medium", {"src/__pycache__/x.cpython-311.pyc": PYC_HEADER}),
    ("artifact_ds_store", "artifacts", "medium", {".DS_Store": b"\x00\x00\x00\x01Bud1\x00"}),
    ("artifact_notebook_outputs", "artifacts", "medium",
     {"notebooks/run.ipynb": json.dumps({"cells": [{"cell_type": "code", "execution_count": 3, "metadata": {},
                                                    "outputs": [{"output_type": "stream", "text": ["ok"]}],
                                                    "source": ["print('ok')"]}], "nbformat": 4})}),
    ("artifact_text_abs_path", "artifacts", "high", {"docs/notes.md": f"see {MAC_PATH} for the raw run\n"}),
]

# look-alikes that must stay below MEDIUM (false-positive guards)
CONTROLS = [
    ("control_weak_count_no_context", {"src/misc.py": "BATCH = 23\n"}),  # fingerprint-scan: ignore (synthetic test value)
    ("control_rounded_no_context", {"src/misc.py": "PADDING = 22\n"}),
    ("control_synthetic_zone_coord", {"src/misc.py": "DEMO = (-5.4321, -147.1234)\n"}),
    ("control_placeholder_path", {"docs/setup.md": "Clone into /home/<user>/src or " + SEP.join(["", "Users", "you", "src"]) + ".\n"}),
    ("control_version_and_date", {"CHANGELOG.md": "## 4.37.0 - 2026-01-15\nversion 4.37.1\n"}),
    ("control_pragma", {"src/misc.py": "LEGACY = 4.37  # fingerprint-scan: ignore (public spec value)\n"}),
    ("control_round_utm_in_synthetic", {"src/misc.py": "GRID0 = (500600, 5000800)\n"}),
    ("control_constants_table_not_coords",
     {"src/consts.py": "KNOWN = (1.609344, 9.80665, 0.0174533, 57.2958, 3.28084, 0.621371)\n"
                       "PAIR = (1.609344, 9.80665)\n"}),
    ("control_long_number_row_not_coords", {"data/row.csv": "41.2468, 45.6789, 23.4567, 56.7891, 34.5678\n"}),
    ("control_number_inside_identifier",
     {"docs/build.md": "Remove src/__pycache__/site.cpython-311.pyc and py311 wheels; use utf-8 and sha256.\n"}),
    ("control_version_strings", {"ci.yml": "runs-on: ubuntu-22.04\nversion: v2.3.1\narch: x86_64\n"}),
    ("control_metres_per_degree_not_utm", {"src/consts.py": "M_PER_DEG = (111320.0, 111319.49)\n"}),
    # ignore-file silences heuristics only: an unfenced coordinate and an irregular number in a test file
    ("control_ignore_file_pragma", {"tests/test_demo.py": "# fingerprint-scan: ignore-file (synthetic demo)\n"
                                                         "P = (-47.3821, -38.6154)\nexpected = 7391.46\n"}),
]


# --------------------------------------------------------------------------- harness
def write_tree(root: Path, files: dict):
    for rel, content in files.items():
        if rel == "__ledger__":
            continue
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        elif p.exists():
            with p.open("a", encoding="utf-8") as fh:
                fh.write(content)
        else:
            p.write_text(content, encoding="utf-8")


def scan(root: Path, disabled=(), ledger_path: Path = LEDGER):
    led = fs.load_ledger(LEDGER)
    led.path = ledger_path      # facts always come from the example ledger; the path is what the tree check sees
    led.synthetic_example = False   # behave as a real (unmarked) ledger
    fen = fs.load_fences(FENCES)
    findings, _ = fs.scan_tree(root, led, fen, disabled)
    return findings


def key(f):
    return (f.path, f.line, f.detector, f.value, f.detail)


def new_findings(base, mutant):
    seen = {key(f) for f in base}
    return [f for f in mutant if key(f) not in seen]


def at_least(fs_, sev, detector=None):
    return [f for f in fs_ if fs.SEV_RANK[f.severity] >= fs.SEV_RANK[sev]
            and (detector is None or f.detector == detector)]


def run_all(verbose=True):
    problems = []
    rows = []
    with tempfile.TemporaryDirectory() as td:
        base_dir = Path(td) / "baseline"
        write_tree(base_dir, BASELINE)
        base = scan(base_dir)
        dirty = at_least(base, "medium")
        if dirty:
            problems.append("baseline is dirty: " + "; ".join(f"{f.path}:{f.line} {f.detector} {f.value} {f.detail}"
                                                              for f in dirty))
        base_by_det = {d: scan(base_dir, disabled=[d]) for d in fs.DETECTORS}

        for i, (name, det, sev, files) in enumerate(MUTANTS):
            mdir = Path(td) / f"m{i}"
            shutil.copytree(base_dir, mdir)
            write_tree(mdir, files)
            lp = mdir / files["__ledger__"] if "__ledger__" in files else LEDGER
            got = new_findings(base, scan(mdir, ledger_path=lp))
            killed = bool(at_least(got, sev, det))
            others = sorted({f.detector for f in at_least(got, sev) if f.detector != det})
            got_wo = new_findings(base_by_det[det], scan(mdir, disabled=[det], ledger_path=lp))
            isolated = not at_least(got_wo, sev)
            rows.append((name, det, sev, "killed" if killed else "SURVIVED",
                         "yes" if isolated else "NO (" + ",".join(sorted({f.detector for f in at_least(got_wo, sev)})) + ")"))
            if not killed:
                problems.append(f"mutant survived: {name} (got: {[(f.detector, f.severity, f.value) for f in got]})")
            if not isolated:
                problems.append(f"mutant {name} is also killed by {others} -> detector '{det}' not isolated")

        for i, (name, files) in enumerate(CONTROLS):
            cdir = Path(td) / f"c{i}"
            shutil.copytree(base_dir, cdir)
            write_tree(cdir, files)
            got = at_least(new_findings(base, scan(cdir)), "medium")
            rows.append((name, "-", "<medium", "clean" if not got else "FLAGGED", "-"))
            if got:
                problems.append(f"control flagged: {name}: {[(f.detector, f.severity, f.value, f.detail) for f in got]}")

    if verbose:
        w = max(len(r[0]) for r in rows)
        print(f"baseline: {len(base)} finding(s) total, {len(dirty)} at MEDIUM+")
        print(f"{'mutant/control'.ljust(w)}  {'detector':9}  {'min':7}  {'result':9}  isolated")
        for r in rows:
            print(f"{r[0].ljust(w)}  {r[1]:9}  {r[2]:7}  {r[3]:9}  {r[4]}")
        n_m = len(MUTANTS)
        n_k = sum(1 for r in rows[:n_m] if r[3] == "killed")
        print(f"\nkilled {n_k}/{n_m}; controls clean {sum(1 for r in rows[n_m:] if r[3] == 'clean')}/{len(CONTROLS)}")
        for p in problems:
            print("PROBLEM:", p)
    return problems


def cli(*args):
    return subprocess.run([sys.executable, str(PKG / "scripts" / "fingerprint_scan.py"), *map(str, args)],
                          capture_output=True, text=True, timeout=120)


class MutantTests(unittest.TestCase):
    def test_mutants_baseline_isolation_controls(self):
        problems = run_all(verbose=False)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "t"
            write_tree(root, BASELINE)
            r = cli(root, "--ledger", LEDGER, "--fences", FENCES)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            write_tree(root, {"src/site.py": "SITE_AREA_KM2 = 4.37\n"})  # fingerprint-scan: ignore (synthetic test value)
            r = cli(root, "--ledger", LEDGER, "--fences", FENCES, "--format", "json")
            self.assertEqual(r.returncode, 1, r.stderr)
            data = json.loads(r.stdout)
            self.assertTrue(any(f["detector"] == "ledger" and f["severity"] == "high" for f in data["findings"]))
            r = cli(root, "--ledger", LEDGER, "--fail-on", "high", "--disable", "ledger")
            self.assertEqual(r.returncode, 0, r.stdout)
            bad = Path(td) / "bad.txt"
            bad.write_text("this is not a ledger line\n", encoding="utf-8")
            r = cli(root, "--ledger", bad)
            self.assertEqual(r.returncode, 2)
            r = cli(root)   # no ledger: must warn that ledger detectors are off
            self.assertIn("ledger", r.stderr.lower())
            self.assertIn("not evidence", r.stderr.lower())


def main():
    problems = run_all(verbose=True)
    suite = unittest.TestSuite([MutantTests("test_cli_exit_codes")])
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if not problems and res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
