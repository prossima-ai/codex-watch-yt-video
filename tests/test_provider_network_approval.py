from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from watch_provider_network import (  # noqa: E402
    ProviderNetworkApprovalDecision,
    ProviderNetworkApprovalReceiptError,
    ProviderNetworkApprovalRegistry,
    ProviderNetworkBinding,
)


class ProviderNetworkApprovalRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 100.0
        self.registry = ProviderNetworkApprovalRegistry(
            clock=lambda: self.now,
            receipt_factory=lambda: "provider_receipt_test",
        )
        self.binding = ProviderNetworkBinding(
            action="transcribe_selected_audio",
            watch_request_id="provider_request_1",
            source_value="https://video.example/watch?v=one",
            session_id="provider_session_1",
            workspace_id="workspace_1",
            provider="openai",
            model="whisper-1",
            destination="https://api.openai.example/v1/audio/transcriptions",
            selected_audio_track_id="audio_track_1",
            request_limit_bytes=20_000_000,
            retry_budget=3,
        )

    def test_receipt_is_single_use_and_bound_to_every_disclosed_fact(self) -> None:
        binding_fields = (
            "watch_request_id",
            "source_value",
            "session_id",
            "workspace_id",
            "provider",
            "model",
            "destination",
            "selected_audio_track_id",
            "request_limit_bytes",
            "retry_budget",
        )
        for field in binding_fields:
            with self.subTest(field=field):
                prompt = self.registry.issue(self.binding)
                changed = replace(
                    self.binding,
                    **{
                        field: (
                            getattr(self.binding, field) + 1
                            if isinstance(getattr(self.binding, field), int)
                            else getattr(self.binding, field) + "_changed"
                        )
                    },
                )
                with self.assertRaises(ProviderNetworkApprovalReceiptError) as rejected:
                    self.registry.verify_and_consume(
                        ProviderNetworkApprovalDecision(prompt.receipt, "approved"),
                        changed,
                    )
                self.assertEqual(rejected.exception.code, "invalid_receipt")
                with self.assertRaises(ProviderNetworkApprovalReceiptError):
                    self.registry.verify_and_consume(
                        ProviderNetworkApprovalDecision(prompt.receipt, "approved"),
                        self.binding,
                    )

    def test_expired_denied_and_canceled_receipts_cannot_be_reused(self) -> None:
        expired = self.registry.issue(self.binding)
        self.now += 5 * 60
        with self.assertRaises(ProviderNetworkApprovalReceiptError) as rejected:
            self.registry.verify_and_consume(
                ProviderNetworkApprovalDecision(expired.receipt, "approved"),
                self.binding,
            )
        self.assertEqual(rejected.exception.code, "expired_receipt")

        for decision in ("declined", "canceled"):
            with self.subTest(decision=decision):
                prompt = self.registry.issue(self.binding)
                verified = self.registry.verify_and_consume(
                    ProviderNetworkApprovalDecision(prompt.receipt, decision),
                    self.binding,
                )
                self.assertEqual(verified.decision, decision)
                with self.assertRaises(ProviderNetworkApprovalReceiptError):
                    self.registry.verify_and_consume(
                        ProviderNetworkApprovalDecision(prompt.receipt, "approved"),
                        self.binding,
                    )

    def test_session_and_terminal_invalidation_reject_prior_receipts(self) -> None:
        cross_session = self.registry.issue(self.binding)
        with self.assertRaises(ProviderNetworkApprovalReceiptError):
            self.registry.verify_and_consume(
                ProviderNetworkApprovalDecision(cross_session.receipt, "approved"),
                replace(self.binding, session_id="provider_session_2"),
            )

        terminal = self.registry.issue(self.binding)
        self.registry.invalidate_workspace(self.binding.workspace_id)
        with self.assertRaises(ProviderNetworkApprovalReceiptError):
            self.registry.verify_and_consume(
                ProviderNetworkApprovalDecision(terminal.receipt, "approved"),
                self.binding,
            )
