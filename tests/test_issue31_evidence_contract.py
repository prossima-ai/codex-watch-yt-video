from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from issue31_support import ROW_IDS, validate_evidence_record


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_RECORD = REPOSITORY_ROOT / "docs" / "verification" / "issue-31-evidence.json"
PINNED_BASE = "ebcd7f30e49505bd2b94367f495b03fde789de8f"
SPECIFICATION_REVISION = "9d9eea698b4eda09a435f1b198c606e7058033a6"
PACKAGE_TREE = "d678b0774e51f3f84aff349c90b201350e756e1e"
SKILL_SHA256 = "8f1e4240ce682d2d33f142f1ccc790a0db8f36e97d1fffdee04e0b6eb50ffaf2"
MANIFEST_SHA256 = "cfbacf0277d0d56a32111d8493efe31095996f383714cea565a284257d82600d"
FIXTURE_WORKTREE = "/tmp/issue31-worktree"
FIXTURE_NEUTRAL_DIRECTORY = "/tmp/issue31-neutral"
REPOSITORY_SKILL = f"{FIXTURE_WORKTREE}/.agents/skills/watch/SKILL.md"
PERSONAL_SKILL = "/Users/fixture/.agents/skills/watch/SKILL.md"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def implementation_revision_exists(revision: str) -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def _task(
    task_id: str,
    *,
    title: str,
    selected_skill_path: str | None,
    primary_folder: str = FIXTURE_WORKTREE,
) -> dict[str, object]:
    skill_root = (
        selected_skill_path.rsplit("/SKILL.md", 1)[0] if selected_skill_path else None
    )
    return {
        "id": task_id,
        "title": title,
        "primary_folder": primary_folder,
        "fresh_target_macos_desktop": True,
        "inventory_path": selected_skill_path,
        "displayed_alias": "watch" if selected_skill_path else None,
        "selected_skill_path": selected_skill_path,
        "script_path": (
            f"{skill_root}/scripts/prepare_visual.py"
            if skill_root is not None
            else None
        ),
        "sanitized_prompt": "Inspect the supplied lawful local fixture without network access.",
        "command_trace": "Recorded sanitized task trace.",
    }


def _row(
    task_refs: list[str],
    selected_paths: list[str],
) -> dict[str, object]:
    return {
        "normative_meaning": "Actual target-macOS Desktop qualification.",
        "outcome": "PASS",
        "proof_scope": "target_macos_desktop",
        "task_refs": task_refs,
        "selected_skill_paths": selected_paths,
        "sanitized_stimulus": "A lawful synthetic local fixture.",
        "trace": "Observed in a fresh target-macOS Desktop task.",
        "approval_decisions": [
            {
                "category": "local_fixture",
                "decision": "not_required",
                "pre_check": "Fixture was local and controlled.",
                "post_check": "No authority was added.",
            }
        ],
        "side_effect_checks": {
            "public_media_contact": False,
            "source_host_dns_http_request": False,
            "native_caption_request": False,
            "provider_contact": False,
            "credential_read": False,
            "audio_upload": False,
            "outside_workspace_write_succeeded": False,
            "unrelated_user_file_mutation": False,
        },
        "artifacts": [{"id": "sanitized-task-record", "sha256": "a" * 64}],
        "limitations": ["The evidence is limited to the stated Desktop row."],
        "qualification_basis": ["actual_target_macos_desktop_task"],
    }


