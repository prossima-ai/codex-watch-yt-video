#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from typing import Any, Mapping

sys.dont_write_bytecode = True

from watch_evidence import EvidenceOutcome, WatchEvidenceRuntime


def _prepare_outcome(
    runtime: WatchEvidenceRuntime, request: object
) -> EvidenceOutcome:
    prior_evidence: object | None = None
    watch_request = request
    if isinstance(request, Mapping) and "prior_evidence" in request:
        prior_evidence = request["prior_evidence"]
        watch_request = {
            key: value for key, value in request.items() if key != "prior_evidence"
        }
    return runtime.prepare(watch_request, prior_evidence)


def _outcome_from_json(
    runtime: WatchEvidenceRuntime, raw_input: str
) -> EvidenceOutcome:
    try:
        request: Any = json.loads(raw_input)
    except (json.JSONDecodeError, UnicodeError):
        return runtime.invalid_input(
            "invalid_json", "Standard input must contain one valid JSON object."
        )
    return _prepare_outcome(runtime, request)


def _write_outcome(outcome: EvidenceOutcome) -> None:
    json.dump(outcome.to_dict(), sys.stdout, ensure_ascii=True, sort_keys=True)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _session_main(runtime: WatchEvidenceRuntime) -> int:
    for raw_input in sys.stdin:
        _write_outcome(_outcome_from_json(runtime, raw_input))
    return 0


def main() -> int:
    runtime = WatchEvidenceRuntime(visual_enabled=False)
    if sys.argv[1:] == ["--session"]:
        return _session_main(runtime)
    if len(sys.argv) != 1:
        sys.stderr.write("Usage: prepare_metadata.py [--session]\n")
        return 2
    _write_outcome(_outcome_from_json(runtime, sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
