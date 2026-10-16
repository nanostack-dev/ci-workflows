"""Tests for migration_lint.py.

Every file in fixtures/cases declares what it must produce in its own header:

    -- expect-custom: rule-a, rule-b      custom checks (use `none` for a clean file)
    -- expect-custom-warning: rule        custom checks that only warn
    -- expect-squawk: rule-a, rule-a      squawk after the script's filtering

fixtures/history stands for the repository's earlier migrations: the script
reads it to learn which tables are hypertables.

squawk tests need the binary. Set SQUAWK to its path or put it on PATH; without
one they are skipped (the self-test workflow installs the pinned release).

Run from scripts/migration-lint:  python3 -m unittest discover -s tests -v
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import migration_lint as ml  # noqa: E402

HISTORY = os.path.join(HERE, "fixtures", "history")
CASES = os.path.join(HERE, "fixtures", "cases")
SCRIPT = os.path.join(os.path.dirname(HERE), "migration_lint.py")
SQUAWK = os.environ.get("SQUAWK") or shutil.which("squawk")


def header(path, key):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"--\s*%s:\s*(.*?)\s*$" % re.escape(key), line)
            if m:
                return [] if m.group(1) == "none" else sorted(x.strip() for x in m.group(1).split(","))
    return None


def case_files():
    return sorted(os.path.join(CASES, f) for f in os.listdir(CASES) if f.endswith(".sql"))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TokenizerTests(unittest.TestCase):
    def test_splits_on_semicolons_outside_quoting(self):
        src = "SELECT 'a;b'; SELECT \"x;y\"; SELECT $$p;q$$; SELECT $t$r;s$t$; -- c;d\nSELECT E'\\';';"
        self.assertEqual(len(ml.split_statements(src)), 5)

    def test_nested_block_comment(self):
        self.assertEqual(len(ml.split_statements("/* a /* b */ ; */ SELECT 1; SELECT 2;")), 2)

    def test_unterminated_last_statement_counts(self):
        self.assertEqual(len(ml.split_statements("SELECT 1; SELECT 2")), 2)

    def test_comment_only_file_has_no_statements(self):
        self.assertEqual(ml.split_statements("-- nothing\n/* here */\n"), [])

    def test_trailing_comment_belongs_to_previous_statement(self):
        first, second = ml.split_statements("SELECT 1; -- one\n-- two\nSELECT 2;")
        self.assertEqual([c.text.strip() for c in first.comments], ["one"])
        self.assertEqual([c.text.strip() for c in second.comments], ["two"])

    def test_parameter_is_not_a_dollar_quote(self):
        self.assertEqual(len(ml.split_statements("SELECT $1; SELECT $2;")), 2)


class CustomCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hypertables = ml.collect_hypertables(HISTORY, [])

    def test_hypertables_are_found_in_every_supported_spelling(self):
        self.assertEqual(self.hypertables, {"events", "Metrics", "samples"})

    def test_extra_hypertables_input(self):
        found = ml.collect_hypertables(HISTORY, ["public.readings", '"Mixed"'])
        self.assertIn("readings", found)
        self.assertIn("Mixed", found)


def _make_custom_test(path):
    def test(self):
        findings, _stmts, _created = ml.custom_checks(path, read(path), self.hypertables)
        errors = sorted(f.rule for f in findings if not f.source.endswith("warning"))
        warnings = sorted(f.rule for f in findings if f.source.endswith("warning"))
        expected = header(path, "expect-custom")
        self.assertIsNotNone(expected, "%s declares no expect-custom header" % os.path.basename(path))
        self.assertEqual(errors, expected)
        self.assertEqual(warnings, header(path, "expect-custom-warning") or [])

    return test


for _p in case_files():
    _name = "test_custom_" + re.sub(r"\W", "_", os.path.basename(_p)[: -len(".sql")])
    setattr(CustomCheckTests, _name, _make_custom_test(_p))


@unittest.skipUnless(SQUAWK, "squawk binary not available (set SQUAWK)")
class SquawkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hypertables = ml.collect_hypertables(HISTORY, [])

    def lint(self, path, exclude=()):
        src = read(path)
        _f, stmts, created = ml.custom_checks(path, src, self.hypertables)
        excluded = list(ml.BASE_EXCLUDED_RULES) + list(exclude)
        raw = ml.run_squawk(SQUAWK, [path], excluded, [], "18")
        return sorted(f.rule for f in ml.filter_squawk(raw, {path: (src, stmts, created)}, self.hypertables))

    def test_base_exclusions_name_real_rules(self):
        # squawk rejects an unknown rule name, which would break every caller.
        probe = os.path.join(CASES, "concurrently_alone.up.sql")
        ml.run_squawk(SQUAWK, [probe], list(ml.BASE_EXCLUDED_RULES), [], "18")

    def test_extra_exclusion_silences_a_rule(self):
        path = os.path.join(CASES, "drop_column.up.sql")
        self.assertEqual(self.lint(path), ["ban-drop-column"])
        self.assertEqual(self.lint(path, exclude=["ban-drop-column"]), [])


def _make_squawk_test(path):
    def test(self):
        self.assertEqual(self.lint(path), header(path, "expect-squawk"))

    return test


for _p in case_files():
    if header(_p, "expect-squawk") is None:
        continue
    if _p.endswith(".down.sql"):
        continue  # the script never sends down files to squawk
    _name = "test_squawk_" + re.sub(r"\W", "_", os.path.basename(_p)[: -len(".sql")])
    setattr(SquawkTests, _name, _make_squawk_test(_p))


class GitDiffTests(unittest.TestCase):
    """The script lints what a change adds or modifies, not the history."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="migration-lint-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.mig = os.path.join(self.tmp, "db", "migrations")
        os.makedirs(self.mig)
        for f in os.listdir(HISTORY):
            shutil.copy(os.path.join(HISTORY, f), self.mig)
        # History that would fail every check: it must never be reported.
        self.put("000002_old_backfill.up.sql", "UPDATE webhooks SET created_at = now();\n")
        self.put("000002_old_backfill.down.sql", "SELECT 1;\n")
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.commit("base")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()

    def git(self, *args):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
        return subprocess.run(["git", *args], cwd=self.tmp, capture_output=True, text=True, check=True, env=env)

    def commit(self, msg):
        self.git("-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)

    def put(self, name, body):
        with open(os.path.join(self.mig, name), "w", encoding="utf-8") as fh:
            fh.write(body)

    def run_lint(self, *extra):
        cmd = [sys.executable, "-I", SCRIPT, "--migrations-dir", "db/migrations", "--no-squawk", *extra]
        return subprocess.run(cmd, cwd=self.tmp, capture_output=True, text=True)

    def test_only_changed_files_are_linted(self):
        self.put("000003_cursor_index.up.sql", "CREATE INDEX CONCURRENTLY IF NOT EXISTS i ON webhooks (id);\nANALYZE webhooks;\n")
        self.put("000003_cursor_index.down.sql", "DROP INDEX IF EXISTS i;\n")
        self.git("add", "-A")
        self.commit("add")
        r = self.run_lint("--base", self.base)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("000003_cursor_index.up.sql:1: error: [concurrently-alone]", r.stdout)
        self.assertNotIn("000002_old_backfill", r.stdout)

    def test_clean_change_passes(self):
        self.put("000003_ok.up.sql", "CREATE INDEX CONCURRENTLY IF NOT EXISTS i ON webhooks (id);\n")
        self.git("add", "-A")
        self.commit("add")
        r = self.run_lint("--base", self.base)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Migration lint passed.", r.stdout)

    def test_modified_migration_is_linted(self):
        self.put("000002_old_backfill.down.sql", "DELETE FROM webhooks;\n")
        self.git("add", "-A")
        self.commit("edit")
        r = self.run_lint("--base", self.base)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("[unbounded-delete]", r.stdout)

    def test_change_that_touches_no_migration_passes(self):
        with open(os.path.join(self.tmp, "README.md"), "w") as fh:
            fh.write("x\n")
        self.git("add", "-A")
        self.commit("docs")
        r = self.run_lint("--base", self.base)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("nothing to lint", r.stdout)

    def test_unresolvable_base_fails_instead_of_passing(self):
        r = self.run_lint("--base", "0" * 40)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("Cannot resolve", r.stderr)

    def test_no_base_and_no_files_is_an_error(self):
        r = self.run_lint()
        self.assertEqual(r.returncode, 2)

    def test_github_annotations(self):
        self.put("000003_bad.up.sql", "DELETE FROM webhooks;\n")
        self.git("add", "-A")
        self.commit("add")
        env = dict(os.environ, GITHUB_ACTIONS="true", GITHUB_STEP_SUMMARY=os.path.join(self.tmp, "summary.md"))
        cmd = [sys.executable, "-I", SCRIPT, "--migrations-dir", "db/migrations", "--no-squawk", "--base", self.base]
        r = subprocess.run(cmd, cwd=self.tmp, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 1)
        self.assertRegex(r.stdout, r"::error file=db/migrations/000003_bad\.up\.sql,line=1,title=migration-lint/unbounded-delete::")
        with open(env["GITHUB_STEP_SUMMARY"], encoding="utf-8") as fh:
            self.assertIn("unbounded-delete", fh.read())

    def test_explicit_files_mode(self):
        path = os.path.join(CASES, "update_backfill.up.sql")
        r = subprocess.run(
            [sys.executable, "-I", SCRIPT, "--migrations-dir", HISTORY, "--no-squawk", "--files", path],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("[update-backfill]", r.stdout)


if __name__ == "__main__":
    unittest.main()
