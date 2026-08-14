#!/usr/bin/env python3
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from watch_evidence import WatchEvidenceRuntime
from watch_runtime_cli import outcome_from_json, session_main, write_outcome
from watch_transcription import release_transcription_providers


def main() -> int:
    session_mode = sys.argv[1:] == ["--session"]
    runtime = WatchEvidenceRuntime(
        visual_enabled=False,
        reuse_enabled=session_mode,
        transcription_providers=release_transcription_providers(),
    )
    try:
        if session_mode:
            return session_main(runtime)
        if len(sys.argv) != 1:
            sys.stderr.write("Usage: prepare_metadata.py [--session]\n")
            return 2
        write_outcome(outcome_from_json(runtime, sys.stdin.read()))
        return 0
    finally:
        runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
