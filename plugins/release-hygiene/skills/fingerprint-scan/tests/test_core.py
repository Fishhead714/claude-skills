#!/usr/bin/env python3
# fingerprint-scan: ignore-file (mutation fixtures deliberately contain the synthetic example values)
"""Unit tests for parsing, units, fences, performance bounds, and a sabotage check of the mutant harness."""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))
import fingerprint_scan as fs  # noqa: E402


def lits(s):
    return [(l.raw, l.value, l.sig) for l in fs.extract_literals(s, 1)]


class LiteralTests(unittest.TestCase):
    def test_forms(self):
        self.assertIn(("4.37e6", 4.37e6, 3), lits("x = 4.37e6"))  # fingerprint-scan: ignore (synthetic test value)
        self.assertIn(("-12.5", -12.5, 3), lits("y=-12.5;"))
        self.assertIn(("4,370,000", 4370000.0, 3), lits("total 4,370,000 m2"))  # fingerprint-scan: ignore (synthetic test value)
        self.assertIn(("4_370_000", 4370000.0, 3), lits("N = 4_370_000"))  # fingerprint-scan: ignore (synthetic test value)
        self.assertIn((".75", 0.75, 2), lits("f(.75)"))

    def test_not_numbers(self):
        self.assertEqual(lits("version 1.2.3"), [])
        self.assertTrue(all(l.glued for l in fs.extract_literals("abc123 x2 py311 utf-8 x86_64 abc-123", 1)))
        self.assertEqual([l.raw for l in fs.extract_literals("v2.3.1 1.2.3.4", 1)], [])

    def test_identifier_numbers(self):
        """A number inside an identifier is at most LOW for the ledger and invisible to heuristics."""
        led = fs.load_ledger(HERE.parent / "examples" / "ledger.example.txt")
        sc = fs.Scanner(led, fs.load_fences(HERE.parent / "examples" / "fences.example.json"))
        got = sc.scan_text("tests/t.py", "p = 'src/__pycache__/site.cpython-311.pyc'\n")
        self.assertTrue(got and all(f.severity == "low" and "inside identifier" in f.detail for f in got), got)
        got = sc.scan_text("tests/t.py", "site_area_437 = True\n")  # fingerprint-scan: ignore (synthetic test value)
        self.assertTrue(any(f.detector == "ledger" and f.severity == "low" for f in got), "kept as LOW, not dropped")
        self.assertEqual(sc.scan_text("ci.yml", "runs-on: ubuntu-22.04\nversion: v2.3.1\n"), [])
        got = sc.scan_text("ci.yml", "image: ubuntu-22.04, 13.2456\n")
        self.assertFalse(any(f.detector == "coords" for f in got), "identifier number is not half of a coordinate")

    def test_precision(self):
        (l,) = fs.extract_literals("4400000", 1)
        self.assertEqual(l.sig, 2)
        self.assertAlmostEqual(l.half, 50000)
        (l,) = fs.extract_literals("4.40", 1)
        self.assertEqual(l.sig, 3)
        self.assertAlmostEqual(l.half, 0.005)


class UnitTests(unittest.TestCase):
    def test_canon(self):
        for a, b in [("km²", "km2"), ("sq km", "km2"), ("Hectares", "ha"), ("°C", "c"), ("percent", "%"),
                     ("", "count"), ("MW", "mw"), ("sqft", "ft2")]:
            self.assertEqual(fs.canon_unit(a), b, a)

    def test_temperature(self):
        conv = {u: v for u, v, _ in fs.convert_all(20.0, "c")}
        self.assertAlmostEqual(conv["f"], 68.0)
        self.assertAlmostEqual(conv["k"], 293.15)

    def test_area(self):
        conv = {u: v for u, v, _ in fs.convert_all(2.0, "km2")}
        self.assertAlmostEqual(conv["ha"], 200.0)
        self.assertAlmostEqual(conv["m2"], 2e6)


