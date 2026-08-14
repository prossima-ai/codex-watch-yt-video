from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPOSITORY_ROOT / ".agents" / "skills" / "watch"
SKILL_FILE = SKILL_ROOT / "SKILL.md"
METADATA_FILE = SKILL_ROOT / "agents" / "openai.yaml"
README_FILE = REPOSITORY_ROOT / "README.md"
SETUP_FILE = REPOSITORY_ROOT / "docs" / "setup-and-troubleshooting.md"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_package_contract import (  # noqa: E402
    capture_fresh_task_inventory,
    discover_personal_skills,
    discover_repository_skills,
    inspect_personal_installation,
    isolate_skill_path,
    plan_manual_personal_installation,
    route_watch_invocation,
    validate_skill_package,
)


NARROW_DESCRIPTION = (
    "Inspect exactly one public unauthenticated video URL or one lawful local video "
    "when the user asks to inspect, analyze, summarize, or answer from it. Use "
    "explicitly with $watch or implicitly only for a clear request about one "
    "supplied or Current source; exclude downloads, edits, code requests, private, "
    "authenticated, or live media, playlists, and ambiguous or multiple sources."
)


def write_skill_fixture(repository_root: Path, name: str = "watch") -> Path:
    skill_root = repository_root / ".agents" / "skills" / name
    (skill_root / "agents").mkdir(parents=True)
    (skill_root / "scripts").mkdir()
    (skill_root / "references").mkdir()
    (skill_root / "SKILL.md").write_text(
        "\n".join(("---", f"name: {name}", f"description: {NARROW_DESCRIPTION}", "---", "")),
        encoding="utf-8",
    )
    (skill_root / "agents" / "openai.yaml").write_text(
        "\n".join(
            (
                "interface:",
                '  display_name: "Watch"',
                '  short_description: "Inspect one supplied video as grounded evidence"',
                '  default_prompt: "$watch <source>"',
                "policy:",
                "  allow_implicit_invocation: true",
                "",
            )
        ),
        encoding="utf-8",
    )
    return skill_root


