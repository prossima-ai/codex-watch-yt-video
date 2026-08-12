from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import sys
from typing import Any


REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY / ".agents" / "skills" / "watch" / "scripts"
SIMULATED_MISSING_TOOL_HEADER = "X-TestSprite-Simulate-Missing-Tool"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS))

from watch_evidence import WatchEvidenceRuntime  # noqa: E402


def runtime_for_request(headers: object) -> WatchEvidenceRuntime:
    simulated_missing_tool = getattr(headers, "get")(SIMULATED_MISSING_TOOL_HEADER)
    if simulated_missing_tool is None:
        return WatchEvidenceRuntime()
    if simulated_missing_tool != "ffprobe":
        raise ValueError(
            f"{SIMULATED_MISSING_TOOL_HEADER} supports only the test value 'ffprobe'."
        )

    def find_executable(name: str) -> str | None:
        return None if name == simulated_missing_tool else shutil.which(name)

    return WatchEvidenceRuntime(find_executable=find_executable)


class TestSpriteWatchHandler(BaseHTTPRequestHandler):
    server_version = "TestSpriteWatchAdapter/1"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(
                200,
                {
                    "status": "ready",
                    "adapter": "test-only",
                    "missing_tool_simulation": SIMULATED_MISSING_TOOL_HEADER,
                },
            )
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/prepare-metadata":
            self._send_json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            request: Any = json.loads(raw_body)
            runtime = runtime_for_request(self.headers)
        except (ValueError, UnicodeError, json.JSONDecodeError) as error:
            outcome = WatchEvidenceRuntime().invalid_input("invalid_json", str(error))
        else:
            outcome = runtime.prepare(request)
        self._send_json(200, outcome.to_dict())

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(f"testsprite-adapter: {format % args}\n")

    def _send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 5173), TestSpriteWatchHandler).serve_forever()
