from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PREPARE_METADATA = (
    REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "scripts" / "prepare_metadata.py"
)
PREPARE_VISUAL = (
    REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "scripts" / "prepare_visual.py"
)
SCRIPTS_DIRECTORY = PREPARE_METADATA.parent
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from watch_evidence import WatchEvidenceRuntime  # noqa: E402
from watch_transcription import (  # noqa: E402
    TRANSCRIPTION_RELEASE_BLOCKER,
    TRANSCRIPTION_RELEASE_ENABLED,
    release_transcription_providers,
)


class PrepareMetadataTests(unittest.TestCase):
    def make_fake_tool(self, directory: Path, name: str, body: str) -> Path:
        tool = directory / name
        tool.write_text(body, encoding="utf-8")
        tool.chmod(0o755)
        return tool

    def configure_fake_ytdlp(
        self,
        root: Path,
        metadata_payload: dict[str, object],
    ) -> tuple[dict[str, str], Path]:
        binary_directory = root / "bin"
        binary_directory.mkdir()
        command_log = root / "commands.jsonl"
        payload_literal = repr(metadata_payload)
        self.make_fake_tool(
            binary_directory,
            "yt-dlp",
            f"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

with Path(os.environ["WATCH_COMMAND_LOG"]).open("a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
if "--version" in sys.argv:
    print("2026.08.12")
elif "--verbose" in sys.argv:
    print("[debug] JS runtimes: node-24.10.0", file=sys.stderr)
    raise SystemExit(1)
else:
    print(json.dumps({payload_literal}))
""",
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{binary_directory}:{environment['PATH']}"
        environment["WATCH_COMMAND_LOG"] = str(command_log)
        return environment, command_log

    def read_invocations(self, command_log: Path) -> list[list[str]]:
        return [
            json.loads(line) for line in command_log.read_text(encoding="utf-8").splitlines()
        ]

    def run_request(
        self,
        request: dict[str, object],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, "-B", str(PREPARE_METADATA)],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=False,
            cwd=cwd,
            env=env,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def start_session(
        self,
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.Popen[str]:
        return subprocess.Popen(
            [sys.executable, "-B", str(PREPARE_METADATA), "--session"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
        )

    def run_session_request(
        self, session: subprocess.Popen[str], request: dict[str, object]
    ) -> dict[str, object]:
        self.assertIsNotNone(session.stdin)
        self.assertIsNotNone(session.stdout)
        assert session.stdin is not None
        assert session.stdout is not None
        session.stdin.write(json.dumps(request) + "\n")
        session.stdin.flush()
        response = session.stdout.readline()
        if not response:
            self.fail(session.stderr.read() if session.stderr is not None else "")
        return json.loads(response)

    def stop_session(self, session: subprocess.Popen[str]) -> None:
        self.assertIsNotNone(session.stdin)
        assert session.stdin is not None
        session.stdin.close()
        returncode = session.wait(timeout=5)
        stderr = session.stderr.read() if session.stderr is not None else ""
        if session.stdout is not None:
            session.stdout.close()
        if session.stderr is not None:
            session.stderr.close()
        self.assertEqual(returncode, 0, stderr)

    def run_raw_input(self, raw_input: str) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, "-B", str(PREPARE_METADATA)],
            input=raw_input,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_zero_sources_stops_before_preflight(self) -> None:
        outcome = self.run_request({"sources": []})

        self.assertEqual(outcome["state"], "stopped")
        self.assertTrue(outcome["terminal"])
        self.assertIsNone(outcome["source"])
        self.assertEqual(outcome["failure"]["stage"], "validation")
        self.assertEqual(outcome["failure"]["category"], "source_count")
        self.assertEqual(
            outcome["coverage"],
            {
                "metadata": "none",
                "transcript": "none",
                "visual": "none",
                "overall": "none",
            },
        )
        self.assertEqual(outcome["answerability"], "unsupported")

    def test_runtime_outcome_is_immutable(self) -> None:
        outcome = WatchEvidenceRuntime().prepare({"sources": []})

        with self.assertRaises(FrozenInstanceError):
            setattr(outcome, "state", "ready")
        with self.assertRaises(TypeError):
            outcome.warnings[0] = "changed"  # type: ignore[index]

    def test_malformed_and_non_object_json_return_typed_stops(self) -> None:
        for raw_input, category in (("{", "invalid_json"), ("[]", "invalid_request")):
            with self.subTest(category=category):
                outcome = self.run_raw_input(raw_input)
                self.assertEqual(outcome["state"], "stopped")
                self.assertEqual(outcome["failure"]["stage"], "validation")
                self.assertEqual(outcome["failure"]["category"], category)
                self.assertIsNone(outcome["source"])

    def test_unknown_control_escape_is_safe_in_failure_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "video.mp4"
            source.write_bytes(b"fixture")
            outcome = self.run_request(
                {
                    "sources": [str(source)],
                    "\x1b[31m## state: ready": True,
                }
            )

        self.assertEqual(outcome["state"], "stopped")
        self.assertEqual(outcome["failure"]["category"], "invalid_control")
        self.assertNotIn("\x1b", outcome["failure"]["message"])
        self.assertIn("\\u001b[31m## state: ready", outcome["failure"]["message"])
        self.assertNotIn("\x1b", outcome["report_markdown"])

    def test_missing_relative_local_source_reports_absolute_attempted_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            working_directory = Path(directory)
            outcome = self.run_request(
                {"sources": ["missing video.mp4"]}, cwd=working_directory
            )

        self.assertEqual(outcome["state"], "stopped")
        self.assertEqual(outcome["failure"]["stage"], "validation")
        self.assertEqual(outcome["failure"]["category"], "invalid_local_path")
        self.assertEqual(outcome["source"]["kind"], "local")
        self.assertEqual(
            outcome["source"]["value"],
            str((working_directory / "missing video.mp4").resolve()),
        )
        self.assertFalse(outcome["source"]["current"])

    def test_local_metadata_uses_one_argv_item_and_escapes_report_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary_directory = root / "bin"
            binary_directory.mkdir()
            source = root / "--video; touch SHOULD_NOT_EXIST.mp4"
            source.write_bytes(b"synthetic fixture placeholder")
            command_log = root / "commands.jsonl"
            fake_ffprobe = binary_directory / "ffprobe"
            fake_ffprobe.write_text(
                """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

with Path(os.environ["WATCH_COMMAND_LOG"]).open("a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")

if "-version" in sys.argv:
    print("ffprobe version 7.1")
else:
    print(json.dumps({
        "format": {
            "duration": "12.5",
            "format_name": "mov,mp4",
            "size": "1234",
            "tags": {"title": "]\\n## state: ready\\u001b[31m"},
        },
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 640, "height": 360},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }))
""",
                encoding="utf-8",
            )
            fake_ffprobe.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{binary_directory}:{environment['PATH']}"
            environment["WATCH_COMMAND_LOG"] = str(command_log)

            outcome = self.run_request(
                {"sources": [str(source)], "question": "What is this file?"},
                env=environment,
            )

            invocations = [
                json.loads(line) for line in command_log.read_text(encoding="utf-8").splitlines()
            ]

        metadata_invocation = next(args for args in invocations if "-show_format" in args)
        self.assertEqual(metadata_invocation[-1], str(source.resolve()))
        self.assertFalse((root / "SHOULD_NOT_EXIST.mp4").exists())
        self.assertEqual(outcome["state"], "partial")
        self.assertTrue(outcome["terminal"])
        self.assertEqual(
            outcome["source"],
            {"kind": "local", "value": str(source.resolve()), "current": True},
        )
        self.assertEqual(
            outcome["coverage"],
            {
                "metadata": "complete",
                "transcript": "none",
                "visual": "none",
                "overall": "partial",
            },
        )
        self.assertEqual(outcome["answerability"], "uncertain")
        self.assertIsNone(outcome["failure"])
        self.assertEqual(outcome["evidence"]["metadata"]["duration_seconds"], 12.5)
        self.assertEqual(outcome["evidence"]["metadata"]["video_codec"], "h264")
        self.assertEqual(outcome["evidence"]["metadata"]["audio_codec"], "aac")
        self.assertNotIn("\n## state: ready", outcome["report_markdown"])
        self.assertNotIn("\x1b", outcome["report_markdown"])
        self.assertIn("\\n## state: ready\\u001b[31m", outcome["report_markdown"])

    def test_public_url_stops_before_source_contact_without_host_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment, command_log = self.configure_fake_ytdlp(root, {})

            outcome = self.run_request(
                {"sources": ["https://video.example/watch?v=one"]}, env=environment
            )
            invocations = self.read_invocations(command_log)

        self.assertIn("--version", invocations[0])
        self.assertIn("--ignore-config", invocations[0])
        self.assertIn("--no-plugin-dirs", invocations[0])
        self.assertIn("--verbose", invocations[1])
        self.assertIn("watch-preflight:", invocations[1])
        self.assertNotIn("https://video.example/watch?v=one", invocations[1])
        self.assertEqual(len(invocations), 2)
        self.assertEqual(outcome["state"], "stopped")
        self.assertEqual(outcome["failure"]["stage"], "metadata")
        self.assertEqual(outcome["failure"]["category"], "network_approval_required")
        self.assertEqual(
            outcome["source"],
            {
                "kind": "url",
                "value": "https://video.example/watch?v=one",
                "current": True,
            },
        )

    def test_public_url_metadata_is_bounded_and_preserves_query_as_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "SHOULD_NOT_EXIST"
            source = (
                "https://video.example/watch?v=one&next=$(touch%20"
                f"{marker})"
            )
            environment, command_log = self.configure_fake_ytdlp(
                root,
                {
                    "_type": "video",
                    "id": "one",
                    "title": "Safe title",
                    "uploader": "Example uploader",
                    "duration": 61.25,
                    "ext": "webm",
                    "vcodec": "vp9",
                    "acodec": "opus",
                    "width": 1920,
                    "height": 1080,
                    "is_live": False,
                },
            )

            outcome = self.run_request(
                {"sources": [source], "source_network_approved": True},
                env=environment,
            )
            invocations = self.read_invocations(command_log)

        metadata_invocation = next(args for args in invocations if "--dump-single-json" in args)
        self.assertEqual(metadata_invocation[-2:], ["--", source])
        self.assertIn("--ignore-config", metadata_invocation)
        self.assertIn("--no-plugin-dirs", metadata_invocation)
        self.assertIn("--no-playlist", metadata_invocation)
        self.assertIn("--skip-download", metadata_invocation)
        self.assertIn("--socket-timeout", metadata_invocation)
        self.assertIn("--no-cache-dir", metadata_invocation)
        self.assertIn("--no-update", metadata_invocation)
        self.assertIn("--no-remote-components", metadata_invocation)
        self.assertNotIn("--cookies", metadata_invocation)
        self.assertNotIn("--cookies-from-browser", metadata_invocation)
        self.assertFalse(marker.exists())
        self.assertEqual(outcome["state"], "partial")
        self.assertEqual(outcome["source"]["value"], source)
        self.assertEqual(outcome["evidence"]["metadata"]["duration_seconds"], 61.25)
        self.assertEqual(outcome["evidence"]["metadata"]["uploader"], "Example uploader")
        self.assertEqual(
            outcome["javascript_support"],
            {"status": "available", "runtime": "node-24.10.0"},
        )
        self.assertIn("JavaScript support: `available`", outcome["report_markdown"])
        self.assertTrue(outcome["workspace_id"].startswith("workspace_"))
        self.assertIsNone(outcome["evidence_handle"])
        self.assertEqual(outcome["disposal_state"], "retained")
        self.assertEqual(outcome["reuse_state"], "none")
        self.assertIn(
            "Workspace reuse: `unavailable after this one-shot runtime exits`",
            outcome["report_markdown"],
        )

    def test_cli_caption_choices_are_opaque_and_fresh_process_selections_do_not_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment, command_log = self.configure_fake_ytdlp(
                root,
                {
                    "_type": "video",
                    "id": "one",
                    "duration": 2.0,
                    "ext": "webm",
                    "vcodec": "vp9",
                    "acodec": "opus",
                    "is_live": False,
                    "subtitles": {
                        "en": [{"ext": "vtt", "url": "https://cdn.example/en.vtt"}]
                    },
                    "automatic_captions": {
                        "fr": [{"ext": "vtt", "url": "https://cdn.example/fr.vtt"}]
                    },
                },
            )
            initial = self.run_request(
                {
                    "sources": ["https://video.example/watch?v=one"],
                    "detail": "transcript",
                    "source_network_approved": True,
                },
                env=environment,
            )
            initial_invocations = self.read_invocations(command_log)
            rejected = self.run_request(
                {
                    "sources": ["https://video.example/watch?v=one"],
                    "detail": "transcript",
                    "source_network_approved": True,
                    "caption_track": initial["choices"][0]["id"],
                    "prior_evidence": initial,
                },
                env=environment,
            )
            invocations_after_rejection = self.read_invocations(command_log)

        self.assertEqual(initial["state"], "decision_required")
        self.assertFalse(initial["terminal"])
        self.assertTrue(initial["decision_handle"].startswith("decision_"))
        self.assertIsNone(initial["evidence_handle"])
        self.assertEqual(initial["reuse_state"], "none")
        self.assertEqual(len(initial["choices"]), 2)
        self.assertNotIn("cdn.example", json.dumps(initial, sort_keys=True))
        self.assertEqual(
            len([args for args in initial_invocations if "--dump-single-json" in args]),
            1,
        )
        self.assertFalse(
            any(
                "--write-subs" in args or "--write-auto-subs" in args
                for args in initial_invocations
            )
        )
        self.assertEqual(rejected["state"], "stopped")
        self.assertEqual(rejected["failure"]["category"], "invalid_selection")
        self.assertEqual(invocations_after_rejection, initial_invocations)

    def test_session_reuses_an_opaque_handle_then_allows_explicit_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment, command_log = self.configure_fake_ytdlp(
                root,
                {
                    "_type": "video",
                    "id": "one",
                    "duration": 2.0,
                    "ext": "webm",
                    "vcodec": "vp9",
                    "acodec": "opus",
                    "is_live": False,
                },
            )
            session = self.start_session(env=environment)
            try:
                initial = self.run_session_request(
                    session,
                    {
                        "sources": ["https://video.example/watch?v=one"],
                        "detail": "transcript",
                        "source_network_approved": True,
                    },
                )
                invocations_before_reuse = self.read_invocations(command_log)
                reused = self.run_session_request(
                    session,
                    {
                        "sources": ["https://video.example/watch?v=one"],
                        "question": "What remains available?",
                        "source_network_approved": True,
                        "prior_evidence": {
                            "evidence_handle": initial["evidence_handle"]
                        },
                    },
                )
                cleaned = self.run_session_request(session, {"cleanup": "current"})
            finally:
                self.stop_session(session)
            invocations_after_cleanup = self.read_invocations(command_log)

        self.assertTrue(initial["evidence_handle"].startswith("evidence_"))
        self.assertTrue(initial["workspace_id"].startswith("workspace_"))
        self.assertNotIn("/", initial["evidence_handle"])
        self.assertEqual(reused["evidence_handle"], initial["evidence_handle"])
        self.assertEqual(invocations_before_reuse, invocations_after_cleanup)
        self.assertEqual(cleaned["state"], "cleanup_incomplete")
        self.assertEqual(cleaned["workspace_id"], initial["workspace_id"])

    def test_release_facing_sessions_keep_transcription_disabled_without_reading_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment, command_log = self.configure_fake_ytdlp(
                root,
                {
                    "_type": "video",
                    "id": "one",
                    "duration": 2.0,
                    "ext": "webm",
                    "vcodec": "vp9",
                    "acodec": "opus",
                    "is_live": False,
                    "subtitles": {},
                    "automatic_captions": {},
                },
            )
            environment.pop("OPENAI_API_KEY", None)
            environment.pop("GROQ_API_KEY", None)
            session = self.start_session(env=environment)
            try:
                outcome = self.run_session_request(
                    session,
                    {
                        "sources": ["https://video.example/watch?v=one"],
                        "detail": "transcript",
                        "source_network_approved": True,
                    },
                )
            finally:
                self.stop_session(session)
            invocations = self.read_invocations(command_log)

        self.assertEqual(outcome["state"], "partial")
        self.assertIsNone(outcome["choice_kind"])
        self.assertEqual(outcome["choices"], [])
        self.assertFalse(any("--format" in arguments for arguments in invocations))
        self.assertNotIn(
            "default_transcription_providers", PREPARE_METADATA.read_text(encoding="utf-8")
        )
        self.assertNotIn(
            "default_transcription_providers", PREPARE_VISUAL.read_text(encoding="utf-8")
        )
        self.assertFalse(TRANSCRIPTION_RELEASE_ENABLED)
        self.assertIn("multipart/form-data", TRANSCRIPTION_RELEASE_BLOCKER)
        self.assertIn("not merely nominal media-file size", TRANSCRIPTION_RELEASE_BLOCKER)
        self.assertEqual(release_transcription_providers(), {})

    def test_private_network_url_aliases_stop_during_validation(self) -> None:
        for host in ("127.0.0.1", "127.1", "2130706433", "0x7f000001"):
            with self.subTest(host=host):
                outcome = self.run_request(
                    {
                        "sources": [f"http://{host}/private-video"],
                        "source_network_approved": True,
                    }
                )

                self.assertEqual(outcome["state"], "stopped")
                self.assertEqual(outcome["failure"]["stage"], "validation")
                self.assertEqual(outcome["failure"]["category"], "non_public_url")
                self.assertFalse(outcome["source"]["current"])

    def test_invalid_controls_stop_before_preflight(self) -> None:
        cases = (
            ({"detail": "maximum"}, "invalid_detail"),
            ({"detail": []}, "invalid_detail"),
            ({"max_frames": 0}, "invalid_max_frames"),
            ({"keep_duplicates": "yes"}, "invalid_keep_duplicates"),
            ({"focus": ["00:10", "00:05"]}, "invalid_focus"),
            ({"cues": "00:03,bad"}, "invalid_cues"),
        )
        for controls, category in cases:
            with self.subTest(category=category):
                outcome = self.run_request(
                    {"sources": ["https://video.example/watch?v=one"], **controls}
                )
                self.assertEqual(outcome["state"], "stopped")
                self.assertEqual(outcome["failure"]["stage"], "validation")
                self.assertEqual(outcome["failure"]["category"], category)
                self.assertFalse(outcome["source"]["current"])

    def test_focus_start_at_known_duration_stops_after_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment, _ = self.configure_fake_ytdlp(
                root,
                {
                    "_type": "video",
                    "duration": 1.0,
                    "is_live": False,
                },
            )
            outcome = self.run_request(
                {
                    "sources": ["https://video.example/watch?v=one"],
                    "source_network_approved": True,
                    "focus": ["00:00:01", None],
                },
                env=environment,
            )

        self.assertEqual(outcome["state"], "stopped")
        self.assertTrue(outcome["source"]["current"])
        self.assertEqual(outcome["failure"]["stage"], "metadata")
        self.assertEqual(outcome["failure"]["category"], "invalid_focus")
        self.assertEqual(outcome["failure"]["attempts"], 1)
        self.assertIsNone(outcome["evidence"])

    def test_cue_beyond_known_duration_stops_after_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment, _ = self.configure_fake_ytdlp(
                root,
                {
                    "_type": "video",
                    "duration": 1.0,
                    "is_live": False,
                },
            )
            outcome = self.run_request(
                {
                    "sources": ["https://video.example/watch?v=one"],
                    "source_network_approved": True,
                    "cues": ["00:00:01.001"],
                },
                env=environment,
            )

        self.assertEqual(outcome["state"], "stopped")
        self.assertTrue(outcome["source"]["current"])
        self.assertEqual(outcome["failure"]["stage"], "metadata")
        self.assertEqual(outcome["failure"]["category"], "invalid_cues")
        self.assertEqual(outcome["failure"]["attempts"], 1)
        self.assertIsNone(outcome["evidence"])

    def test_cues_outside_focus_are_dropped_and_counted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment, _ = self.configure_fake_ytdlp(
                root,
                {
                    "_type": "video",
                    "duration": 10.0,
                    "is_live": False,
                },
            )
            outcome = self.run_request(
                {
                    "sources": ["https://video.example/watch?v=one"],
                    "source_network_approved": True,
                    "focus": ["00:00:02", "00:00:04"],
                    "cues": ["00:00:01", "00:00:03", "00:00:05"],
                },
                env=environment,
            )

        self.assertEqual(outcome["state"], "partial")
        self.assertEqual(outcome["controls"]["cues_seconds"], [3.0])
        self.assertEqual(outcome["controls"]["dropped_cues_count"], 2)
        self.assertIn("Cues dropped outside focus: `2`", outcome["report_markdown"])

    def test_missing_required_tool_fails_with_guidance_and_no_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            empty_binary_directory = root / "bin"
            empty_binary_directory.mkdir()
            source = root / "video.mp4"
            source.write_bytes(b"fixture")
            environment = os.environ.copy()
            environment["PATH"] = str(empty_binary_directory)

            outcome = self.run_request({"sources": [str(source)]}, env=environment)
            paths_after_run = sorted(path.name for path in root.iterdir())

        self.assertEqual(paths_after_run, ["bin", "video.mp4"])
        self.assertEqual(outcome["state"], "failed")
        self.assertEqual(outcome["failure"]["stage"], "preflight")
        self.assertEqual(outcome["failure"]["category"], "missing_dependency")
        self.assertEqual(outcome["failure"]["attempts"], 0)
        self.assertEqual(outcome["failure"]["disposal_state"], "not_created")
        self.assertEqual(outcome["failure"]["reuse_state"], "current_source_only")
        statuses = {tool["name"]: tool for tool in outcome["tools"]}
        self.assertFalse(statuses["ffprobe"]["available"])
        self.assertTrue(statuses["ffprobe"]["required_for_metadata"])

    def test_multiple_ambiguous_and_credentialed_sources_stop_in_validation(self) -> None:
        cases = (
            (
                {"sources": ["one.mp4", "two.mp4"]},
                "source_count",
            ),
            ({"sources": ["   "]}, "ambiguous_source"),
            (
                {"sources": ["https://user:secret@video.example/watch?v=one"]},
                "unsupported_access",
            ),
        )

        for request, category in cases:
            with self.subTest(category=category):
                outcome = self.run_request(request)
                self.assertEqual(outcome["state"], "stopped")
                self.assertEqual(outcome["failure"]["stage"], "validation")
                self.assertEqual(outcome["failure"]["category"], category)
                self.assertEqual(outcome["failure"]["attempts"], 0)
                if category == "unsupported_access":
                    self.assertIsNone(outcome["source"])
                    self.assertNotIn("secret", json.dumps(outcome))

    def test_playlist_metadata_stops_without_media_acquisition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment, command_log = self.configure_fake_ytdlp(
                root, {"_type": "playlist", "entries": [{"id": "one"}]}
            )

            outcome = self.run_request(
                {
                    "sources": ["https://video.example/playlist?list=many"],
                    "source_network_approved": True,
                },
                env=environment,
            )
            invocations = self.read_invocations(command_log)

        metadata_invocations = [args for args in invocations if "--dump-single-json" in args]
        self.assertEqual(len(metadata_invocations), 1)
        self.assertIn("--skip-download", metadata_invocations[0])
        self.assertEqual(outcome["state"], "stopped")
        self.assertEqual(outcome["failure"]["category"], "unsupported_playlist")
        self.assertEqual(outcome["failure"]["attempts"], 1)
        self.assertFalse(outcome["source"]["current"])


if __name__ == "__main__":
    unittest.main()