def complete_record() -> dict[str, object]:
    tasks = [
        _task(
            "task-d01",
            title="Issue31 D01 repository discovery",
            selected_skill_path=REPOSITORY_SKILL,
        ),
        _task(
            "task-d02",
            title="Issue31 D02 personal discovery",
            selected_skill_path=PERSONAL_SKILL,
            primary_folder=FIXTURE_NEUTRAL_DIRECTORY,
        ),
        _task(
            "task-d03-explicit",
            title="Issue31 D03 explicit trigger",
            selected_skill_path=REPOSITORY_SKILL,
        ),
        _task(
            "task-d03-implicit",
            title="Issue31 D03 implicit trigger",
            selected_skill_path=REPOSITORY_SKILL,
        ),
        _task(
            "task-d03-near-miss",
            title="Issue31 D03 near-miss control",
            selected_skill_path=None,
        ),
        _task(
            "task-d03-negative",
            title="Issue31 D03 negative control",
            selected_skill_path=None,
        ),
        _task(
            "task-d03-reload",
            title="Issue31 D03 fresh-task reload",
            selected_skill_path=REPOSITORY_SKILL,
        ),
        _task(
            "task-d04",
            title="Issue31 D04 offline authority and frame fallback",
            selected_skill_path=REPOSITORY_SKILL,
        ),
    ]
    rows = {
        "D-01": _row(["task-d01"], [REPOSITORY_SKILL]),
        "D-02": _row(["task-d02"], [PERSONAL_SKILL]),
        "D-03": _row(
            [
                "task-d03-explicit",
                "task-d03-implicit",
                "task-d03-near-miss",
                "task-d03-negative",
                "task-d03-reload",
            ],
            [REPOSITORY_SKILL],
        ),
        "D-04": _row(["task-d04"], [REPOSITORY_SKILL]),
    }
    rows["D-02"]["existing_target_refusal"] = {
        "target_identity_before": "b" * 64,
        "target_identity_after": "b" * 64,
        "target_sha256_before": "c" * 64,
        "target_sha256_after": "c" * 64,
        "refused": True,
    }
    rows["D-02"]["refusals"] = [
        "Neutral target path provisioning was refused because the personal symlink path already exists."
    ]
    rows["D-02"]["refusal_reasons"] = [
        "Existing personal symlink was detected and must not be clobbered in the neutral-path protection run.",
        "No host-level symlink target mutation was observed before or after the preflight refusal.",
    ]
    rows["D-02"]["side_effect_checks"] = {
        "observed": False,
        "public_media_contact": False,
        "source_host_dns_http_request": False,
        "native_caption_request": False,
        "provider_contact": False,
        "credential_read": False,
        "audio_upload": False,
        "outside_workspace_write_succeeded": False,
        "unrelated_user_file_mutation": False,
        "pre_checks": {
            "neutral_path_exists": True,
            "neutral_path_has_no_repository_copy": True,
            "personal_symlink_literal_exists": True,
            "personal_symlink_target_recorded": True,
        },
        "post_checks": {
            "personal_symlink_target_unchanged": True,
            "personal_symlink_literal_unchanged": True,
            "personal_symlink_parent_unchanged": True,
            "no_new_clobber_artifacts": True,
        },
    }
    rows["D-03"]["trigger_controls"] = {
        "explicit": {"task_ref": "task-d03-explicit", "selected_watch": True},
        "implicit": {"task_ref": "task-d03-implicit", "selected_watch": True},
        "near_miss": {
            "task_ref": "task-d03-near-miss",
            "selected_watch": False,
            "watch_script_started": False,
            "network_activity": False,
            "media_process_started": False,
            "long_running_work": False,
        },
        "negative": {
            "task_ref": "task-d03-negative",
            "selected_watch": False,
            "watch_script_started": False,
            "network_activity": False,
            "media_process_started": False,
            "long_running_work": False,
        },
    }
    rows["D-03"]["duplicate_paths"] = {
        "repository": REPOSITORY_SKILL,
        "personal": PERSONAL_SKILL,
        "path_isolated": True,
    }
    rows["D-03"]["reload"] = {
        "original_sha256": MANIFEST_SHA256,
        "probe_sha256": "d" * 64,
        "restored_sha256": MANIFEST_SHA256,
        "patch_sha256": "e" * 64,
        "new_task_ref": "task-d03-reload",
        "restart_count": 0,
        "in_task_refresh_proved": False,
        "disclaimer": (
            "This proves discovery/reload in a newly constructed task inventory. "
            "It does not prove refresh inside an already-open task."
        ),
    }
    rows["D-04"]["authority_checks"] = {
        "offline": {
            "bundled_runtime": True,
            "inspected_frame_count": 1,
            "visual_claim_for_unseen_frame": False,
        },
        "network_denial": {
            "source": "https://video.example/issue31-network-denial",
            "source_network_approved": False,
            "state": "stopped",
            "stage": "metadata",
            "category": "network_approval_required",
            "attempt_count": 0,
            "dns_http_activity": False,
        },
        "outside_workspace_write_denial": {
            "sentinel_path": "/tmp/issue31-sentinel",
            "target_existed_before": False,
            "target_exists_after": False,
            "parent_unchanged": True,
            "fallback_target_exists": False,
        },
        "local_frame_fallback": {
            "fixture_path": f"{FIXTURE_WORKTREE}/.issue31/frame.jpg",
            "successful_inspection_before": True,
            "failure_induced": True,
            "visual_observation_created": False,
            "visual_claim_made": False,
            "original_sha256": "f" * 64,
            "restored_sha256": "f" * 64,
            "original_mode": "0644",
            "restored_mode": "0644",
        },
    }
    return {
        "schema_version": "issue31-evidence-v1",
        "issue": 31,
        "recorded_at_utc": "2026-08-16T00:00:00Z",
        "base_revision": PINNED_BASE,
        "implementation_revision": PINNED_BASE,
        "specification_revision": SPECIFICATION_REVISION,
        "package": {
            "tree": PACKAGE_TREE,
            "key_file_sha256": {
                "SKILL.md": SKILL_SHA256,
                "agents/openai.yaml": MANIFEST_SHA256,
            },
        },
        "environment": {
            "host": {"os": "macOS fixture", "architecture": "arm64"},
            "desktop": {
                "observed": True,
                "version": "fixture desktop",
                "bundle": "fixture bundle",
            },
            "tools": {
                "codex_cli": "fixture codex",
                "python": "fixture python",
                "yt_dlp": "fixture yt-dlp",
                "ffmpeg": "fixture ffmpeg",
                "ffprobe": "fixture ffprobe",
            },
        },
        "paths": {
            "repository": f"{FIXTURE_WORKTREE}/.agents/skills/watch",
            "personal": {
                "literal": "/Users/fixture/.agents/skills/watch",
                "resolved": "/Users/fixture/durable_repository/.agents/skills/watch",
                "revision": PINNED_BASE,
                "tree": PACKAGE_TREE,
                "key_file_sha256": {
                    "SKILL.md": SKILL_SHA256,
                    "agents/openai.yaml": MANIFEST_SHA256,
                },
            },
        },
        "task_plan": [
            {
                "title": task["title"],
                "primary_folder": task["primary_folder"],
                "sanitized_prompt": task["sanitized_prompt"],
                "expected_writes": "Only a runtime-owned workspace or controlled fixture.",
                "intended_evidence": "Target-Desktop observation only.",
            }
            for task in tasks
        ],
        "tasks": tasks,
        "fixture": {
            "kind": "synthetic_local",
            "generation_command": "recorded local synthetic generation command",
            "mp4_sha256": "1" * 64,
            "jpeg_sha256": "2" * 64,
        },
        "supporting_checks": [
            {
                "name": "evidence-contract tests",
                "command": "fixture command",
                "exit_code": 0,
                "count": "fixture count",
                "outcome": "PASS",
                "scope": "static_integrity_only",
                "trace": "The validator does not prove Desktop behavior.",
                "limitations": ["Static integrity only."],
            },
            {
                "name": "D-02 personal target refusal preflight",
                "command": "fixture command",
                "exit_code": 0,
                "count": "1 local preflight run",
                "outcome": "PASS",
                "scope": "static_integrity_only",
                "trace": "Personal symlink path already existed in the host pathing namespace; refusal to clobber preserved the symlink target and did not perform any replacement action.",
                "limitations": [
                    "This is a local host-side preflight check and does not prove a target-Desktop refusal decision."
                ],
            },
        ],
        "side_effect_assertions": {
            "host_audit_available": True,
            "public_media_contact": False,
            "source_host_dns_http_request": False,
            "native_caption_request": False,
            "provider_contact": False,
            "credential_read": False,
            "audio_upload": False,
            "outside_workspace_write_succeeded": False,
            "unrelated_user_file_mutation": False,
        },
        "reviews": {"standards": "PASS", "spec": "PASS"},
        "unproven": [
            "public media",
            "caption networking",
            "providers",
            "credentials",
            "uploads",
            "live cleanup",
            "in-task refresh",
            "release readiness",
        ],
        "rows": rows,
    }