class CanonicalSkillPackageTests(unittest.TestCase):
    def test_canonical_package_has_only_supported_discovery_metadata(self) -> None:
        self.assertTrue(SKILL_FILE.is_file())
        self.assertEqual(
            METADATA_FILE.read_text(encoding="utf-8"),
            "\n".join(
                (
                    "interface:",
                    '  display_name: "Watch"',
                    '  short_description: "Inspect one supplied video as grounded evidence"',
                    '  default_prompt: "$watch <one public unauthenticated video URL or lawful local video> [optional question]"',
                    "policy:",
                    "  allow_implicit_invocation: true",
                    "",
                )
            ),
        )

        front_matter = SKILL_FILE.read_text(encoding="utf-8").split("---", 2)[1]
        front_matter_keys = [
            line.split(":", 1)[0]
            for line in front_matter.splitlines()
            if line and not line.isspace()
        ]
        self.assertEqual(front_matter_keys, ["name", "description"])
        package_entries = {path.name for path in SKILL_ROOT.iterdir()}
        self.assertTrue({"SKILL.md", "agents", "references", "scripts"} <= package_entries)
        self.assertFalse(
            {"tests", "fixtures", "development", "release-evidence"} & package_entries
        )

    def test_package_validator_accepts_the_canonical_package(self) -> None:
        report = validate_skill_package(SKILL_ROOT)

        self.assertTrue(report.valid)
        self.assertEqual(report.errors, ())

    def test_package_validator_rejects_unsupported_metadata_and_authority_claims(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = write_skill_fixture(root)
            metadata_file = skill_root / "agents" / "openai.yaml"
            metadata_file.write_text(
                metadata_file.read_text(encoding="utf-8")
                + "dependencies:\n  tools:\n    - type: mcp\n",
                encoding="utf-8",
            )
            unsupported_metadata = validate_skill_package(skill_root)

            metadata_file.write_text(
                "\n".join(
                    (
                        "interface:",
                        '  display_name: "Watch"',
                        '  short_description: "Inspect one supplied video as grounded evidence"',
                        '  default_prompt: "$watch <source>"',
                        "policy:",
                        "  allow_implicit_invocation: true",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            skill_file = skill_root / "SKILL.md"
            skill_file.write_text(
                skill_file.read_text(encoding="utf-8")
                + "This skill can self-install, requires an MCP dependency, and bypasses the sandbox.\n",
                encoding="utf-8",
            )
            unsupported_claims = validate_skill_package(skill_root)

        self.assertIn("metadata_sections_invalid", unsupported_metadata.errors)
        self.assertIn("unsupported_authority_claim", unsupported_claims.errors)

    def test_package_validator_rejects_a_broad_discovery_description(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = write_skill_fixture(Path(directory))
            (skill_root / "SKILL.md").write_text(
                "\n".join(
                    (
                        "---",
                        "name: watch",
                        "description: Analyze any video request.",
                        "---",
                        "",
                    )
                ),
                encoding="utf-8",
            )

            report = validate_skill_package(skill_root)

        self.assertIn("trigger_description_invalid", report.errors)

    def test_package_validator_rejects_implicit_watch_as_a_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = write_skill_fixture(Path(directory))
            skill_file = skill_root / "SKILL.md"
            skill_file.write_text(
                skill_file.read_text(encoding="utf-8").replace(
                    "asks to inspect", "asks to watch"
                ),
                encoding="utf-8",
            )

            report = validate_skill_package(skill_root)

        self.assertIn("trigger_description_invalid", report.errors)

    def test_package_validator_requires_code_and_live_trigger_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for phrase in ("code requests, ", "or live media, "):
                with self.subTest(phrase=phrase):
                    skill_root = write_skill_fixture(Path(directory) / phrase[:4])
                    skill_file = skill_root / "SKILL.md"
                    skill_file.write_text(
                        skill_file.read_text(encoding="utf-8").replace(phrase, ""),
                        encoding="utf-8",
                    )

                    report = validate_skill_package(skill_root)

                    self.assertIn("trigger_description_invalid", report.errors)

    def test_package_validator_keeps_tests_and_release_evidence_outside_skill_tree(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = write_skill_fixture(Path(directory))
            (skill_root / "tests").mkdir()
            (skill_root / "release-evidence").mkdir()

            report = validate_skill_package(skill_root)

        self.assertIn("forbidden_skill_entry:tests", report.errors)
        self.assertIn("forbidden_skill_entry:release-evidence", report.errors)

    def test_package_validator_rejects_nested_artifacts_and_symlinked_components(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested_skill = write_skill_fixture(root / "nested")
            (nested_skill / "scripts" / "fixtures").mkdir()
            outside_directory = root / "outside-directory"
            outside_directory.mkdir()
            (nested_skill / "references" / "outside").symlink_to(
                outside_directory,
                target_is_directory=True,
            )
            nested_report = validate_skill_package(nested_skill)

            linked_skill = write_skill_fixture(root / "linked")
            external_skill_file = root / "external-skill.md"
            external_skill_file.write_text("not a canonical skill", encoding="utf-8")
            (linked_skill / "SKILL.md").unlink()
            (linked_skill / "SKILL.md").symlink_to(external_skill_file)
            linked_report = validate_skill_package(linked_skill)

        self.assertIn("forbidden_skill_entry:scripts/fixtures", nested_report.errors)
        self.assertIn("symlink_in_skill_tree:references/outside", nested_report.errors)
        self.assertIn("symlink_in_skill_tree:SKILL.md", linked_report.errors)

    def test_documented_manual_installation_is_fail_closed_and_truthful(self) -> None:
        readme = README_FILE.read_text(encoding="utf-8")
        setup = SETUP_FILE.read_text(encoding="utf-8")

        self.assertIn("$REPO_ROOT/.agents/skills/watch", readme)
        self.assertIn("docs/setup-and-troubleshooting.md", readme)
        self.assertIn("$watch https://video.example/watch?v=one", readme)
        self.assertIn('$watch "/path/to/local video.mp4"', readme)
        self.assertIn(
            "$HOME/.agents/skills/watch -> $REPO_ROOT/.agents/skills/watch",
            setup,
        )
        self.assertIn('[ -e "$target" ] || [ -L "$target" ]', setup)
        self.assertIn('agents_parent="$HOME/.agents"', setup)
        self.assertIn('skills_parent="$agents_parent/skills"', setup)
        self.assertIn("broken symlink", setup)
        self.assertIn("Do not use `ln -f`", setup)
        self.assertIn("Do not use a bare `ln -s`", setup)
        self.assertNotIn('ln -s "$source" "$target"', setup)
        self.assertIn("never copy", setup.casefold())
        self.assertIn("never self-install", setup.casefold())
        self.assertIn("never self-update", setup.casefold())
        self.assertIn("configuration", setup.casefold())
        self.assertIn("outside-workspace", setup.casefold())
        self.assertIn("code", setup.casefold())
        self.assertIn("live", setup.casefold())
        self.assertIn("no duplicate-name precedence", setup.casefold())
        self.assertIn("new Desktop task", setup)
        self.assertIn("already-open task", setup)
        self.assertIn("restart once", setup.casefold())
        self.assertIn("do not prove live Desktop discovery", setup)


class HermeticDiscoveryTests(unittest.TestCase):

    def test_repository_discovery_reports_the_canonical_path_from_a_nested_task(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository_root = Path(directory) / "repository"
            canonical_skill = write_skill_fixture(repository_root)
            nested_task = repository_root / "nested" / "task"
            nested_task.mkdir(parents=True)

            candidates = discover_repository_skills(nested_task, repository_root)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].scope, "repository")
        self.assertEqual(candidates[0].name, "watch")
        self.assertEqual(candidates[0].skill_root, canonical_skill)

    def test_personal_discovery_preserves_the_symlink_path_and_verifies_its_target(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root = root / "repository with spaces [safe]"
            canonical_skill = write_skill_fixture(repository_root)
            personal_home = root / "personal home !"
            personal_target = personal_home / ".agents" / "skills" / "watch"
            personal_target.parent.mkdir(parents=True)
            personal_target.symlink_to(canonical_skill, target_is_directory=True)

            candidates = discover_personal_skills(personal_home)
            inspection = inspect_personal_installation(personal_home, repository_root)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].scope, "personal")
        self.assertEqual(candidates[0].skill_root, personal_target)
        self.assertEqual(candidates[0].resolved_skill_root, canonical_skill.resolve())
        self.assertEqual(inspection.status, "valid_symlink")
        self.assertEqual(inspection.target, personal_target)
        self.assertEqual(inspection.source, canonical_skill.resolve())

    def test_manual_installation_refuses_every_existing_personal_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root = root / "repository"
            canonical_skill = write_skill_fixture(repository_root)

            absent_home = root / "absent home"
            missing_parent_plan = plan_manual_personal_installation(
                absent_home, repository_root
            )
            self.assertEqual(missing_parent_plan.status, "refused_missing_parent")
            self.assertFalse(missing_parent_plan.requires_explicit_approval)
            self.assertIsNone(missing_parent_plan.exact_mutation)

            ready_home = root / "ready home"
            (ready_home / ".agents" / "skills").mkdir(parents=True)
            ready_plan = plan_manual_personal_installation(ready_home, repository_root)
            self.assertEqual(ready_plan.status, "manual_action_required")
            self.assertTrue(ready_plan.requires_explicit_approval)
            self.assertEqual(ready_plan.source, canonical_skill.resolve())
            self.assertFalse(os.path.lexists(ready_plan.target))
            self.assertIn(str(ready_plan.target), ready_plan.exact_mutation)

            for kind in (
                "file",
                "directory",
                "valid_symlink",
                "broken_symlink",
                "hostile_symlink",
            ):
                with self.subTest(kind=kind):
                    home = root / f"{kind} home"
                    target = home / ".agents" / "skills" / "watch"
                    target.parent.mkdir(parents=True)
                    if kind == "file":
                        target.write_text("do not replace", encoding="utf-8")
                    elif kind == "directory":
                        target.mkdir()
                    elif kind == "valid_symlink":
                        target.symlink_to(canonical_skill, target_is_directory=True)
                    elif kind == "broken_symlink":
                        target.symlink_to(root / "missing target", target_is_directory=True)
                    else:
                        hostile_target = root / "hostile target"
                        hostile_target.mkdir()
                        target.symlink_to(hostile_target, target_is_directory=True)

                    plan = plan_manual_personal_installation(home, repository_root)

                    self.assertEqual(plan.status, "refused_existing_target")
                    self.assertFalse(plan.requires_explicit_approval)
                    self.assertEqual(plan.target, target)
                    self.assertTrue(os.path.lexists(target))

    def test_manual_plan_refuses_symlinked_personal_parents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root = root / "repository"
            write_skill_fixture(repository_root)

            for parent_name in (".agents", "skills"):
                with self.subTest(parent_name=parent_name):
                    personal_home = root / f"personal-{parent_name}"
                    hostile_parent = root / f"hostile-{parent_name}"
                    hostile_parent.mkdir()
                    if parent_name == ".agents":
                        personal_home.mkdir()
                        (personal_home / ".agents").symlink_to(
                            hostile_parent,
                            target_is_directory=True,
                        )
                    else:
                        (personal_home / ".agents").mkdir(parents=True)
                        (personal_home / ".agents" / "skills").symlink_to(
                            hostile_parent,
                            target_is_directory=True,
                        )

                    plan = plan_manual_personal_installation(
                        personal_home, repository_root
                    )

                    self.assertEqual(plan.status, "refused_parent_symlink")
                    self.assertFalse(plan.requires_explicit_approval)
                    self.assertIsNone(plan.exact_mutation)
                    self.assertFalse((hostile_parent / "watch").exists())

    def test_manual_plan_preserves_special_paths_without_executing_global_mutation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root = root / "repository [space] & safe"
            canonical_skill = write_skill_fixture(repository_root)
            personal_home = root / "personal home ! #"
            (personal_home / ".agents" / "skills").mkdir(parents=True)
            global_configuration = root / ".codex" / "config.toml"
            global_configuration.parent.mkdir()
            global_configuration.write_text("unchanged", encoding="utf-8")

            with (
                patch(
                    "skill_package_contract.os.symlink",
                    side_effect=AssertionError("must not self-install"),
                ) as symlink,
                patch(
                    "skill_package_contract.os.replace",
                    side_effect=AssertionError("must not overwrite"),
                ) as replace,
                patch(
                    "skill_package_contract.os.unlink",
                    side_effect=AssertionError("must not remove"),
                ) as unlink,
                patch(
                    "shutil.copyfile",
                    side_effect=AssertionError("must not copy"),
                ) as copyfile,
                patch(
                    "shutil.copytree",
                    side_effect=AssertionError("must not copy a package tree"),
                ) as copytree,
                patch.object(
                    Path,
                    "write_text",
                    side_effect=AssertionError("must not self-update or write configuration"),
                ) as write_text,
                patch.object(
                    Path,
                    "home",
                    side_effect=AssertionError("must not select the real home directory"),
                ),
            ):
                plan = plan_manual_personal_installation(personal_home, repository_root)

            self.assertEqual(plan.status, "manual_action_required")
            self.assertIn(
                str(canonical_skill.resolve()),
                plan.exact_mutation,
            )
            self.assertIn("personal home ! #", str(plan.target))
            self.assertFalse(os.path.lexists(plan.target))
            self.assertNotIn("cp", plan.exact_mutation.casefold())
            self.assertNotIn("copy", plan.exact_mutation.casefold())
            self.assertNotIn("overwrite", plan.exact_mutation.casefold())
            self.assertNotIn("self-install", plan.exact_mutation.casefold())
            self.assertNotIn("update", plan.exact_mutation.casefold())
            self.assertNotIn("configuration", plan.exact_mutation.casefold())
            self.assertEqual(global_configuration.read_text(encoding="utf-8"), "unchanged")
            symlink.assert_not_called()
            replace.assert_not_called()
            unlink.assert_not_called()
            copyfile.assert_not_called()
            copytree.assert_not_called()
            write_text.assert_not_called()

    def test_explicit_and_narrow_implicit_invocation_do_not_grant_authority(
        self,
    ) -> None:
        explicit = route_watch_invocation(
            "$watch https://video.example/watch?v=one",
            source_count=1,
        )
        supplied_video = route_watch_invocation(
            "Please summarize this video for me.",
            source_count=1,
        )
        current_source = route_watch_invocation(
            "What does the current source show?",
            source_count=0,
            has_current_source=True,
        )

        self.assertEqual(explicit.route, "explicit")
        self.assertEqual(supplied_video.route, "implicit")
        self.assertEqual(current_source.route, "implicit")
        self.assertFalse(explicit.grants_authority)
        self.assertFalse(supplied_video.grants_authority)
        self.assertFalse(current_source.grants_authority)

    def test_near_miss_and_negative_requests_do_not_invoke_watch(self) -> None:
        cases = (
            ("What videos are available?", 1, False, "supported"),
            ("Download this video.", 1, False, "supported"),
            ("Edit this video into a short clip.", 1, False, "supported"),
            ("Write code to process this video.", 1, False, "supported"),
            ("Summarize these videos.", 2, False, "supported"),
            ("Summarize this video.", 0, False, "supported"),
            ("Analyze this video.", 1, False, "playlist"),
            ("Analyze this video.", 1, False, "private"),
            ("Analyze this video.", 1, False, "authenticated"),
            ("Analyze this video.", 1, False, "live"),
            ("Analyze this video.", 1, False, "ambiguous"),
            ("Watch this video.", 1, False, "supported"),
        )

        for prompt, source_count, has_current_source, source_state in cases:
            with self.subTest(prompt=prompt, source_state=source_state):
                decision = route_watch_invocation(
                    prompt,
                    source_count=source_count,
                    has_current_source=has_current_source,
                    source_state=source_state,
                )
                self.assertEqual(decision.route, "none")
                self.assertFalse(decision.grants_authority)

    def test_fresh_task_reads_benign_metadata_changes_without_refreshing_open_task(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository_root = Path(directory) / "repository"
            canonical_skill = write_skill_fixture(repository_root)
            task_directory = repository_root / "task"
            task_directory.mkdir()

            open_task = capture_fresh_task_inventory(task_directory, repository_root)
            metadata_file = canonical_skill / "agents" / "openai.yaml"
            metadata_file.write_text(
                metadata_file.read_text(encoding="utf-8").replace(
                    "grounded evidence", "updated discovery text"
                ),
                encoding="utf-8",
            )
            fresh_task = capture_fresh_task_inventory(task_directory, repository_root)

        self.assertEqual(len(open_task.entries), 1)
        self.assertEqual(len(fresh_task.entries), 1)
        self.assertIn("grounded evidence", open_task.entries[0].metadata)
        self.assertIn("updated discovery text", fresh_task.entries[0].metadata)

    def test_duplicate_names_require_exact_path_isolation_without_precedence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root = root / "repository"
            canonical_skill = write_skill_fixture(repository_root)
            personal_home = root / "personal"
            personal_skill = personal_home / ".agents" / "skills" / "watch"
            personal_skill.parent.mkdir(parents=True)
            personal_skill.symlink_to(canonical_skill, target_is_directory=True)
            task_directory = repository_root / "task"
            task_directory.mkdir()

            inventory = capture_fresh_task_inventory(
                task_directory,
                repository_root,
                personal_home=personal_home,
            )
            ambiguous = isolate_skill_path(inventory, "watch")
            repository_copy = isolate_skill_path(
                inventory, "watch", expected_path=canonical_skill
            )
            personal_copy = isolate_skill_path(
                inventory, "watch", expected_path=personal_skill
            )

        self.assertEqual(
            {(entry.scope, entry.skill_root) for entry in inventory.entries},
            {("repository", canonical_skill), ("personal", personal_skill)},
        )
        self.assertEqual(ambiguous.status, "path_required")
        self.assertIsNone(ambiguous.selected_path)
        self.assertEqual(repository_copy.status, "isolated")
        self.assertEqual(repository_copy.selected_path, canonical_skill)
        self.assertEqual(personal_copy.status, "isolated")
        self.assertEqual(personal_copy.selected_path, personal_skill)


if __name__ == "__main__":
    unittest.main()
