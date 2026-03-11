from collections.abc import Callable
from pathlib import Path
from typing import Final
import unittest


README_DEPLOY_DEFAULTS_SENTENCE: Final[str] = (
    "`deploy_local.sh` now seeds integrity strictness flags "
    "(`JARVIS_INTEGRITY_FAIL_ON_ORPHANS`, "
    "`JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT`, "
    "`JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS`) to `0` "
    "in `/etc/jarvis/config.env` when missing, so behavior is explicit and opt-in."
)

DEPLOY_SCRIPT_PATH: Final[Path] = Path("scripts/deploy_local.sh")
ENV_EXAMPLE_PATH: Final[Path] = Path("config/jarvis.env.example")
README_PATH: Final[Path] = Path("README.md")
EXPECTED_FIXTURE_PATHS: Final[tuple[Path, ...]] = (DEPLOY_SCRIPT_PATH, ENV_EXAMPLE_PATH, README_PATH)


ReadmeSnippetTuple = tuple[str, ...]
FixturePathCheck = Callable[[Path], None]


EXPECTED_README_SNIPPETS_SET: Final[set[str]] = {
    "JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT",
    "JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT=1",
    "JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS",
    "JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS=1",
    "JARVIS_INTEGRITY_FAIL_ON_ORPHANS",
    "JARVIS_INTEGRITY_FAIL_ON_ORPHANS=1",
    "deploy_local.sh",
    "duplicate/malformed membership drift",
    "exit code `8`",
}



EXPECTED_README_SNIPPETS_SORTED: Final[ReadmeSnippetTuple] = tuple(sorted(EXPECTED_README_SNIPPETS_SET))


README_INTEGRITY_SNIPPETS: Final[ReadmeSnippetTuple] = (
    "JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT",
    "JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT=1",
    "JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS",
    "JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS=1",
    "JARVIS_INTEGRITY_FAIL_ON_ORPHANS",
    "JARVIS_INTEGRITY_FAIL_ON_ORPHANS=1",
    "deploy_local.sh",
    "duplicate/malformed membership drift",
    "exit code `8`",
)


class DeployConfigDefaultsTests(unittest.TestCase):

    def assert_readme_contains(self, readme: str, snippet: str) -> None:
        self.assertIn(snippet, readme, msg=f"README is missing expected text: {snippet!r}")

    def assert_readme_contains_defaults_sentence(self, readme: str) -> None:
        self.assertIn(
            README_DEPLOY_DEFAULTS_SENTENCE,
            readme,
            msg="README is missing the deploy-defaults integrity strictness sentence",
        )

    def assert_readme_snippets_match_expected_order(self) -> None:
        self.assertEqual(
            README_INTEGRITY_SNIPPETS,
            EXPECTED_README_SNIPPETS_SORTED,
            msg="README_INTEGRITY_SNIPPETS ordering should match sorted expected snippet set",
        )

    def assert_each_fixture_path(self, check: FixturePathCheck) -> None:
        for path in EXPECTED_FIXTURE_PATHS:
            with self.subTest(path=path):
                check(path)

    def test_fixture_paths_order_is_stable(self):
        self.assertEqual(
            EXPECTED_FIXTURE_PATHS,
            (DEPLOY_SCRIPT_PATH, ENV_EXAMPLE_PATH, README_PATH),
            msg="EXPECTED_FIXTURE_PATHS order should stay deploy/env/readme for predictable subTest output",
        )

    def test_fixture_paths_match_expected_set(self):
        expected_paths = {DEPLOY_SCRIPT_PATH, ENV_EXAMPLE_PATH, README_PATH}
        self.assertEqual(
            set(EXPECTED_FIXTURE_PATHS),
            expected_paths,
            msg="EXPECTED_FIXTURE_PATHS must include exactly deploy script, env example, and README",
        )

    def test_fixture_paths_do_not_use_parent_traversal(self):
        self.assert_each_fixture_path(
            lambda path: self.assertNotIn("..", path.parts, msg=f"Fixture path must not use parent traversal: {path}")
        )

    def test_fixture_paths_are_relative(self):
        self.assert_each_fixture_path(
            lambda path: self.assertFalse(path.is_absolute(), msg=f"Fixture path should be relative: {path}")
        )

    def test_fixture_paths_are_unique(self):
        self.assertEqual(
            len(EXPECTED_FIXTURE_PATHS),
            len(set(EXPECTED_FIXTURE_PATHS)),
            msg="Fixture paths should be distinct to prevent overlapping coverage",
        )

    def test_fixture_paths_exist(self):
        self.assert_each_fixture_path(
            lambda path: self.assertTrue(path.is_file(), msg=f"Expected fixture file missing: {path}")
        )

    def test_deploy_script_seeds_integrity_strictness_defaults(self):
        script = DEPLOY_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn('ensure_env_default "JARVIS_INTEGRITY_FAIL_ON_ORPHANS" "0"', script)
        self.assertIn('ensure_env_default "JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT" "0"', script)
        self.assertIn('ensure_env_default "JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS" "0"', script)

    def test_env_example_documents_integrity_strictness_flags(self):
        env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
        self.assertIn("# JARVIS_INTEGRITY_FAIL_ON_ORPHANS=0", env_example)
        self.assertIn("# JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT=0", env_example)
        self.assertIn("# JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS=0", env_example)


    def test_readme_defaults_sentence_is_non_empty_and_trimmed(self):
        self.assertTrue(
            README_DEPLOY_DEFAULTS_SENTENCE,
            msg="README_DEPLOY_DEFAULTS_SENTENCE must not be empty",
        )
        self.assertEqual(
            README_DEPLOY_DEFAULTS_SENTENCE,
            README_DEPLOY_DEFAULTS_SENTENCE.strip(),
            msg="README_DEPLOY_DEFAULTS_SENTENCE must not have surrounding whitespace",
        )

    def test_readme_integrity_snippet_expectations_are_sorted(self):
        self.assert_readme_snippets_match_expected_order()

    def test_readme_integrity_snippet_expectations_are_non_empty_and_trimmed(self):
        for snippet in README_INTEGRITY_SNIPPETS:
            with self.subTest(snippet=snippet):
                self.assertTrue(snippet, msg="README snippet expectation must not be empty")
                self.assertEqual(
                    snippet,
                    snippet.strip(),
                    msg=f"README snippet expectation has surrounding whitespace: {snippet!r}",
                )

    def test_readme_integrity_snippet_set_matches_expected(self):
        self.assertEqual(
            set(README_INTEGRITY_SNIPPETS),
            EXPECTED_README_SNIPPETS_SET,
            msg="README_INTEGRITY_SNIPPETS must stay aligned with expected deploy docs coverage",
        )

    def test_readme_documents_duplicate_membership_strictness_flag(self):
        readme = README_PATH.read_text(encoding="utf-8")

        self.assert_readme_contains_defaults_sentence(readme)
        for snippet in README_INTEGRITY_SNIPPETS:
            with self.subTest(snippet=snippet):
                self.assert_readme_contains(readme, snippet)



if __name__ == "__main__":
    unittest.main()
