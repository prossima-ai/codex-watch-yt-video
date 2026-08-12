#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from typing import Any

sys.dont_write_bytecode = True

from watch_evidence import WatchEvidenceRuntime


def main() -> int:
    runtime = WatchEvidenceRuntime()
    try:
        request: Any = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeError):
        outcome = runtime.invalid_input(
            "invalid_json", "Standard input must contain one valid JSON object."
        )
    else:
        outcome = runtime.prepare(request)
    json.dump(outcome.to_dict(), sys.stdout, ensure_ascii=True, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
