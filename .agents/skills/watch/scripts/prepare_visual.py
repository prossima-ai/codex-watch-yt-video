#!/usr/bin/env python3
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from watch_evidence import WatchEvidenceRuntime
from watch_runtime_cli import outcome_from_json, session_main, write_outcome
from watch_transcription import default_transcription_providers


def main() -> int:
    session_mode = sys.argv[1:] == ["--session"]
    runtime = WatchEvidenceRuntime(
        reuse_enabled=session_mode,
        transcription_providers=(
            default_transcription_providers() if session_mode else None
        ),
    )
    try:
        if session_mode:
            return session_main(runtime)
        if len(sys.argv) != 1:
            sys.stderr.write("Usage: prepare_visual.py [--session]\n")
            return 2
        write_outcome(outcome_from_json(runtime, sys.stdin.read()))
        return 0
    finally:
        runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
