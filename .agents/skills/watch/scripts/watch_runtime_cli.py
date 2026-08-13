from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from watch_evidence import CleanupOutcome, EvidenceOutcome, WatchEvidenceRuntime


RuntimeOutcome = EvidenceOutcome | CleanupOutcome


def prepare_outcome(
    runtime: WatchEvidenceRuntime, request: object
) -> RuntimeOutcome:
    if isinstance(request, Mapping) and "cleanup" in request:
        if set(request) != {"cleanup"}:
            return runtime.invalid_input(
                "invalid_request",
                "A cleanup request must contain only its explicit cleanup selector.",
            )
        return runtime.cleanup(request["cleanup"])
    prior_evidence: object | None = None
    watch_request = request
    if isinstance(request, Mapping) and "prior_evidence" in request:
        prior_evidence = request["prior_evidence"]
        watch_request = {
            key: value for key, value in request.items() if key != "prior_evidence"
        }
    return runtime.prepare(watch_request, prior_evidence)


def outcome_from_json(runtime: WatchEvidenceRuntime, raw_input: str) -> RuntimeOutcome:
    try:
        request: Any = json.loads(raw_input)
    except (json.JSONDecodeError, UnicodeError):
        return runtime.invalid_input(
            "invalid_json", "Standard input must contain one valid JSON object."
        )
    return prepare_outcome(runtime, request)


def write_outcome(outcome: RuntimeOutcome) -> None:
    json.dump(outcome.to_dict(), sys.stdout, ensure_ascii=True, sort_keys=True)
    sys.stdout.write("\n")
    sys.stdout.flush()


def session_main(runtime: WatchEvidenceRuntime) -> int:
    for raw_input in sys.stdin:
        write_outcome(outcome_from_json(runtime, raw_input))
    return 0