class Issue31EvidenceContractTests(unittest.TestCase):
    def test_complete_passing_fixture_is_valid(self) -> None:
        self.assertEqual(validate_evidence_record(complete_record()), ())

    def test_rejects_missing_rows_invalid_outcomes_and_non_desktop_scope(self) -> None:
        record = complete_record()
        del record["rows"]["D-04"]
        record["rows"]["D-01"]["outcome"] = "MAYBE"
        record["rows"]["D-02"]["proof_scope"] = "hermetic"

        errors = validate_evidence_record(record)

        self.assertEqual(ROW_IDS, ("D-01", "D-02", "D-03", "D-04"))
        self.assertIn("row D-01 has invalid outcome", errors)
        self.assertIn("row D-02 has invalid proof_scope", errors)
        self.assertIn("missing row D-04", errors)

    def test_rejects_unknown_revisions_and_stale_personal_package_hashes(self) -> None:
        record = complete_record()
        record["implementation_revision"] = "0" * 40
        record["paths"]["personal"]["key_file_sha256"]["SKILL.md"] = "0" * 64

        errors = validate_evidence_record(
            record, implementation_revision_exists=lambda _revision: False
        )

        self.assertIn("unknown implementation_revision", errors)
        self.assertIn("personal package key_file_sha256 does not match package", errors)

    def test_rejects_stale_personal_revision_for_an_otherwise_passing_d02(self) -> None:
        record = complete_record()
        record["paths"]["personal"]["revision"] = "0" * 40

        errors = validate_evidence_record(record)

        self.assertIn("personal package revision does not match implementation_revision", errors)

    def test_rejects_missing_or_duplicate_actual_task_identity_and_selected_paths(self) -> None:
        record = complete_record()
        record["tasks"][1]["id"] = "task-d01"
        record["rows"]["D-01"]["task_refs"] = []
        record["rows"]["D-02"]["selected_skill_paths"] = []

        errors = validate_evidence_record(record)

        self.assertIn("duplicate task id at index 1", errors)
        self.assertIn("row D-01 needs actual task_refs for PASS or FAIL", errors)
        self.assertIn("row D-02 needs selected_skill_paths for PASS or FAIL", errors)

    def test_rejects_task_fields_unbound_from_the_selected_skill(self) -> None:
        record = complete_record()
        record["tasks"][0]["inventory_path"] = "/tmp/other/SKILL.md"
        record["tasks"][1]["script_path"] = "/private/tmp/unrelated.py"
        record["tasks"][2]["displayed_alias"] = "other"

        errors = validate_evidence_record(record)

        self.assertIn(
            "task 0 inventory_path does not match selected_skill_path", errors
        )
        self.assertIn("task 1 script_path is not a bundled script", errors)
        self.assertIn("task 2 has an invalid displayed_alias", errors)

    def test_rejects_missing_decisions_blank_evidence_and_malformed_artifact_hashes(self) -> None:
        record = complete_record()
        record["rows"]["D-01"]["approval_decisions"] = []
        record["rows"]["D-02"]["trace"] = ""
        record["rows"]["D-03"]["limitations"] = []
        record["rows"]["D-04"]["artifacts"] = [{"id": "task", "sha256": "bad"}]

        errors = validate_evidence_record(record)

        self.assertIn("row D-01 has no approval_decisions", errors)
        self.assertIn("row D-02 has no trace", errors)
        self.assertIn("row D-03 has invalid limitations", errors)
        self.assertIn("row D-04 artifact 0 has invalid sha256", errors)

    def test_rejects_incomplete_static_check_execution_details(self) -> None:
        record = complete_record()
        check = record["supporting_checks"][0]
        check["command"] = ""
        check["exit_code"] = "zero"
        check["limitations"] = []

        errors = validate_evidence_record(record)

        self.assertIn("supporting_check 0 has invalid command", errors)
        self.assertIn("supporting_check 0 has invalid exit_code", errors)
        self.assertIn("supporting_check 0 has invalid limitations", errors)

    def test_rejects_static_proof_in_task_refresh_and_unrestored_metadata_probe(self) -> None:
        record = complete_record()
        record["rows"]["D-01"]["qualification_basis"] = [
            "unit_tests",
            "prior_issue",
        ]
        record["rows"]["D-03"]["reload"]["in_task_refresh_proved"] = True
        record["rows"]["D-03"]["reload"]["restart_count"] = 2
        record["rows"]["D-03"]["reload"]["restored_sha256"] = "0" * 64

        errors = validate_evidence_record(record)

        self.assertIn("row D-01 PASS has no actual Desktop qualification basis", errors)
        self.assertIn("row D-03 claims in-task refresh", errors)
        self.assertIn("row D-03 has more than one restart", errors)
        self.assertIn("row D-03 metadata probe was not restored", errors)

    def test_rejects_inconsistent_denials_and_visual_fallback_claims(self) -> None:
        record = complete_record()
        authority = record["rows"]["D-04"]["authority_checks"]
        authority["network_denial"]["attempt_count"] = 1
        authority["outside_workspace_write_denial"]["target_exists_after"] = True
        authority["local_frame_fallback"]["visual_claim_made"] = True
        authority["local_frame_fallback"]["restored_sha256"] = "0" * 64

        errors = validate_evidence_record(record)

        self.assertIn("row D-04 network denial has outbound activity", errors)
        self.assertIn("row D-04 denied write created a target", errors)
        self.assertIn("row D-04 fallback made a visual claim", errors)
        self.assertIn("row D-04 frame fixture was not restored", errors)

    def test_requires_desktop_and_audit_prerequisites_for_each_passing_row(self) -> None:
        record = complete_record()
        record["environment"]["desktop"] = {
            "observed": False,
            "version": None,
            "bundle": None,
            "limitation": "fixture",
        }
        record["side_effect_assertions"]["host_audit_available"] = False
        record["reviews"] = {"standards": "UNVERIFIED", "spec": "UNVERIFIED"}
        for row_id in ("D-01", "D-02", "D-03"):
            record["rows"][row_id]["outcome"] = "BLOCKED"
            record["rows"][row_id]["blocker"] = "fixture blocker"

        errors = validate_evidence_record(record)

        self.assertIn("PASS rows require observed Desktop version and bundle", errors)
        self.assertIn("PASS rows require host-audited side-effect checks", errors)
        self.assertIn("PASS rows require passing independent reviews", errors)

    def test_rejects_a_non_reserved_network_denial_source(self) -> None:
        record = complete_record()
        record["rows"]["D-04"]["authority_checks"]["network_denial"]["source"] = (
            "https://public.example/not-a-reserved-denial"
        )

        errors = validate_evidence_record(record)

        self.assertIn("row D-04 has an unexpected network denial source", errors)

    def test_rejects_any_recorded_public_media_or_provider_activity(self) -> None:
        record = complete_record()
        record["side_effect_assertions"]["public_media_contact"] = True
        record["side_effect_assertions"]["provider_contact"] = True

        errors = validate_evidence_record(record)

        self.assertIn("side_effect_assertions must keep public_media_contact false", errors)
        self.assertIn("side_effect_assertions must keep provider_contact false", errors)

    def test_rejects_network_or_process_activity_in_a_near_miss_control(self) -> None:
        record = complete_record()
        control = record["rows"]["D-03"]["trigger_controls"]["near_miss"]
        control["network_activity"] = True
        control["media_process_started"] = True
        control["long_running_work"] = True

        errors = validate_evidence_record(record)

        self.assertIn("row D-03 near_miss control has network activity", errors)
        self.assertIn("row D-03 near_miss control started a media process", errors)
        self.assertIn("row D-03 near_miss control started long-running work", errors)

    def test_rejects_sensitive_values_and_forbidden_raw_evidence_fields(self) -> None:
        record = complete_record()
        record["tasks"][0]["sanitized_prompt"] = (
            "https://video.example/issue31?signature=should-not-appear"
        )
        record["tasks"][1]["command_trace"] = "Authorization: Bearer secret"
        record["tasks"][2]["raw_task_transcript"] = "unredacted task transcript"
        record["tasks"][3]["caption_receipt"] = "opaque receipt"
        record["rows"]["D-04"]["Cookie"] = "session=not-allowed"
        record["tasks"][4]["https://video.example/?signature=not-allowed"] = "value"
        record["environment"]["environment_dump"] = "OPENAI_API_KEY=not-allowed"

        errors = validate_evidence_record(record)

        self.assertTrue(any("sensitive" in error for error in errors), errors)
        self.assertTrue(any("forbidden raw evidence field" in error for error in errors), errors)

    def test_rejects_secret_bearing_free_text(self) -> None:
        values = (
            "AWS_SESSION_TOKEN=fixture-value",
            "OPENAI_API_KEY=fixture-value",
            "JWT=fixture-value",
            "Cookie=fixture-session-value",
            "Bearer eyJ.fixture.payload",
            "eyJfixture.payload.signature",
            "X-API-Key: fixture-value",
            "https%3A%2F%2Fcaptions.example%2Fsubtitles.vtt%3Fsignature=fixture",
            "//captions.example/subtitles.vtt?signature=fixture",
        )

        for value in values:
            with self.subTest(value=value):
                record = complete_record()
                record["rows"]["D-01"]["trace"] = value

                errors = validate_evidence_record(record)

                self.assertTrue(any("sensitive value" in error for error in errors), errors)

    def test_rejects_normalized_sensitive_field_name_variants(self) -> None:
        variants = (".env", "dotenv_contents", "captionReceipt", "session_cookie")

        for field_name in variants:
            with self.subTest(field_name=field_name):
                record = complete_record()
                record["tasks"][0][field_name] = "not-allowed"

                errors = validate_evidence_record(record)

                self.assertTrue(
                    any("forbidden raw evidence field" in error for error in errors),
                    errors,
                )

    def test_rejects_compact_sensitive_field_name_variants_outside_tasks(self) -> None:
        variants = (
            "credentialread",
            "approvalreceipt",
            "rawtranscript",
            "environmentdump",
            "sessioncookie",
            "captionreceipt",
        )

        for field_name in variants:
            with self.subTest(field_name=field_name):
                record = complete_record()
                record["rows"]["D-01"][field_name] = "opaque-recorded-value"

                errors = validate_evidence_record(record)

                self.assertTrue(
                    any("forbidden raw evidence field" in error for error in errors),
                    errors,
                )

    def test_rejects_credential_field_name_variants(self) -> None:
        variants = (
            "authorization",
            "apiKey",
            "apikey",
            "access_token",
            "shared_secret",
            "secretKey",
            "credential",
            "credentials",
            "privateKey",
            "password",
            "caption_url",
            "CAPTIONURL",
            "credentialed_caption_url",
        )

        for field_name in variants:
            with self.subTest(field_name=field_name):
                record = complete_record()
                record["tasks"][0][field_name] = "https://captions.example/subtitles.vtt"

                errors = validate_evidence_record(record)

                self.assertTrue(
                    any("forbidden raw evidence field" in error for error in errors),
                    errors,
                )

    def test_only_allows_credential_read_as_a_scoped_false_boolean(self) -> None:
        record = complete_record()
        record["side_effect_assertions"]["credential_read"] = "opaque-recorded-secret"
        record["rows"]["D-01"]["credential_read"] = "opaque-recorded-secret"

        errors = validate_evidence_record(record)

        self.assertTrue(any("forbidden raw evidence field" in error for error in errors), errors)

    def test_diagnostics_do_not_echo_untrusted_evidence_identifiers(self) -> None:
        hostile = "https://captions.example/subtitles.vtt?signature=fixture"
        record = complete_record()
        record["rows"]["D-01"][hostile] = "opaque"
        record["tasks"][1]["id"] = hostile
        record["rows"]["D-01"]["task_refs"] = [hostile]
        record["rows"]["D-04"]["artifacts"][0]["id"] = hostile
        record["rows"]["D-04"]["artifacts"][0]["sha256"] = "bad"
        record["rows"][hostile] = {}

        errors = validate_evidence_record(record)

        self.assertTrue(errors)
        self.assertTrue(all(hostile not in error for error in errors), errors)

    def test_rejects_unknown_task_record_fields(self) -> None:
        record = complete_record()
        record["tasks"][0]["unreviewed_extension"] = "not-allowed"

        errors = validate_evidence_record(record)

        self.assertIn("task 0 has unsupported fields", errors)

    def test_rejects_placeholder_paths_in_observed_evidence(self) -> None:
        record = complete_record()
        record["paths"]["repository"] = "$ISSUE31_WORKTREE/.agents/skills/watch"
        record["paths"]["personal"]["literal"] = "$HOME/.agents/skills/watch"
        record["tasks"][0]["primary_folder"] = "$ISSUE31_WORKTREE"
        record["rows"]["D-04"]["authority_checks"][
            "outside_workspace_write_denial"
        ]["sentinel_path"] = "$ISSUE31_SENTINEL"
        record["rows"]["D-04"]["authority_checks"]["local_frame_fallback"][
            "fixture_path"
        ] = "$ISSUE31_WORKTREE/.issue31/frame.jpg"

        errors = validate_evidence_record(record)

        self.assertIn("paths has a placeholder repository", errors)
        self.assertIn("personal has a placeholder literal", errors)
        self.assertIn("task 0 has a placeholder primary_folder", errors)
        self.assertIn("row D-04 has a placeholder denied write sentinel", errors)
        self.assertIn("row D-04 has a placeholder fallback fixture path", errors)

    def test_uses_outcome_neutral_diagnostics_for_a_failing_desktop_row(self) -> None:
        record = complete_record()
        record["rows"]["D-01"]["outcome"] = "FAIL"
        record["rows"]["D-01"]["task_refs"] = []

        errors = validate_evidence_record(record)

        self.assertIn("row D-01 needs actual task_refs for PASS or FAIL", errors)

    def test_labels_missing_desktop_prerequisites_for_a_failing_row_as_failures(self) -> None:
        record = complete_record()
        record["rows"]["D-01"]["outcome"] = "FAIL"
        for row_id in ("D-02", "D-03", "D-04"):
            record["rows"][row_id]["outcome"] = "BLOCKED"
            record["rows"][row_id]["blocker"] = "fixture blocker"
        record["environment"]["desktop"] = {
            "observed": False,
            "version": None,
            "bundle": None,
            "limitation": "fixture",
        }

        errors = validate_evidence_record(record)

        self.assertIn("FAIL rows require observed Desktop version and bundle", errors)

    def test_committed_record_is_truthful_and_binds_the_current_package(self) -> None:
        record = json.loads(EVIDENCE_RECORD.read_text(encoding="utf-8"))

        self.assertEqual(
            validate_evidence_record(
                record, implementation_revision_exists=implementation_revision_exists
            ),
            (),
        )
        self.assertEqual(record["base_revision"], PINNED_BASE)
        self.assertEqual(record["specification_revision"], SPECIFICATION_REVISION)
        self.assertEqual(record["package"]["tree"], PACKAGE_TREE)
        self.assertEqual(record["rows"].keys(), set(ROW_IDS))
        self.assertTrue(all(row["outcome"] == "BLOCKED" for row in record["rows"].values()))
        self.assertEqual(record["tasks"], [])
        self.assertEqual(
            record["package"]["key_file_sha256"]["SKILL.md"],
            sha256_file(REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "SKILL.md"),
        )
        self.assertEqual(
            record["package"]["key_file_sha256"]["agents/openai.yaml"],
            sha256_file(
                REPOSITORY_ROOT
                / ".agents"
                / "skills"
                / "watch"
                / "agents"
                / "openai.yaml"
            ),
        )


if __name__ == "__main__":
    unittest.main()
