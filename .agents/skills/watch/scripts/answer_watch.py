#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

sys.dont_write_bytecode = True

from watch_answer import invalid_watch_answer, compose_watch_answer


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, UnicodeError):
        answer = invalid_watch_answer(
            "invalid_json", "Standard input must contain one valid JSON object."
        )
    else:
        answer = compose_watch_answer(request)
    json.dump(answer.to_dict(), sys.stdout, ensure_ascii=True, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
