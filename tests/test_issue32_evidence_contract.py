from __future__ import annotations

import json
from pathlib import Path
import unittest

from issue32_support import validate_evidence_record


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_RECORD = REPOSITORY_ROOT / "docs" / "verification" / "issue-32-evidence.json"


class Issue32EvidenceContractTests(unittest.TestCase):
    def test_committed_record_is_a_truthful_partial_live_evidence_card(self) -> None:
        record = json.loads(EVIDENCE_RECORD.read_text(encoding="utf-8"))

        self.assertEqual(validate_evidence_record(record), ())
        self.assertEqual(record["issue"], 32)
        self.assertEqual(record["outcome"], "PASS")
        self.assertEqual(record["coverage"], "partial")
        self.assertEqual(record["qualification"]["L-01"], "PASS")
        self.assertEqual(record["caption_run"]["coverage"], "partial")
        self.assertEqual(record["visual_run"]["coverage"], "none")
        self.assertEqual(record["visual_run"]["frames"], [])
        self.assertFalse(record["side_effect_assertions"]["provider_contact"])
        self.assertFalse(record["side_effect_assertions"]["audio_upload"])
        self.assertFalse(record["side_effect_assertions"]["credential_read"])

    def test_rejects_a_caption_pass_without_jit_approval_and_bounded_artifact(self) -> None:
        record = json.loads(EVIDENCE_RECORD.read_text(encoding="utf-8"))
        record["caption_run"]["caption_network_approval"] = "not_observed"
        record["caption_run"]["artifact"]["size_bytes"] = 4 * 1024 * 1024 + 1
        record["caption_run"]["purpose"] = "unknown"
        record["caption_run"]["media_download_completed"] = True

        errors = validate_evidence_record(record)

        self.assertIn("caption_run requires approved caption_network_approval", errors)
        self.assertIn("caption_run artifact exceeds caption byte cap", errors)
        self.assertIn("caption_run has invalid purpose", errors)
        self.assertIn("caption_run media_download_completed must be false", errors)

    def test_rejects_visual_claims_without_frames_and_nonredacted_receipts(self) -> None:
        record = json.loads(EVIDENCE_RECORD.read_text(encoding="utf-8"))
        record["visual_run"]["claims"] = ["An uninspected frame shows a UI."]
        record["caption_run"]["receipt"] = "caption_receipt_should_not_be_committed"

        errors = validate_evidence_record(record)

        self.assertIn("visual_run has claims without inspected frames", errors)
        self.assertIn("record contains forbidden field receipt", errors)

    def test_rejects_a_record_that_turns_the_403_visual_result_into_a_pass(self) -> None:
        record = json.loads(EVIDENCE_RECORD.read_text(encoding="utf-8"))
        record["visual_run"]["coverage"] = "complete"
        record["visual_run"]["outcome"] = "PASS"
        record["visual_run"]["frames"] = [{"path": "frame.jpg"}]

        errors = validate_evidence_record(record)

        self.assertIn("visual_run 403 outcome must retain none coverage", errors)
        self.assertIn("visual_run 403 outcome must not claim frames", errors)

    def test_rejects_an_l01_pass_without_required_observed_context(self) -> None:
        record = json.loads(EVIDENCE_RECORD.read_text(encoding="utf-8"))
        record.pop("test_id")
        record.pop("environment")
        record.pop("trace")
        record["source"].pop("video_id")
        record["qualification"]["L-01"] = "BLOCKED"

        errors = validate_evidence_record(record)

        self.assertIn("missing test_id", errors)
        self.assertIn("environment must be an object", errors)
        self.assertIn("trace must be a non-empty list", errors)
        self.assertIn("source has invalid video_id", errors)
        self.assertIn("qualification L-01 must be PASS", errors)


if __name__ == "__main__":
    unittest.main()