class LedgerTests(unittest.TestCase):
    def test_text_and_json_agree(self):
        with tempfile.TemporaryDirectory() as td:
            t = Path(td) / "l.txt"
            t.write_text("a_len = 31.62 cm context=foo tol=1%\nb = 56 weak\nderive a_len / b\n"
                         "seq = [1.1, 2.2, 3.3]\n", encoding="utf-8")
            j = Path(td) / "l.json"
            j.write_text(json.dumps({"facts": [{"name": "a_len", "value": 31.62, "unit": "cm", "context": ["foo"],
                                                "tol": "1%"}, {"name": "b", "value": 56, "flags": ["weak"]}],
                                     "derive": [{"a": "a_len", "op": "/", "b": "b"}],
                                     "sequences": [{"name": "seq", "values": [1.1, 2.2, 3.3]}]}), encoding="utf-8")
            lt, lj = fs.load_ledger(t), fs.load_ledger(j)
            for L in (lt, lj):
                self.assertEqual(L.facts["a_len"].unit, "cm")
                self.assertAlmostEqual(L.facts["a_len"].tol, 0.01)
                self.assertIn("foo", L.facts["a_len"].keywords)
                self.assertTrue(L.facts["b"].weak)
                self.assertFalse(L.facts["a_len"].weak)
                self.assertEqual(len(L.derives), 1)
                self.assertEqual(L.sequences[0].min_run, 3)

    def test_bad_lines_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "l.txt"
            for bad in ("just words\n", "x = 1 cm extra junk\n", "derive a / b\n"):
                p.write_text(bad, encoding="utf-8")
                with self.assertRaises(SystemExit):
                    fs.load_ledger(p)


class FenceTests(unittest.TestCase):
    def test_geojson(self):
        gj = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"name": "sq", "kind": "private"},
             "geometry": {"type": "Polygon", "coordinates": [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]]}},
            {"type": "Feature", "properties": {"name": "demo", "kind": "synthetic"},
             "geometry": {"type": "MultiPolygon",
                          "coordinates": [[[[20, 20], [21, 20], [21, 21], [20, 20]]]]}},
            {"type": "Feature", "properties": {"name": "grid", "kind": "private",
                                               "utm": {"easting": [300000, 301000], "northing": [900000, 901000]}},
             "geometry": None}]}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "f.geojson"
            p.write_text(json.dumps(gj), encoding="utf-8")
            f = fs.load_fences(p)
        self.assertEqual(fs.zone_hit(10.5, 10.5, f["private"]), "sq")
        self.assertIsNone(fs.zone_hit(12.0, 10.5, f["private"]))
        self.assertEqual(fs.zone_hit(20.2, 20.7, f["synthetic"]), "demo")
        self.assertEqual(f["private_utm"][0]["name"], "grid")


class FenceValidationTests(unittest.TestCase):
    def test_malformed_zones_rejected(self):
        bad = [
            {"private": [{"name": "empty"}]},
            {"private": [{"name": "flipped", "bbox": [10, 5, 9, 6]}]},
            {"synthetic": [{"name": "flipped-lat", "bbox": [1, 6, 2, 5]}]},
            {"private_utm": [{"name": "half", "easting": [100000, 200000]}]},
            {"private_utm": [{"name": "rev", "easting": [2, 1], "northing": [1, 2]}]},
            {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"kind": "private"},
                                                        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]}}]},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "f.json"
            for b in bad:
                p.write_text(json.dumps(b), encoding="utf-8")
                with self.assertRaises(SystemExit, msg=b):
                    fs.load_fences(p)

    def test_cli_exit_2_on_bad_fence(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "f.json"
            p.write_text(json.dumps({"private": [{"name": "empty"}]}), encoding="utf-8")
            r = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "fingerprint_scan.py"), td,
                                "--fences", str(p)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("neither bbox nor polygon", r.stderr)


class PatternTests(unittest.TestCase):
    def test_patterned(self):
        for d in ("123456", "654321", "1212", "5000", "777"):
            self.assertTrue(fs.is_patterned(d), d)
        for d in ("739146", "5172"):
            self.assertFalse(fs.is_patterned(d), d)

    def test_measured(self):
        def m(s):
            (l,) = fs.extract_literals(s, 1)
            return fs.looks_measured(l)
        self.assertTrue(m("7391.46"))
        for s in ("3.14159", "2024", "0.3048", "1000", "12345", "0.001", "9.81", "500200"):
            self.assertFalse(m(s), s)


class PerformanceTests(unittest.TestCase):
    def test_pathological_lines_are_fast(self):
        """Every regex has bounded repetition; a megabyte of adversarial text must not stall the scan."""
        led = fs.load_ledger(HERE.parent / "examples" / "ledger.example.txt")
        sc = fs.Scanner(led, fs.load_fences(HERE.parent / "examples" / "fences.example.json"))
        nasty = ["a" * 1_000_000, "1" * 1_000_000, ("1." * 300_000), ("45.6789 " * 100_000),
                 "lat=" + "9" * 500_000, ("1,234," * 150_000)]
        t0 = time.time()
        for s in nasty:
            sc.scan_text("tests/x.py", s)
        self.assertLess(time.time() - t0, 120, "scan too slow on adversarial input")

    def test_long_line_is_scanned_to_the_end(self):
        """Minified files are one long line: a fingerprint at the far end must still be found."""
        led = fs.load_ledger(HERE.parent / "examples" / "ledger.example.txt")
        sc = fs.Scanner(led, fs.load_fences(HERE.parent / "examples" / "fences.example.json"))
        filler = ", ".join(["0.5"] * 60_000)
        for tail in ("[-31.1537, -20.5118]", "\"area_m2\": 4370000"):  # fingerprint-scan: ignore (synthetic test value)
            got = sc.scan_text("data/min.json", "[" + filler + ", " + tail + "]")
            self.assertTrue(any(f.severity == "high" and f.line == 1 for f in got), (tail, got[:3]))
        # a pair cut exactly at a segment boundary is still seen whole thanks to the overlap
        for pad in range(0, 40, 3):
            line = "x" * (fs.MAX_LINE_CHARS - 12 + pad) + " (-31.1537, -20.5118) " + "y" * 5000  # fingerprint-scan: ignore (synthetic test value)
            got = sc.scan_text("a.txt", line)
            self.assertTrue(any(f.detector == "coords" and f.severity == "high" for f in got), pad)


