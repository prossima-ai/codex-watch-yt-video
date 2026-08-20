from __future__ import annotations

from dataclasses import dataclass
import secrets
from typing import Callable, Literal


PROVIDER_APPROVAL_RECEIPT_LIFETIME_SECONDS = 5 * 60


class ProviderNetworkApprovalReceiptError(ValueError):
    def __init__(self, code: Literal["invalid_receipt", "expired_receipt"]) -> None:
        self.code = code
        super().__init__(
            "The provider-network approval receipt has expired."
            if code == "expired_receipt"
            else "The provider-network approval receipt is invalid or no longer usable."
        )


@dataclass(frozen=True)
class ProviderNetworkApprovalDecision:
    """One untrusted decision payload; the registry validates its value."""

    receipt: str
    decision: str


@dataclass(frozen=True)
class ProviderNetworkBinding:
    action: Literal["transcribe_selected_audio"]
    watch_request_id: str
    source_value: str
    session_id: str
    workspace_id: str
    provider: str
    model: str
    destination: str
    selected_audio_track_id: str
    request_limit_bytes: int
    retry_budget: int


@dataclass(frozen=True)
class ProviderNetworkApproval:
    receipt: str
    purpose: Literal["transcribe_selected_audio"]
    provider: str
    model: str
    destination: str
    selected_audio_track_id: str
    request_limit_bytes: int
    retry_budget: int


@dataclass
class _IssuedReceipt:
    binding: ProviderNetworkBinding
    issued_at: float
    consumed: bool = False


class ProviderNetworkApprovalRegistry:
    """Same-session, single-use approval receipts for one provider route only.

    This lifecycle deliberately remains route-specific rather than sharing a
    generic receipt primitive with native captions: each security boundary
    validates and exposes only its own complete binding vocabulary.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float],
        receipt_factory: Callable[[], str] = lambda: "provider_receipt_"
        + secrets.token_urlsafe(24),
    ) -> None:
        self._clock = clock
        self._receipt_factory = receipt_factory
        self._receipts: dict[str, _IssuedReceipt] = {}

    def issue(self, binding: ProviderNetworkBinding) -> ProviderNetworkApproval:
        if not self._valid_binding(binding):
            raise ValueError("Invalid internal provider-network receipt binding.")
        receipt = self._new_receipt()
        self._receipts[receipt] = _IssuedReceipt(binding, self._clock())
        return ProviderNetworkApproval(
            receipt=receipt,
            purpose=binding.action,
            provider=binding.provider,
            model=binding.model,
            destination=binding.destination,
            selected_audio_track_id=binding.selected_audio_track_id,
            request_limit_bytes=binding.request_limit_bytes,
            retry_budget=binding.retry_budget,
        )

    def verify_and_consume(
        self, decision: object, expected_binding: ProviderNetworkBinding
    ) -> ProviderNetworkApprovalDecision:
        if (
            not isinstance(decision, ProviderNetworkApprovalDecision)
            or not isinstance(decision.receipt, str)
            or not decision.receipt
        ):
            raise ProviderNetworkApprovalReceiptError("invalid_receipt")
        issued = self._receipts.get(decision.receipt)
        if issued is None or issued.consumed:
            raise ProviderNetworkApprovalReceiptError("invalid_receipt")
        if decision.decision not in {"approved", "declined", "canceled"}:
            issued.consumed = True
            raise ProviderNetworkApprovalReceiptError("invalid_receipt")
        if self._clock() >= issued.issued_at + PROVIDER_APPROVAL_RECEIPT_LIFETIME_SECONDS:
            issued.consumed = True
            raise ProviderNetworkApprovalReceiptError("expired_receipt")
        if issued.binding != expected_binding:
            issued.consumed = True
            raise ProviderNetworkApprovalReceiptError("invalid_receipt")
        issued.consumed = True
        return decision

    def invalidate_all(self) -> None:
        for issued in self._receipts.values():
            issued.consumed = True

    def invalidate_receipt(self, receipt: object) -> None:
        if isinstance(receipt, str):
            issued = self._receipts.get(receipt)
            if issued is not None:
                issued.consumed = True

    def invalidate_workspace(self, workspace_id: str) -> None:
        for issued in self._receipts.values():
            if issued.binding.workspace_id == workspace_id:
                issued.consumed = True

    @staticmethod
    def _valid_binding(binding: ProviderNetworkBinding) -> bool:
        return (
            binding.action == "transcribe_selected_audio"
            and all(
                isinstance(value, str) and value
                for value in (
                    binding.watch_request_id,
                    binding.source_value,
                    binding.session_id,
                    binding.workspace_id,
                    binding.provider,
                    binding.model,
                    binding.destination,
                    binding.selected_audio_track_id,
                )
            )
            and not isinstance(binding.request_limit_bytes, bool)
            and binding.request_limit_bytes > 0
            and not isinstance(binding.retry_budget, bool)
            and binding.retry_budget > 0
        )

    def _new_receipt(self) -> str:
        candidate = self._receipt_factory()
        if not isinstance(candidate, str) or not candidate:
            raise ValueError("The provider receipt factory returned no opaque receipt.")
        receipt = candidate
        suffix = 1
        while receipt in self._receipts:
            receipt = f"{candidate}_{suffix}"
            suffix += 1
        return receipt
