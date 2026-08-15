from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from issue30_synthetic_media import canonical_json_bytes
from issue30_support import ROW_IDS, validate_evidence_record


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_RECORD = REPO_ROOT / "docs" / "verification" / "issue-30-evidence.json"
S04_REVIEW_RECORD = REPO_ROOT / "docs" / "verification" / "issue-30-s04-review.json"


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
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def complete_record() -> dict[str, object]:
    rows = {
        row_id: {
            "normative_meaning": f"Independent qualification for {row_id}.",
            "outcome": "PASS",
            "proof_scope": "hermetic" if row_id.startswith("H-") else "synthetic",
            "trace": f"offline fixture trace for {row_id}",
            "approval_status": "not_required_offline",
            "tests": [f"test_{row_id.lower().replace('-', '_')}"],
            "artifacts": [{"id": f"artifact-{row_id}", "sha256": "d" * 64}],
            "limits": ["No live source, provider, Desktop, or approval behavior is proved."],
        }
        for row_id in ROW_IDS
    }
    return {
        "schema_version": "issue30-evidence-v1",
        "issue": 30,
        "base_revision": "dcf58a30090c56a9ee04addf4d706a5a85815133",
        "implementation_revision": "b" * 40,
        "specification_revision": "dcf58a30090c56a9ee04addf4d706a5a85815133",
        "scope": {
            "classification": "offline fixture qualification",
            "live_activity": False,
            "closure_rows": list(ROW_IDS),
        },
        "environment": {
            "os": "fixture os",
            "python": "fixture python",
            "yt_dlp": "fixture yt-dlp",
            "ffmpeg": "fixture ffmpeg",
            "ffprobe": "fixture ffprobe",
        },
        "commands": [
            {
                "command": "fixture command",
                "result": "PASS: fixture",
                "scope": "fixture scope",
            }
        ],
        "reviews": {"standards": "UNVERIFIED", "spec": "UNVERIFIED"},
        "rows": rows,
    }


class Issue30EvidenceContractTests(unittest.TestCase):
    def test_rejects_a_record_that_omits_current_qualification_rows(self) -> None:
        record = {
            "schema_version": "issue30-evidence-v1",
            "base_revision": "a" * 40,
            "implementation_revision": "b" * 40,
            "specification_revision": "c" * 40,
            "rows": {"H-01": {"outcome": "PASS"}},
        }

        errors = validate_evidence_record(record)

        self.assertEqual(ROW_IDS[0], "H-01")
        self.assertIn("missing row H-02", errors)
        self.assertIn("missing row S-04", errors)

    def test_rejects_wrong_base_overclaimed_scope_and_missing_artifact_hash(self) -> None:
        record = complete_record()
        record["base_revision"] = "f" * 40
        rows = record["rows"]
        rows["H-09"]["proof_scope"] = "live"
        rows["S-04"]["artifacts"] = [{"id": "review-output"}]

        errors = validate_evidence_record(record)

        self.assertIn("unexpected base_revision", errors)
        self.assertIn("row H-09 has invalid proof_scope", errors)
        self.assertIn("row S-04 artifact review-output has invalid sha256", errors)

    def test_rejects_blank_artifact_ids_live_scope_and_unknown_implementation(self) -> None:
        record = complete_record()
        record["rows"]["H-01"]["artifacts"] = [{"id": "", "sha256": "d" * 64}]
        record["scope"]["live_activity"] = True

        errors = validate_evidence_record(
            record, implementation_revision_exists=lambda _revision: False
        )

        self.assertIn("row H-01 has an artifact with invalid id", errors)
        self.assertIn("scope must declare live_activity false", errors)
        self.assertIn("unknown implementation_revision", errors)

    def test_committed_record_is_complete_pinned_and_keeps_s04_review_blind(self) -> None:
        record = json.loads(EVIDENCE_RECORD.read_text(encoding="utf-8"))
        review = json.loads(S04_REVIEW_RECORD.read_text(encoding="utf-8"))

        self.assertEqual(
            validate_evidence_record(
                record, implementation_revision_exists=implementation_revision_exists
            ),
            (),
        )
        self.assertEqual(record["issue"], 30)
        self.assertFalse(record["scope"]["live_activity"])
        self.assertEqual(
            record["h09_h11_reconciliation"]["h11"],
            "non_regression_only_not_an_issue30_closure_row",
        )
        self.assertEqual(
            record["rows"]["H-01"]["artifacts"][0]["sha256"],
            sha256_file(REPO_ROOT / "tests" / "test_issue30_hermetic_qualification.py"),
        )

        self.assertTrue(implementation_revision_exists(record["implementation_revision"]))

        self.assertEqual(review["result"], "PASS")
        self.assertEqual(review["review_output"]["verdict"], "SUPPORTS")
        self.assertEqual(
            review["review_output_sha256"],
            hashlib.sha256(canonical_json_bytes(review["review_output"])).hexdigest(),
        )
        self.assertEqual(
            review["reviewer_visible_context"],
            {
                "candidate_claim": "At the cited time, the frame shows a blue field with a centered brighter blue rectangle.",
                "frame_id": "frame-001",
                "source_absolute_time_seconds": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