class IgnoreFileTests(unittest.TestCase):
    def test_file_pragma_is_reported_and_bounded(self):
        led = fs.load_ledger(HERE.parent / "examples" / "ledger.example.txt")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.md").write_text("<!-- fingerprint-scan: ignore-file (demo) -->\nArea 4.37 km2\n"  # fingerprint-scan: ignore (synthetic test value)
                                       "P = (-47.3821, -38.6154)\n", encoding="utf-8")
            (root / "b.md").write_text("\n" * 12 + "<!-- fingerprint-scan: ignore-file -->\nP = (-47.3821, -38.6154)\n",
                                       encoding="utf-8")
            found, stats = fs.scan_tree(root, led, None)
        self.assertIn("a.md (ignore-file pragma: heuristics only)", stats["ignored_files"])
        a = [f for f in found if f.path == "a.md"]
        self.assertTrue(any(f.detector == "ledger" and f.severity == "high" for f in a), "ledger hit must survive")
        self.assertFalse(any(f.detector == "coords" for f in a), "unfenced coordinate is a heuristic: silenced")
        self.assertTrue(any(f.path == "b.md" and f.detector == "coords" and f.severity == "medium" for f in found),
                        "pragma after line 10 must not apply")

    def test_line_pragma_on_private_fact(self):
        led = fs.load_ledger(HERE.parent / "examples" / "ledger.example.txt")
        sc = fs.Scanner(led, None)
        got = sc.scan_text("s.py", "A = 4.37  # fingerprint-scan: ignore (public spec value)\n")
        self.assertEqual([(f.severity, f.detail.startswith("SUPPRESSED (public spec value)")) for f in got],
                         [("low", True)], "with a reason: downgraded but still visible")
        got = sc.scan_text("s.py", "AREA = 4.37  # fingerprint-scan: ignore\n")  # fingerprint-scan: ignore (synthetic test value)
        self.assertTrue(any(f.severity == "high" and "reason" in f.detail for f in got), "no reason: pragma ignored")

    def test_unmarked_ledger_inside_tree_is_high(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lp = root / "ledger.txt"
            lp.write_text("site_area = 4.37 km2\n", encoding="utf-8")  # fingerprint-scan: ignore (synthetic test value)
            found, _ = fs.scan_tree(root, fs.load_ledger(lp), None)
            self.assertTrue(any(f.path == "ledger.txt" and f.severity == "high" for f in found))
            lp.write_text("# fingerprint-scan: synthetic-example\nsite_area = 4.37 km2\n", encoding="utf-8")  # fingerprint-scan: ignore (synthetic test value)
            found, stats = fs.scan_tree(root, fs.load_ledger(lp), None)
            self.assertEqual([f for f in found if f.severity != "low"], [])


class HarnessSabotageTests(unittest.TestCase):
    """The mutant harness itself must be able to fail: break a capability, the matching mutant must survive."""

    def test_breaking_unit_conversion_is_noticed(self):
        import test_mutants as tm
        with mock.patch.object(fs, "convert_all", lambda v, u: [(u, v, 1.0)]):
            problems = tm.run_all(verbose=False)
        self.assertTrue(any("ledger_unit_converted_m2" in p for p in problems), problems)

    def test_breaking_rounding_is_noticed(self):
        import test_mutants as tm
        orig = fs.classify

        def exact_only(lit, c):
            k = orig(lit, c)
            return k if k == "exact" else None
        with mock.patch.object(fs, "classify", exact_only):
            problems = tm.run_all(verbose=False)
        self.assertTrue(any("ledger_rounded_to_integer" in p for p in problems), problems)

    def test_breaking_fences_is_noticed(self):
        import test_mutants as tm
        with mock.patch.object(fs, "zone_hit", lambda lat, lon, zones: None):
            problems = tm.run_all(verbose=False)
        self.assertTrue(any("coords_fenced_latlon" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
