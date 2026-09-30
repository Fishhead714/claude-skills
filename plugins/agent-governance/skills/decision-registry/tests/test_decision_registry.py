#!/usr/bin/env python3
"""Regression suite for decision-registry (stdlib unittest, no network).

Run:  python3 -m unittest discover -s tests -v      (from the package root)
  or: python3 tests/test_decision_registry.py

Every test builds its own temporary registry with init.py and never touches a
real one. Convention: each assertion must be able to reproduce the defect it
guards against -- if someone reverts the fix, the test must turn red again,
otherwise it is decoration. Every ERROR gate has at least one test that makes
audit exit 1, and a clean example registry must exit 0.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG))

import init as INIT  # noqa: E402
import miniyaml  # noqa: E402
import registry as R  # noqa: E402

ENV = {k: v for k, v in os.environ.items() if k != R.ENV_VAR}
ENV["PYTHONDONTWRITEBYTECODE"] = "1"
ENV["PYTHONIOENCODING"] = "utf-8"


def run(script, *args, rd=None, cwd=None, env_rd=True):
    env = dict(ENV)
    if rd is not None and env_rd:
        env[R.ENV_VAR] = str(rd)
    return subprocess.run([sys.executable, str(PKG / script), *map(str, args)],
                          capture_output=True, text=True, env=env,
                          cwd=str(cwd or PKG), timeout=120, encoding="utf-8")


BASE_FIELDS = {
    "domain": "internal",
    "title": "Test card",
    "force": "binding",
    "status": "active",
    "enforcement": "skill",
    "source": "unit test",
    "source_tier": "owner-decision",
    "acquisition": "human_only",
    "asked": "the test author",
    "verified": "2000-01-01",
    "review_by": "2099-01-01",
    "consequence": "test consequence",
    "evidence": "[notes/x.md]",
    "tags": "[]",
}


def raw_card(cid: str, typ: str, scope=("all", "all", "[release]"), drop=(), **over) -> str:
    f = dict(BASE_FIELDS)
    if typ == "stance":
        f.update(force="guidance", confidence="medium", falsified_if="something")
    if typ == "decision":
        f.update(decided_on="2000-01-01", decided_by="tester")
    f.update(over)
    lines = [f"id: {cid}", f"type: {typ}"]
    for k, v in f.items():
        if k in drop:
            continue
        lines.append(f"{k}: {v}")
        if k == "enforcement":
            lines += ["scope:", f"  regions: {scope[0]}", f"  projects: {scope[1]}",
                      f"  activities: {scope[2]}"]
    return "---\n" + "\n".join(lines) + "\n---\n\n## Body\n\ntext\n"


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="decreg_test_")
        self.tmp = Path(self._td.name)
        self.rd = self.tmp / "decision-registry"
        INIT.scaffold(self.rd, with_examples=True)

    def tearDown(self):
        self._td.cleanup()

    # helpers ------------------------------------------------------------
    def put(self, cid, typ, **kw):
        sub = R.SUBDIRS[typ]
        p = self.rd / sub / f"{cid}-test.md"
        p.write_text(raw_card(cid, typ, **kw), encoding="utf-8")
        return p

    def card(self, cid) -> Path:
        hits = sorted(self.rd.rglob(f"{cid}-*.md"))
        self.assertTrue(hits, f"card {cid} not found")
        return hits[0]

    def edit(self, p: Path, pat, repl):
        t = p.read_text(encoding="utf-8")
        t2 = re.sub(pat, repl, t, flags=re.M)
        self.assertNotEqual(t, t2, f"edit did not apply: {pat} in {p.name}")
        p.write_text(t2, encoding="utf-8")

    def reindex(self):
        r = run("build_index.py", rd=self.rd)
        self.assertEqual(r.returncode, 0, r.stderr)

    def audit(self):
        return run("audit.py", rd=self.rd)

    def assertAuditError(self, code):
        self.reindex()
        a = self.audit()
        self.assertEqual(a.returncode, 1, f"audit should exit 1 for {code}:\n{a.stdout}{a.stderr}")
        self.assertRegex(a.stdout, rf"(?m)^ERROR \[{code}\]", a.stdout)
        self.assertNotIn("Traceback", a.stderr)
        return a

    def fm(self, p: Path) -> dict:
        return R._split_frontmatter(p.read_text(encoding="utf-8"), p)[0]


# ============================================================ baseline
class TestBaseline(Base):
    def test_clean_example_registry_exits_0(self):
        a = self.audit()
        self.assertEqual(a.returncode, 0, a.stdout + a.stderr)
        self.assertIn("Clean.", a.stdout)

    def test_empty_registry_exits_0(self):
        rd2 = self.tmp / "empty" / "decision-registry"
        INIT.scaffold(rd2, with_examples=False)
        a = run("audit.py", rd=rd2)
        self.assertEqual(a.returncode, 0, a.stdout + a.stderr)

    def test_init_refuses_existing_registry(self):
        r = run("init.py", self.rd)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refusing", r.stdout + r.stderr)

    def test_init_creates_layout(self):
        for rel in ("schema.json", "README.md", "INDEX.json", "_templates/constraint.md",
                    "_templates/decision.md", "_templates/stance.md", "constraints",
                    "decisions", "stances", "_inbox/IGNORE.txt"):
            self.assertTrue((self.rd / rel).exists(), rel)

    def test_templates_are_parseable(self):
        for t in (self.rd / "_templates").glob("*.md"):
            R._split_frontmatter(t.read_text(encoding="utf-8"), t)

    def test_check_lists_binding_first(self):
        r = run("check.py", "--activity", "customer-email", rd=self.rd)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(r.stdout.index("C-001"), r.stdout.index("D-001"))

    def test_check_unknown_activity_refused(self):
        r = run("check.py", "--activity", "not-an-activity", rd=self.rd)
        self.assertEqual(r.returncode, 2)

    def test_check_says_no_binding_out_loud(self):
        r = run("check.py", "--activity", "hiring", rd=self.rd)
        self.assertIn("nobody has registered one", r.stdout)


# ============================================================ registry location
class TestResolution(Base):
    def test_no_registry_is_an_error_not_an_empty_list(self):
        # a fresh temp dir that is NOT a sibling of the test registry
        with tempfile.TemporaryDirectory(prefix="decreg_nowhere_") as nowhere:
            r = run("check.py", cwd=nowhere)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("No decision registry found", r.stdout + r.stderr)
        self.assertNotIn("binding (0)", r.stdout)

    def test_walk_up_from_subdirectory(self):
        deep = self.tmp / "a" / "b"
        deep.mkdir(parents=True)
        r = run("check.py", cwd=deep)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(str(self.rd), r.stdout)

    def test_walk_up_from_inside_registry(self):
        r = run("check.py", cwd=self.rd / "constraints")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_env_var(self):
        other = self.tmp / "elsewhere" / "custom-name"
        INIT.scaffold(other, with_examples=False)
        r = run("check.py", rd=other, cwd=self.tmp / "elsewhere")
        self.assertIn("0 cards", r.stdout)

    def test_flag_beats_env(self):
        other = self.tmp / "elsewhere" / "custom-name"
        INIT.scaffold(other, with_examples=False)
        env = dict(ENV, **{R.ENV_VAR: str(self.rd)})
        r = subprocess.run([sys.executable, str(PKG / "check.py"), "--registry", str(other)],
                           capture_output=True, text=True, env=env, cwd=str(PKG), timeout=60)
        self.assertIn("0 cards", r.stdout)

    def test_env_pointing_to_missing_dir_is_error(self):
        r = run("check.py", rd=self.tmp / "missing")
        self.assertNotEqual(r.returncode, 0)

    def test_env_pointing_to_dir_without_schema_is_error(self):
        d = self.tmp / "noschema"
        d.mkdir()
        r = run("check.py", rd=d)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no schema.json", r.stdout + r.stderr)


# ============================================================ one test per ERROR gate
class TestAuditGates(Base):
    def test_E001_missing_required_field(self):
        self.put("C-100", "constraint", drop=("consequence",))
        self.assertAuditError("E001")

    def test_E001_bad_enum(self):
        self.put("C-100", "constraint", force="mandatory")
        self.assertAuditError("E001")

    def test_E002_id_file_mismatch(self):
        p = self.put("C-100", "constraint")
        p.rename(p.with_name("C-999-test.md"))
        self.assertAuditError("E002")

    def test_E002_wrong_directory(self):
        p = self.put("C-100", "constraint")
        p.rename(self.rd / "decisions" / p.name)
        self.assertAuditError("E002")

    def test_E003_inference_cannot_be_binding(self):
        self.put("C-100", "constraint", source_tier="my-inference", force="binding")
        a = self.assertAuditError("E003")
        self.assertIn("C-100", a.stdout)

    def test_E004_binding_cannot_rely_on_retrieval(self):
        self.put("C-100", "constraint", force="binding", enforcement="retrieved")
        self.assertAuditError("E004")

    def test_E005_stance_needs_falsified_if(self):
        self.put("S-100", "stance", drop=("falsified_if",))
        self.assertAuditError("E005")

    def test_E006_supersedes_missing_card(self):
        self.put("D-100", "decision", supersedes="D-404")
        self.assertAuditError("E006")

    def test_E006_superseded_by_but_still_active(self):
        self.put("D-100", "decision", superseded_by="D-001")
        self.assertAuditError("E006")

    def test_E006_new_supersedes_old_but_old_still_active(self):
        self.put("D-100", "decision", supersedes="D-001")
        a = self.assertAuditError("E006")
        self.assertIn("still active", a.stdout)

    def test_E006_list_value_does_not_crash(self):
        self.put("D-100", "decision", supersedes="[C-001, D-001]")
        self.assertAuditError("E006")

    def test_E007_resident_quota(self):
        # C-001 is already resident; 12 more makes 13 > 12
        for i in range(12):
            self.put(f"C-{200 + i}", "constraint", enforcement="resident")
        a = self.assertAuditError("E007")
        self.assertIn("13/12", a.stdout)

    def test_E007_quota_boundary_is_not_an_error(self):
        for i in range(11):
            self.put(f"C-{200 + i}", "constraint", enforcement="resident")
        self.reindex()
        a = self.audit()
        self.assertNotIn("E007", a.stdout)
        self.assertIn("resident 12/12", a.stdout)

    def test_E007_superseded_residents_do_not_count(self):
        for i in range(12):
            self.put(f"C-{200 + i}", "constraint", enforcement="resident", status="retired")
        self.reindex()
        self.assertNotIn("E007", self.audit().stdout)

    def test_E008_stale_index(self):
        self.put("C-100", "constraint")
        a = self.audit()  # no reindex on purpose
        self.assertEqual(a.returncode, 1)
        self.assertIn("[E008]", a.stdout)

    def test_E008_missing_index(self):
        (self.rd / "INDEX.json").unlink()
        a = self.audit()
        self.assertEqual(a.returncode, 1)
        self.assertIn("[E008]", a.stdout)

    def test_E009_acquisition_companion_missing(self):
        self.put("C-100", "constraint", acquisition="public_source")
        self.assertAuditError("E009")

    def test_E010_archive_file_missing_under_existing_tree(self):
        (self.tmp / "archive-tree").mkdir()
        self.put("C-100", "constraint", acquisition="held_copy",
                 archive_ref="archive-tree/gone.pdf", drop=("asked",))
        self.assertAuditError("E010")

    def test_E010_present_file_is_clean(self):
        (self.tmp / "archive-tree").mkdir()
        (self.tmp / "archive-tree" / "here.pdf").write_text("x")
        self.put("C-100", "constraint", acquisition="held_copy",
                 archive_ref="archive-tree/here.pdf", drop=("asked",))
        self.reindex()
        a = self.audit()
        self.assertEqual(a.returncode, 0, a.stdout)

    def test_E011_internal_card_with_external_tier(self):
        self.put("C-100", "constraint", source_tier="law")
        self.assertAuditError("E011")

    def test_E012_external_binding_needs_applicability(self):
        self.put("C-100", "constraint", domain="external", source_tier="regulation")
        self.assertAuditError("E012")

    def test_E013_bad_date(self):
        self.put("C-100", "constraint", review_by="next-year")
        a = self.assertAuditError("E013")
        self.assertIn("C-100", a.stdout)

    def test_E014_scope_all_inside_list(self):
        self.put("C-100", "constraint", scope=("[all]", "all", "[release]"))
        self.assertAuditError("E014")

    def test_E014_nonstandard_activity(self):
        self.put("C-100", "constraint", scope=("all", "all", "[releases]"))
        self.assertAuditError("E014")

    def test_E014_scope_not_a_mapping(self):
        p = self.put("C-100", "constraint")
        t = p.read_text(encoding="utf-8")
        p.write_text(re.sub(r"^scope:\n(  \w+: .*\n){3}", "scope: all\n", t, flags=re.M),
                     encoding="utf-8")
        a = self.audit()
        self.assertEqual(a.returncode, 1)
        self.assertIn("E014", a.stdout)
        self.assertIn("C-100", a.stdout)
        self.assertNotIn("Traceback", a.stderr)

    def test_E015_unreadable_card(self):
        p = self.put("C-100", "constraint")
        p.write_text("---\nid: C-100\ntitle: [unclosed\n---\n", encoding="utf-8")
        a = self.audit()
        self.assertEqual(a.returncode, 1)
        self.assertIn("[E015]", a.stdout)
        self.assertIn("C-100", a.stdout)

    def test_warn_only_exits_0(self):
        self.put("C-100", "constraint", review_by="2001-01-01", evidence="[]")
        self.reindex()
        a = self.audit()
        self.assertEqual(a.returncode, 0, a.stdout)
        self.assertIn("W001", a.stdout)
        self.assertIn("W003", a.stdout)

    def test_W002_conflicting_thresholds(self):
        hv = "{trigger_any: [{metric: m, op: '>=', value: 3}]}"
        hv2 = "{trigger_any: [{metric: m, op: '>=', value: 5}]}"
        self.put("C-100", "constraint", hard_value=hv)
        self.put("C-101", "constraint", hard_value=hv2)
        self.reindex()
        a = self.audit()
        self.assertIn("W002", a.stdout)


# ============================================================ add.py
class TestAdd(Base):
    BASE = ["--source", "s", "--source-tier", "owner-decision", "--consequence", "c",
            "--acquisition", "human_only", "--asked", "a"]

    def new(self, typ, title, *extra):
        return run("add.py", "new", typ, "--title", title, *self.BASE, *extra, rd=self.rd)

    def test_new_card_passes_audit(self):
        r = self.new("constraint", "A fresh rule", "--activities", "onboarding")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.card("C-002").name.startswith("C-002-a-fresh-rule"))
        a = self.audit()
        self.assertEqual(a.returncode, 0, a.stdout)

    def test_new_refuses_E003_at_creation(self):
        r = run("add.py", "new", "constraint", "--title", "t", "--source", "s",
                "--source-tier", "my-inference", "--consequence", "c",
                "--acquisition", "human_only", "--asked", "a", rd=self.rd)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("E003", r.stderr)
        self.assertFalse(list(self.rd.glob("constraints/C-002-*")))

    def test_new_refuses_E004_at_creation(self):
        r = self.new("constraint", "t", "--enforcement", "retrieved")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("E004", r.stderr)

    def test_new_stance_requires_falsified_if(self):
        r = self.new("stance", "t")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("falsified-if", r.stderr)

    def test_new_decision_requires_decided_by(self):
        r = self.new("decision", "t")
        self.assertNotEqual(r.returncode, 0)

    def test_new_unknown_activity_refused(self):
        r = self.new("constraint", "t", "--activities", "nope")
        self.assertNotEqual(r.returncode, 0)

    def test_review_interval_follows_source_tier(self):
        r = run("add.py", "new", "stance", "--title", "guess", "--source", "s",
                "--source-tier", "my-inference", "--consequence", "c",
                "--acquisition", "human_only", "--asked", "a", "--falsified-if", "f",
                rd=self.rd)
        self.assertEqual(r.returncode, 0, r.stderr)
        fm = self.fm(self.card("S-002"))
        rb = date.fromisoformat(fm["review_by"])
        months = (rb.year - date.today().year) * 12 + rb.month - date.today().month
        self.assertEqual(months, 3)

    def test_scope_values_are_escaped(self):
        # a value with ` #` once produced unparseable YAML -> the whole registry unreadable
        self.new("constraint", "escape", "--projects", "alpha #1")
        r = run("check.py", rd=self.rd)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.fm(self.card("C-002"))["scope"]["projects"], ["alpha #1"])

    def test_scope_comma_not_split(self):
        self.new("constraint", "comma", "--projects", "a,b")
        self.assertEqual(self.fm(self.card("C-002"))["scope"]["projects"], ["a,b"])

    def test_verify_rewrites_multiline_value_cleanly(self):
        p = self.put("C-100", "constraint", asked="first line\n  second line must not survive")
        self.reindex()
        r = run("add.py", "verify", "C-100", "--asked", "rewritten", rd=self.rd)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.fm(p)["asked"], "rewritten")

    def test_bad_decided_on_refused_before_write(self):
        r = self.new("decision", "date test", "--decided-by", "me", "--decided-on", "2001-13-45")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(list(self.rd.glob("decisions/D-002-*")))
        self.assertEqual(self.audit().returncode, 0)

    def test_verify_reruns_gates(self):
        r = run("add.py", "verify", "C-001", "--source-tier", "my-inference", rd=self.rd)
        self.assertNotEqual(r.returncode, 0, "verify turned a binding card into my-inference")
        self.assertIn("E003", r.stderr)

    def test_verify_acquisition_upgrade_drops_old_companion(self):
        (self.tmp / "archive-tree").mkdir()
        (self.tmp / "archive-tree" / "doc.pdf").write_text("x")
        r = run("add.py", "verify", "D-001", "--acquisition", "held_copy",
                "--archive-ref", "archive-tree/doc.pdf", rd=self.rd)
        self.assertEqual(r.returncode, 0, r.stderr)
        fm = self.fm(self.card("D-001"))
        self.assertNotIn("asked", fm)
        self.assertEqual(fm["archive_ref"], "archive-tree/doc.pdf")
        self.assertEqual(self.audit().returncode, 0)

    def test_verify_unclosed_frontmatter_exits_cleanly(self):
        p = self.card("C-001")
        t = p.read_text(encoding="utf-8")
        # break the *closing* delimiter
        lines = t.split("\n")
        end = next(i for i in range(1, len(lines)) if lines[i] == "---")
        lines[end] = ""
        p.write_text("\n".join(lines), encoding="utf-8")
        r = run("add.py", "verify", "C-001", "--note", "x", rd=self.rd)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("C-001", r.stderr)

    def test_bad_confidence_refused(self):
        # YAML 1.1 would have turned `no` into False
        r = self.new("stance", "conf", "--falsified-if", "f", "--confidence", "no")
        self.assertNotEqual(r.returncode, 0)

    def test_supersede_links_both_ways(self):
        r = run("add.py", "supersede", "D-001", "--title", "All deliverables use SI and ISO dates",
                *self.BASE, "--decided-by", "leads", rd=self.rd)
        self.assertEqual(r.returncode, 0, r.stderr)
        old, new = self.fm(self.card("D-001")), self.fm(self.card("D-002"))
        self.assertEqual(old["status"], "superseded")
        self.assertEqual(old["superseded_by"], "D-002")
        self.assertEqual(new["supersedes"], "D-001")
        a = self.audit()
        self.assertEqual(a.returncode, 0, a.stdout)
        c = run("check.py", rd=self.rd)
        self.assertIn("no longer in force", c.stdout)

    def test_supersede_of_superseded_card_refused(self):
        run("add.py", "supersede", "D-001", "--title", "v2", *self.BASE, "--decided-by", "x",
            rd=self.rd)
        r = run("add.py", "supersede", "D-001", "--title", "v3", *self.BASE, "--decided-by", "x",
                rd=self.rd)
        self.assertNotEqual(r.returncode, 0)

    def _supersede_in_process(self, fail_on_call):
        import add as ADD
        from unittest import mock
        real = os.replace
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] == fail_on_call:
                raise OSError("simulated failure")
            return real(src, dst)

        before = self.card("D-001").read_text(encoding="utf-8")
        with mock.patch.object(ADD.os, "replace", flaky), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError):
                ADD.main(["--registry", str(self.rd), "supersede", "D-001", "--title", "new rule",
                          *self.BASE, "--decided-by", "x"])
        self.assertEqual(self.card("D-001").read_text(encoding="utf-8"), before,
                         "old card modified although supersede failed")
        self.assertFalse(list(self.rd.glob("decisions/D-002-*")),
                         "new card left behind while the old one stayed active")
        self.assertFalse(list(self.rd.rglob("*.tmp")), "temp files left behind")

    def test_C11_supersede_rolls_back_when_second_replace_fails(self):
        self._supersede_in_process(fail_on_call=2)

    def test_C11_supersede_clean_when_first_replace_fails(self):
        self._supersede_in_process(fail_on_call=1)


# ============================================================ check.py robustness
class TestCheck(Base):
    def test_unknown_region_is_flagged(self):
        self.put("C-100", "constraint", scope=("[EMEA]", "all", "[release]"))
        self.reindex()
        good = run("check.py", "--region", "EMEA", rd=self.rd)
        bad = run("check.py", "--region", "emea", rd=self.rd)
        self.assertIn("C-100", good.stdout)
        self.assertNotIn("C-100", bad.stdout)
        self.assertIn("never appears", bad.stdout)

    def test_malformed_scope_named_not_traceback(self):
        p = self.put("C-100", "constraint")
        t = p.read_text(encoding="utf-8")
        p.write_text(re.sub(r"^scope:\n(  \w+: .*\n){3}", "scope: all\n", t, flags=re.M),
                     encoding="utf-8")
        r = run("check.py", rd=self.rd)
        self.assertEqual(r.returncode, 3)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("C-100", r.stdout + r.stderr)

    def test_unreadable_card_aborts(self):
        p = self.put("C-100", "constraint")
        p.write_text("no frontmatter here\n", encoding="utf-8")
        r = run("check.py", rd=self.rd)
        self.assertEqual(r.returncode, 3)
        self.assertIn("C-100", r.stderr)

    def test_bare_date_does_not_break_index(self):
        self.put("C-100", "constraint", asked="2000-01-01")
        r = run("build_index.py", rd=self.rd)
        self.assertEqual(r.returncode, 0, r.stderr)


# ============================================================ frontmatter splitting
class TestFrontmatter(unittest.TestCase):
    def test_body_hr_does_not_truncate(self):
        text = "---\nid: X-1\ntitle: x\n---\n\n## Body\n\nfirst\n\n---\n\nsecond\n"
        _, body = R._split_frontmatter(text, Path("t.md"))
        self.assertIn("second", body)

    def test_unclosed_frontmatter_detected(self):
        text = "---\nid: X-2\ntitle: x\n\n## Body\n\n---\n\ntail\n"
        with self.assertRaises(R.CardError):
            R._split_frontmatter(text, Path("t.md"))

    def test_crlf_and_bom(self):
        text = "\ufeff---\r\nid: X-3\r\ntitle: x\r\n---\r\nbody\r\n"
        fm, _ = R._split_frontmatter(text, Path("t.md"))
        self.assertEqual(fm["id"], "X-3")

    def test_miniyaml_round_trip(self):
        for s in ["plain", "a,b", "alpha #1", "[x", "true", "12", "a: b", "", "x\ny",
                  "-a", "2000-01-01", "it's", 'say "hi"', "no", "null"]:
            self.assertEqual(miniyaml.loads("k: " + miniyaml.dump_scalar(s))["k"], s, s)
        vals = ["a,b", "c #d", "all", "x]"]
        self.assertEqual(miniyaml.loads("k: " + miniyaml.dump_flow_list(vals))["k"], vals)

    def test_miniyaml_refuses_aliases(self):
        with self.assertRaises(miniyaml.YamlError):
            miniyaml.loads("a: &x 1\nb: *x\n")

    def test_miniyaml_nested(self):
        d = miniyaml.loads(
            "scope:\n  regions: all\n  projects: [a, b]\nlist:\n- one\n- k: v\n  k2: [1, 2]\n"
            "blk: |\n  l1\n  l2\n")
        self.assertEqual(d["scope"], {"regions": "all", "projects": ["a", "b"]})
        self.assertEqual(d["list"], ["one", {"k": "v", "k2": [1, 2]}])
        self.assertEqual(d["blk"], "l1\nl2\n")


# ============================================================ scan_candidates.py
class TestScan(Base):
    def notes(self):
        n = self.tmp / "notes"
        n.mkdir(exist_ok=True)
        return n

    def test_scan_queues_strong_signals_only_into_inbox(self):
        n = self.notes()
        (n / "meeting.md").write_text("# Sync\n\nFinal decision: we will not ship on Fridays.\n",
                                      encoding="utf-8")
        (n / "weak.md").write_text("# Misc\n\nWe must think about this.\n", encoding="utf-8")
        before = sorted(p.name for p in self.rd.rglob("*.md") if "_inbox" not in p.parts)
        r = run("scan_candidates.py", rd=self.rd)
        self.assertEqual(r.returncode, 0, r.stderr)
        q = (self.rd / "_inbox" / "QUEUE.md").read_text(encoding="utf-8")
        self.assertIn("notes/meeting.md", q)
        self.assertNotIn("notes/weak.md", q)
        after = sorted(p.name for p in self.rd.rglob("*.md") if "_inbox" not in p.parts)
        self.assertEqual(before, after, "scan must never enroll a card")
        self.assertEqual(self.audit().returncode, 0)

    def test_scan_skips_cited_ignored_and_old(self):
        n = self.notes()
        for name in ("example-units-meeting.md", "ignored.md", "old.md"):
            (n / name).write_text("Final decision: no longer allowed.\n", encoding="utf-8")
        old = time.time() - 30 * 86400
        os.utime(n / "old.md", (old, old))
        with open(self.rd / "_inbox" / "IGNORE.txt", "a", encoding="utf-8") as fh:
            fh.write("notes/ignored.md\n")
        r = run("scan_candidates.py", rd=self.rd)
        self.assertEqual(r.returncode, 0, r.stderr)
        q = (self.rd / "_inbox" / "QUEUE.md").read_text(encoding="utf-8")
        for name in ("example-units-meeting.md", "ignored.md", "old.md"):
            self.assertNotIn(name, q)

    def test_scan_does_not_read_the_registry_itself(self):
        (self.rd / "constraints" / "C-001-prices-are-never-quoted-to-customers-without.md") \
            .touch()
        run("scan_candidates.py", rd=self.rd)
        q = (self.rd / "_inbox" / "QUEUE.md").read_text(encoding="utf-8")
        self.assertNotIn("decision-registry/", q)

    def test_scan_failure_does_not_overwrite_queue(self):
        q = self.rd / "_inbox" / "QUEUE.md"
        q.write_text("# previous real queue\n", encoding="utf-8")
        r = run("scan_candidates.py", "--root", self.tmp / "does-not-exist", rd=self.rd)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(q.read_text(encoding="utf-8"), "# previous real queue\n")


# ============================================================ review-round regressions
WS = [" ", "\t", "\u00a0", "\u2003", "\u3000", "\u2009", "\u200b", "\n"]


class TestParserFixes(unittest.TestCase):
    def rt(self, s):
        self.assertEqual(miniyaml.loads("k: " + miniyaml.dump_scalar(s))["k"], s, repr(s))
        self.assertEqual(miniyaml.loads("k: " + miniyaml.dump_flow_list([s, "x"]))["k"],
                         [s, "x"], repr(s))
        self.assertEqual(miniyaml.loads("k:\n  - " + miniyaml.dump_scalar(s))["k"], [s], repr(s))

    def test_C1_round_trip_grid_whitespace_x_special(self):
        for ws in WS:
            for ch in ("#", ":"):
                for s in (f"a{ws}{ch}b", f"a{ch}{ws}b", f"a{ws}{ch}", f"a{ch}{ws}",
                          f"{ws}{ch}a", f"{ch}{ws}a", f"a{ch}", f"{ch}a", f"a{ws}b{ws}{ch}{ws}c"):
                    self.rt(s)

    def test_C1_reader_only_space_or_tab_starts_comment(self):
        self.assertEqual(miniyaml.loads("k: a\u3000#b")["k"], "a\u3000#b")
        self.assertEqual(miniyaml.loads("k: a\t#b")["k"], "a")

    def test_C2_continuation_with_mapping_syntax_is_error(self):
        with self.assertRaises(miniyaml.YamlError):
            miniyaml.loads("title: first\n  force: binding\n")

    def test_C2_continuation_comment_stripped(self):
        d = miniyaml.loads("title: first\n  second # note\nnext: 1\n")
        self.assertEqual(d, {"title": "first second", "next": 1})

    def test_C6_empty_flow_element_is_error(self):
        for bad in ("[a,,b]", "[,a]", "{a: 1,,b: 2}"):
            with self.assertRaises(miniyaml.YamlError, msg=bad):
                miniyaml.loads("k: " + bad)
        self.assertEqual(miniyaml.loads("k: [a, b,]")["k"], ["a", "b"])

    def test_C7_nested_block_sequence_is_error(self):
        for bad in ("k:\n  - - a\n", "k:\n  -\n    - a\n"):
            with self.assertRaises(miniyaml.YamlError, msg=bad):
                miniyaml.loads(bad)

    def test_C8_leading_zero_stays_string(self):
        d = miniyaml.loads("a: 007\nb: 0.5\nc: 00.5\nd: 7\n")
        self.assertEqual(d, {"a": "007", "b": 0.5, "c": "00.5", "d": 7})
        self.rt("007")

    def test_C9_block_scalar_dedent_is_error_and_folded_refused(self):
        with self.assertRaises(miniyaml.YamlError):
            miniyaml.loads("k: |\n    four\n  two\n")
        with self.assertRaises(miniyaml.YamlError):
            miniyaml.loads("k: >\n  text\n")
        self.assertEqual(miniyaml.loads("k: |-\n  a\n    b\n")["k"], "a\n  b")

    def test_C10_double_quoted_literal_tab_and_escapes(self):
        self.assertEqual(miniyaml.loads('k: "a\tb"')["k"], "a\tb")
        self.assertEqual(miniyaml.loads(r'k: "a\/b\x41\_\u00e9"')["k"], "a/bA\u00a0\u00e9")
        with self.assertRaises(miniyaml.YamlError):
            miniyaml.loads(r'k: "bad \q escape"')


class TestReviewFixes(Base):
    BASE = TestAdd.BASE

    def test_C3_decided_on_strict_format(self):
        for bad in ("20260105", "2026-1-5", "2026-01-05T00:00"):
            r = run("add.py", "new", "decision", "--title", "d", *self.BASE,
                    "--decided-by", "me", "--decided-on", bad, rd=self.rd)
            self.assertNotEqual(r.returncode, 0, bad)
        self.assertFalse(list(self.rd.glob("decisions/D-002-*")))

    def test_C3_audit_checks_decided_on(self):
        self.put("D-100", "decision", decided_on="20000101")
        a = self.assertAuditError("E013")
        self.assertIn("decided_on", a.stdout)

    def test_C4_indented_dashes_in_block_scalar_are_content(self):
        p = self.rd / "constraints" / "C-100-test.md"
        text = raw_card("C-100", "constraint", notes="|\n  line one\n  ---\n  line three")
        p.write_text(text, encoding="utf-8")
        fm = R._split_frontmatter(text, p)[0]
        self.assertEqual(fm["notes"], "line one\n---\nline three\n")
        self.assertEqual(fm["tags"], [])
        self.reindex()
        self.assertEqual(self.audit().returncode, 0)

    def test_C4_add_py_ignores_indented_dashes(self):
        p = self.put("C-100", "constraint", notes="|\n  ---\n  x")
        self.reindex()
        r = run("add.py", "verify", "C-100", "--note", "n", rd=self.rd)
        self.assertEqual(r.returncode, 0, r.stderr)
        fm = self.fm(p)
        self.assertEqual(fm["notes"], "---\nx\n")
        self.assertEqual(fm["verified"], date.today().isoformat())

    def test_C5_unknown_scope_key(self):
        self.put("C-100", "constraint", scope=("all", "all", "[release]"))
        p = self.card("C-100")
        self.edit(p, r"^  regions: all$", "  region: [EMEA]")
        a = self.audit()
        self.assertEqual(a.returncode, 1)
        self.assertIn("E014", a.stdout)
        self.assertIn("region", a.stdout)
        c = run("check.py", rd=self.rd)
        self.assertEqual(c.returncode, 3)

    def test_C12_superseded_by_requires_back_link(self):
        self.put("D-100", "decision")  # does not claim to supersede D-001
        p = self.card("D-001")
        self.edit(p, r"^status: active$", "status: superseded")
        self.edit(p, r"^superseded_by:\s*$", "superseded_by: D-100")
        a = self.assertAuditError("E006")
        self.assertIn("not closed both ways", a.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
