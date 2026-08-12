from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PREPARE_VISUAL = (
    REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "scripts" / "prepare_visual.py"
)
SCRIPTS_DIRECTORY = PREPARE_VISUAL.parent
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from watch_evidence import (  # noqa: E402
    CommandResult,
    FrameEscalation,
    FrameInspection,
    WatchEvidenceRuntime,
)


class RecordingMediaRunner:
    def __init__(
        self,
        *,
        duration_seconds: float,
        scene_times: tuple[float, ...],
        same_fingerprint: bool = False,
        source_width: int | None = 1920,
        source_height: int | None = 1080,
    ) -> None:
        self.duration_seconds = duration_seconds
        self.scene_times = scene_times
        self.same_fingerprint = same_fingerprint
        self.source_width = source_width
        self.source_height = source_height
        self.invocations: list[tuple[str, list[str]]] = []

    def run(self, executable: str, arguments: object) -> CommandResult:
        args = list(arguments)
        self.invocations.append((executable, args))
        if "-version" in args or "--version" in args:
            return CommandResult(0, f"{Path(executable).name} version fixture\n", "")
        if "--verbose" in args:
            return CommandResult(1, "", "[debug] JS runtimes: none\n")
        if "--dump-single-json" in args:
            return CommandResult(
                0,
                json.dumps(
                    {
                        "_type": "video",
                        "duration": self.duration_seconds,
                        "title": "fixture",
                        "vcodec": "h264",
                        "width": 1920,
                        "height": 1080,
                        "is_live": False,
                    }
                ),
                "",
            )
        if "--print" in args:
            output_template = args[args.index("--output") + 1]
            output = Path(output_template.replace("%(ext)s", "mp4"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"synthetic-media")
            return CommandResult(0, f"{output}\n", "")
        if "-show_format" in args:
            return CommandResult(
                0,
                json.dumps(
                    {
                        "format": {
                            "duration": str(self.duration_seconds),
                            "format_name": "mov,mp4",
                        },
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": self.source_width,
                                "height": self.source_height,
                            }
                        ],
                    }
                ),
                "",
            )
        if "-show_entries" in args:
            width, height = (
                (1024, 576)
                if str(args[-1]).endswith("-detail.jpg")
                else (768, 432)
            )
            return CommandResult(
                0,
                json.dumps(
                    {
                        "streams": [
                            {"codec_name": "mjpeg", "width": width, "height": height}
                        ]
                    }
                ),
                "",
            )
        if "-skip_frame" in args:
            return CommandResult(0, json.dumps({"frames": []}), "")
        if "framemd5" in args:
            timestamp = args[args.index("-ss") + 1]
            fingerprint = (
                "0" * 32
                if self.same_fingerprint
                else hashlib.sha256(timestamp.encode()).hexdigest()[:32]
            )
            return CommandResult(
                0, f"0, 0, 0, 1, 576, {fingerprint}\n", ""
            )
        if "null" in args:
            return CommandResult(
                0,
                "",
                "".join(
                    f"[Parsed_showinfo_0] pts_time:{timestamp:.6f}\n"
                    for timestamp in self.scene_times
                ),
            )
        if "-frames:v" in args:
            output = Path(args[-1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"synthetic-jpeg")
            return CommandResult(0, "", "")
        return CommandResult(0, "", "")


class FailingSceneRunner(RecordingMediaRunner):
    def run(self, executable: str, arguments: object) -> CommandResult:
        args = list(arguments)
        if "null" in args:
            raise OSError("synthetic frame selector failure")
        return super().run(executable, args)


class InspectAllFrames:
    def inspect(self, batches: object) -> FrameInspection:
        return FrameInspection(
            "complete",
            tuple(frame.path for batch in batches for frame in batch),
        )


class EscalateFirstFrame:
    def __init__(self) -> None:
        self.call_count = 0

    def inspect(self, batches: object) -> FrameInspection:
        self.call_count += 1
        frames = tuple(frame for batch in batches for frame in batch)
        if self.call_count == 1:
            return FrameInspection(
                "complete",
                tuple(frame.path for frame in frames),
                escalations=(
                    FrameEscalation(
                        frame_path=frames[0].path,
                        reason="The visible small text is material to the question.",
                    ),
                ),
            )
        return FrameInspection("complete", tuple(frame.path for frame in frames))


class EscalateThenLoseDetailInspection:
    def __init__(self) -> None:
        self.call_count = 0

    def inspect(self, batches: object) -> FrameInspection:
        self.call_count += 1
        frames = tuple(frame for batch in batches for frame in batch)
        if self.call_count == 1:
            return FrameInspection(
                "complete",
                tuple(frame.path for frame in frames),
                escalations=(
                    FrameEscalation(
                        frame_path=frames[0].path,
                        reason="The visible fine detail is material to the question.",
                    ),
                ),
            )
        return FrameInspection(
            "unavailable",
            (),
            "The local image capability could not read the detail frame.",
        )


class UnavailableInspector:
    def inspect(self, batches: object) -> FrameInspection:
        del batches
        return FrameInspection(
            "unavailable",
            (),
            "The local image capability could not read these frames.",
        )


class VisualEvidenceTests(unittest.TestCase):
    def make_fake_tool(self, directory: Path, name: str, body: str) -> Path:
        tool = directory / name
        tool.write_text(body, encoding="utf-8")
        tool.chmod(0o755)
        return tool

    def configure_fake_media_tools(
        self,
        root: Path,
        *,
        keyframe_times: tuple[float, ...] = (2.0, 4.0, 6.0),
        scene_times: tuple[float, ...] = (2.0, 5.0, 8.0),
    ) -> tuple[dict[str, str], Path]:
        binary_directory = root / "bin"
        binary_directory.mkdir()
        command_log = root / "commands.jsonl"
        self.make_fake_tool(
            binary_directory,
            "ffprobe",
            """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

with Path(os.environ["WATCH_COMMAND_LOG"]).open("a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")

if "-version" in sys.argv:
    print("ffprobe version 7.1")
elif sys.argv[-1].endswith(".jpg"):
    print(json.dumps({"streams": [
        {"codec_name": "mjpeg", "width": 768, "height": 432},
    ]}))
elif "-skip_frame" in sys.argv:
    print(json.dumps({"frames": [
        {"best_effort_timestamp_time": str(timestamp)}
        for timestamp in json.loads(os.environ["WATCH_KEYFRAME_TIMES"])
    ]}))
else:
    print(json.dumps({
        "format": {"duration": "10", "format_name": "mov,mp4", "size": "1234"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
        ],
    }))
""",
        )
        self.make_fake_tool(
            binary_directory,
            "ffmpeg",
            """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

with Path(os.environ["WATCH_COMMAND_LOG"]).open("a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")

if "-version" in sys.argv:
    print("ffmpeg version 7.1")
elif "framemd5" in sys.argv:
    timestamp = sys.argv[sys.argv.index("-ss") + 1]
    print(f"0, 0, 0, 1, 576, {sum(timestamp.encode()):032x}")
elif "null" in sys.argv:
    for timestamp in json.loads(os.environ["WATCH_SCENE_TIMES"]):
        print(f"[Parsed_showinfo_0] pts_time:{timestamp:.6f}", file=sys.stderr)
elif sys.argv[-1].startswith("-"):
    # A capability probe has no output path and must not create an option-named file.
    pass
else:
    output = Path(sys.argv[-1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"synthetic-jpeg")
""",
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{binary_directory}:{environment['PATH']}"
        environment["WATCH_COMMAND_LOG"] = str(command_log)
        environment["WATCH_KEYFRAME_TIMES"] = json.dumps(keyframe_times)
        environment["WATCH_SCENE_TIMES"] = json.dumps(scene_times)
        return environment, command_log

    def run_request(
        self, request: dict[str, object], env: dict[str, str]
    ) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, "-B", str(PREPARE_VISUAL)],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_focused_visual_request_returns_timestamped_frames_for_host_inspection(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            environment, command_log = self.configure_fake_media_tools(root)

            outcome = self.run_request(
                {
                    "sources": [str(source)],
                    "detail": "balanced",
                    "focus": ["00:00:02", "00:00:08"],
                    "cues": ["00:00:03", "00:00:07"],
                    "max_frames": 5,
                },
                environment,
            )
            invocations = [
                json.loads(line)
                for line in command_log.read_text(encoding="utf-8").splitlines()
            ]

            visual = outcome["evidence"]["visual"]
            frames = visual["frames"]
            self.assertEqual(outcome["state"], "partial")
            self.assertEqual(outcome["coverage"]["visual"], "none")
            self.assertEqual(visual["inspection_state"], "host_inspection_required")
            self.assertLessEqual(len(frames), 5)
            self.assertEqual(
                [frame["chronological_position"] for frame in frames],
                list(range(1, len(frames) + 1)),
            )
            self.assertEqual(
                [frame["timestamp_seconds"] for frame in frames],
                sorted(frame["timestamp_seconds"] for frame in frames),
            )
            self.assertTrue(
                any(frame["selection_reason"] == "transcript-cue" for frame in frames)
            )
            self.assertTrue(all(frame["format"] == "jpeg" for frame in frames))
            self.assertTrue(all(frame["width"] <= 768 for frame in frames))
            self.assertTrue(all(Path(frame["path"]).is_file() for frame in frames))
            self.assertTrue(all(len(batch) <= 8 for batch in visual["inspection_batches"]))
            self.assertEqual(
                [frame["path"] for batch in visual["inspection_batches"] for frame in batch],
                [frame["path"] for frame in frames],
            )
            self.assertIn("Visual claims: `none until host inspection`", outcome["report_markdown"])

            extraction_calls = [
                args
                for args in invocations
                if args[-1].endswith(".jpg") and "-frames:v" in args
            ]
            self.assertEqual(len(extraction_calls), len(frames))
            self.assertTrue(
                all(
                    any("min(768,iw)" in argument for argument in args)
                    for args in extraction_calls
                )
            )

    def test_transcript_detail_without_cues_creates_no_visual_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            environment, command_log = self.configure_fake_media_tools(root)

            outcome = self.run_request(
                {"sources": [str(source)], "detail": "transcript"}, environment
            )
            invocations = [
                json.loads(line)
                for line in command_log.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(outcome["state"], "partial")
        self.assertEqual(outcome["coverage"]["visual"], "none")
        self.assertEqual(outcome["evidence"]["visual"]["frames"], [])
        self.assertEqual(
            outcome["evidence"]["visual"]["inspection_state"], "not_applicable"
        )
        self.assertIn("no visual fallback was prepared", outcome["report_markdown"])
        self.assertFalse(any("-frames:v" in args for args in invocations))
        self.assertFalse(any("framemd5" in args for args in invocations))

    def test_transcript_detail_allows_valid_cue_only_frames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            environment, _ = self.configure_fake_media_tools(root)

            outcome = self.run_request(
                {
                    "sources": [str(source)],
                    "detail": "transcript",
                    "cues": ["00:00:01", "00:00:03"],
                },
                environment,
            )

        visual = outcome["evidence"]["visual"]
        self.assertEqual(
            [frame["timestamp_seconds"] for frame in visual["frames"]], [1.0, 3.0]
        )
        self.assertEqual(
            {frame["selection_reason"] for frame in visual["frames"]},
            {"transcript-cue"},
        )
        self.assertEqual(visual["ordinary_candidate_count"], 0)
        self.assertEqual(visual["ordinary_frame_cap"], 0)
        self.assertIsNone(visual["cap"])

    def test_cues_reserve_a_finite_cap_and_keep_the_requested_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            environment, _ = self.configure_fake_media_tools(root)

            outcome = self.run_request(
                {
                    "sources": [str(source)],
                    "detail": "balanced",
                    "max_frames": 3,
                    "cues": ["00:00:01", "00:00:02", "00:00:03", "00:00:04", "00:00:05"],
                },
                environment,
            )

        visual = outcome["evidence"]["visual"]
        self.assertEqual(outcome["state"], "partial")
        self.assertEqual(visual["cap"], 3)
        self.assertEqual(visual["cue_requested_count"], 5)
        self.assertEqual(visual["cue_selected_count"], 3)
        self.assertEqual(visual["cue_dropped_by_cap_count"], 2)
        self.assertEqual(visual["ordinary_candidate_count"], 0)
        self.assertEqual(
            [frame["timestamp_seconds"] for frame in visual["frames"]], [1.0, 3.0, 5.0]
        )
        self.assertEqual(
            {frame["selection_reason"] for frame in visual["frames"]},
            {"transcript-cue"},
        )
        self.assertIn("Cue frames dropped by cap: `2`", outcome["report_markdown"])

    def test_efficient_mode_falls_back_to_bounded_uniform_frames_when_keyframes_are_sparse(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            environment, command_log = self.configure_fake_media_tools(root)

            outcome = self.run_request(
                {
                    "sources": [str(source)],
                    "detail": "efficient",
                    "max_frames": 4,
                },
                environment,
            )
            invocations = [
                json.loads(line)
                for line in command_log.read_text(encoding="utf-8").splitlines()
            ]

        visual = outcome["evidence"]["visual"]
        self.assertEqual(visual["fallback"], "uniform")
        self.assertEqual(visual["deduplication"], "applied")
        self.assertEqual(len(visual["frames"]), 4)
        self.assertEqual(visual["frames"][0]["selection_reason"], "first")
        self.assertTrue(
            all(
                frame["selection_reason"] in {"first", "uniform"}
                for frame in visual["frames"]
            )
        )
        self.assertTrue(any("-skip_frame" in args for args in invocations))
        self.assertEqual(sum("framemd5" in args for args in invocations), 4)

    def test_balanced_scene_candidates_are_rate_limited_then_thinned_across_the_scope(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            environment, command_log = self.configure_fake_media_tools(
                root, scene_times=(0.0, 0.1, 0.4, 0.6, 1.2, 9.8)
            )

            outcome = self.run_request(
                {
                    "sources": [str(source)],
                    "detail": "balanced",
                    "max_frames": 3,
                },
                environment,
            )
            invocations = [
                json.loads(line)
                for line in command_log.read_text(encoding="utf-8").splitlines()
            ]

        visual = outcome["evidence"]["visual"]
        timestamps = [frame["timestamp_seconds"] for frame in visual["frames"]]
        self.assertEqual(visual["fallback"], "scene")
        self.assertEqual(visual["deduplication"], "applied")
        self.assertEqual(timestamps[0], 0.0)
        self.assertEqual(timestamps[-1], 9.8)
        self.assertLessEqual(len(timestamps), 3)
        self.assertTrue(
            all(later - earlier >= 0.5 for earlier, later in zip(timestamps, timestamps[1:]))
        )
        self.assertEqual(sum("framemd5" in args for args in invocations), 2)

    def test_cue_priority_keeps_the_final_selection_at_or_below_two_frames_per_second(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            environment, _ = self.configure_fake_media_tools(
                root, scene_times=(0.0, 0.4, 0.8, 3.0)
            )

            outcome = self.run_request(
                {
                    "sources": [str(source)],
                    "detail": "balanced",
                    "cues": ["00:00:00.2"],
                    "max_frames": 5,
                },
                environment,
            )

        timestamps = [
            frame["timestamp_seconds"]
            for frame in outcome["evidence"]["visual"]["frames"]
        ]
        self.assertIn(0.2, timestamps)
        self.assertTrue(
            all(
                later - earlier >= 0.5
                for earlier, later in zip(timestamps, timestamps[1:])
            ),
            timestamps,
        )

    def test_scene_candidates_are_deduplicated_before_the_frame_cap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            runner = RecordingMediaRunner(
                duration_seconds=3.0,
                scene_times=(0.0, 1.0, 2.0),
                same_fingerprint=True,
            )
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=lambda name: name,
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare({"sources": [str(source)], "detail": "balanced"})

        visual = outcome.evidence.visual  # type: ignore[union-attr]
        self.assertEqual(visual.deduplication, "applied")
        self.assertEqual(len(visual.frames), 1)
        self.assertEqual(
            sum("framemd5" in args for _, args in runner.invocations), 3
        )

    def test_keep_duplicates_skips_scene_deduplication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            runner = RecordingMediaRunner(
                duration_seconds=3.0,
                scene_times=(0.0, 1.0, 2.0),
                same_fingerprint=True,
            )
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=lambda name: name,
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare(
                {
                    "sources": [str(source)],
                    "detail": "balanced",
                    "keep_duplicates": True,
                }
            )

        visual = outcome.evidence.visual  # type: ignore[union-attr]
        self.assertEqual(visual.deduplication, "disabled")
        self.assertEqual(len(visual.frames), 3)
        self.assertFalse(any("framemd5" in args for _, args in runner.invocations))

    def test_unfocused_sources_over_ten_minutes_warn_about_sparse_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            runtime = WatchEvidenceRuntime(
                command_runner=RecordingMediaRunner(
                    duration_seconds=601.0, scene_times=()
                ),
                find_executable=lambda name: name,
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare(
                {
                    "sources": [str(source)],
                    "detail": "efficient",
                    "max_frames": 1,
                }
            )

        self.assertTrue(
            any("coverage is sparse" in warning for warning in outcome.warnings),
            outcome.warnings,
        )

    def test_default_efficient_and_balanced_caps_bound_ordinary_frame_scale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            efficient = WatchEvidenceRuntime(
                command_runner=RecordingMediaRunner(
                    duration_seconds=300.0, scene_times=()
                ),
                find_executable=lambda name: name,
                artifact_root=root / "efficient-artifacts",
            ).prepare({"sources": [str(source)], "detail": "efficient"})
            balanced = WatchEvidenceRuntime(
                command_runner=RecordingMediaRunner(
                    duration_seconds=300.0,
                    scene_times=tuple(index * 3.0 for index in range(101)),
                ),
                find_executable=lambda name: name,
                artifact_root=root / "balanced-artifacts",
            ).prepare({"sources": [str(source)], "detail": "balanced"})

        efficient_visual = efficient.evidence.visual  # type: ignore[union-attr]
        balanced_visual = balanced.evidence.visual  # type: ignore[union-attr]
        self.assertEqual(efficient_visual.cap, 50)
        self.assertEqual(len(efficient_visual.frames), 50)
        self.assertEqual(balanced_visual.cap, 100)
        self.assertEqual(len(balanced_visual.frames), 80)
        self.assertLessEqual(len(balanced_visual.frames), balanced_visual.cap)

    def test_small_cap_bounds_fingerprint_work_before_deduplication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            runner = RecordingMediaRunner(
                duration_seconds=1_000.0,
                scene_times=tuple(float(index) for index in range(1_000)),
            )
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=lambda name: name,
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare(
                {
                    "sources": [str(source)],
                    "detail": "balanced",
                    "max_frames": 1,
                }
            )

        visual = outcome.evidence.visual  # type: ignore[union-attr]
        self.assertEqual(len(visual.frames), 1)
        self.assertEqual(
            sum("framemd5" in args for _, args in runner.invocations), 1
        )

    def test_focused_scene_and_keyframe_scans_use_the_effective_interval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            scene_runner = RecordingMediaRunner(
                duration_seconds=1_000.0, scene_times=(500.0, 501.0)
            )
            keyframe_runner = RecordingMediaRunner(
                duration_seconds=1_000.0, scene_times=()
            )
            WatchEvidenceRuntime(
                command_runner=scene_runner,
                find_executable=lambda name: name,
                artifact_root=root / "scene-artifacts",
            ).prepare(
                {
                    "sources": [str(source)],
                    "detail": "balanced",
                    "focus": [500, 502],
                }
            )
            WatchEvidenceRuntime(
                command_runner=keyframe_runner,
                find_executable=lambda name: name,
                artifact_root=root / "keyframe-artifacts",
            ).prepare(
                {
                    "sources": [str(source)],
                    "detail": "efficient",
                    "focus": [500, 502],
                }
            )

        scene_arguments = next(
            arguments
            for _, arguments in scene_runner.invocations
            if "null" in arguments
        )
        keyframe_arguments = next(
            arguments
            for _, arguments in keyframe_runner.invocations
            if "-skip_frame" in arguments
        )
        self.assertEqual(
            scene_arguments[
                scene_arguments.index("-ss") + 1 : scene_arguments.index("-ss") + 4
            ],
            ["500", "-t", "2"],
        )
        self.assertIn("-copyts", scene_arguments)
        self.assertEqual(
            keyframe_arguments[
                keyframe_arguments.index("-read_intervals") + 1
            ],
            "500%+2",
        )

    def test_focus_clamps_the_reported_endpoint_to_known_duration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            runtime = WatchEvidenceRuntime(
                command_runner=RecordingMediaRunner(
                    duration_seconds=10.0, scene_times=(5.0, 8.0, 10.0)
                ),
                find_executable=lambda name: name,
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare(
                {"sources": [str(source)], "focus": [5, 60]}
            )

        visual = outcome.evidence.visual  # type: ignore[union-attr]
        self.assertEqual(outcome.controls.focus_end_seconds, 10.0)
        self.assertIn("- Focus seconds: `5.0` to `10.0`", outcome.report_markdown)
        self.assertTrue(all(frame.timestamp_seconds <= 10.0 for frame in visual.frames))

    def test_token_burner_warns_only_after_more_than_250_selected_frames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            runner = RecordingMediaRunner(
                duration_seconds=125.0,
                scene_times=tuple(index * 0.5 for index in range(251)),
            )
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=lambda name: name,
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare(
                {"sources": [str(source)], "detail": "token-burner"}
            )

        self.assertEqual(outcome.state, "partial")
        self.assertEqual(outcome.evidence.visual.cap, None)  # type: ignore[union-attr]
        self.assertEqual(len(outcome.evidence.visual.frames), 251)  # type: ignore[union-attr]
        self.assertTrue(
            any("high visual-context cost" in warning for warning in outcome.warnings)
        )

    def test_frame_inspector_receives_all_chronological_eight_frame_batches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            runner = RecordingMediaRunner(
                duration_seconds=5.0,
                scene_times=tuple(index * 0.5 for index in range(9)),
            )
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=lambda name: name,
                frame_inspector=InspectAllFrames(),
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare(
                {"sources": [str(source)], "detail": "balanced"}
            )

        visual = outcome.evidence.visual  # type: ignore[union-attr]
        self.assertEqual(visual.inspection_state, "complete")
        self.assertEqual([len(batch) for batch in visual.inspection_batches], [8, 1])
        self.assertTrue(all(frame.inspected for frame in visual.frames))
        self.assertTrue(
            all(
                frame.inspected
                for batch in visual.inspection_batches
                for frame in batch
            )
        )

    def test_unavailable_image_inspection_allows_no_visual_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            runtime = WatchEvidenceRuntime(
                command_runner=RecordingMediaRunner(
                    duration_seconds=5.0, scene_times=(1.0, 4.0)
                ),
                find_executable=lambda name: name,
                frame_inspector=UnavailableInspector(),
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare({"sources": [str(source)]})

        visual = outcome.evidence.visual  # type: ignore[union-attr]
        self.assertEqual(visual.inspection_state, "unavailable")
        self.assertTrue(all(not frame.inspected for frame in visual.frames))
        self.assertEqual(outcome.coverage.visual, "none")
        self.assertIn("Visual claims: `none until host inspection`", outcome.report_markdown)

    def test_only_the_inspector_can_request_one_material_1024px_reextraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            runner = RecordingMediaRunner(duration_seconds=5.0, scene_times=(1.0, 4.0))
            inspector = EscalateFirstFrame()
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=lambda name: name,
                frame_inspector=inspector,
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare(
                {
                    "sources": [str(source)],
                    "detail": "balanced",
                    "question": "What does the small text say?",
                }
            )

        visual = outcome.evidence.visual  # type: ignore[union-attr]
        self.assertEqual(inspector.call_count, 2)
        self.assertEqual(visual.inspection_state, "complete")
        self.assertEqual(visual.frames[0].width, 1024)
        self.assertEqual(visual.frames[0].height, 576)
        self.assertEqual(
            visual.frames[0].resolution_reason,
            "The visible small text is material to the question.",
        )
        self.assertTrue(visual.frames[0].inspected)
        self.assertEqual(visual.frames[1].width, 768)
        self.assertIsNone(visual.frames[1].resolution_reason)
        self.assertTrue(all(frame.inspected for frame in visual.frames))

    def test_higher_resolution_request_without_a_question_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            runner = RecordingMediaRunner(duration_seconds=5.0, scene_times=(1.0, 4.0))
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=lambda name: name,
                frame_inspector=EscalateFirstFrame(),
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare(
                {"sources": [str(source)], "detail": "balanced"}
            )

        visual = outcome.evidence.visual  # type: ignore[union-attr]
        self.assertEqual(visual.frames[0].width, 768)
        self.assertIsNone(visual.frames[0].resolution_reason)
        self.assertTrue(
            any("has no question" in warning for warning in outcome.warnings),
            outcome.warnings,
        )

    def test_unavailable_detail_reinspection_removes_visual_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            inspector = EscalateThenLoseDetailInspection()
            runtime = WatchEvidenceRuntime(
                command_runner=RecordingMediaRunner(
                    duration_seconds=5.0, scene_times=(1.0, 4.0)
                ),
                find_executable=lambda name: name,
                frame_inspector=inspector,
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare(
                {
                    "sources": [str(source)],
                    "question": "What does the fine detail show?",
                }
            )

        visual = outcome.evidence.visual  # type: ignore[union-attr]
        self.assertEqual(inspector.call_count, 2)
        self.assertEqual(visual.inspection_state, "unavailable")
        self.assertTrue(any(frame.inspected for frame in visual.frames))
        self.assertEqual(outcome.coverage.visual, "none")
        self.assertIn("Visual claims: `none until host inspection`", outcome.report_markdown)

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "ffmpeg and ffprobe are required for this synthetic visual fixture",
    )
    def test_real_ffmpeg_extracts_aspect_correct_ordinary_jpegs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "landscape.mp4"
            generated = subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-y",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=320x180:rate=5:duration=2",
                    "-c:v",
                    "mpeg4",
                    str(source),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            runtime = WatchEvidenceRuntime(
                find_executable=lambda name: shutil.which(name)
                if name in {"ffmpeg", "ffprobe"}
                else None,
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare(
                {"sources": [str(source)], "detail": "balanced", "max_frames": 3}
            )

        visual = outcome.evidence.visual  # type: ignore[union-attr]
        self.assertTrue(visual.frames)
        self.assertTrue(all(frame.format == "jpeg" for frame in visual.frames))
        self.assertTrue(all(frame.width <= 320 for frame in visual.frames))
        self.assertTrue(
            all(
                abs((frame.width / frame.height) - (320 / 180)) < 0.02
                for frame in visual.frames
            )
        )

    def test_approved_public_source_downloads_to_a_controlled_path_without_cookie_flags(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = RecordingMediaRunner(duration_seconds=10.0, scene_times=(2.0, 8.0))
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=lambda name: name,
                artifact_root=root / "artifacts",
            )
            source = "https://video.example/watch?v=one&note=untrusted"

            outcome = runtime.prepare(
                {"sources": [source], "source_network_approved": True}
            )

        visual = outcome.evidence.visual  # type: ignore[union-attr]
        download = next(
            args for executable, args in runner.invocations if executable == "yt-dlp" and "--print" in args
        )
        self.assertTrue(visual.frames)
        self.assertEqual(download[-2:], ["--", source])
        self.assertIn("--ignore-config", download)
        self.assertIn("--no-plugin-dirs", download)
        self.assertIn("--no-playlist", download)
        self.assertIn("--no-cache-dir", download)
        self.assertIn("--no-update", download)
        self.assertIn("--no-remote-components", download)
        self.assertNotIn("--cookies", download)
        self.assertNotIn("--cookies-from-browser", download)
        output_template = Path(download[download.index("--output") + 1])
        self.assertTrue(
            str(output_template).startswith(str((root / "artifacts").resolve())),
            output_template,
        )

    def test_output_dir_does_not_grant_visual_artifact_write_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            supplied_output_dir = root / "user-retained-artifacts"
            runtime = WatchEvidenceRuntime(
                command_runner=RecordingMediaRunner(
                    duration_seconds=5.0, scene_times=(1.0, 4.0)
                ),
                find_executable=lambda name: name,
                artifact_root=root / "controlled-artifacts",
            )

            outcome = runtime.prepare(
                {
                    "sources": [str(source)],
                    "output_dir": str(supplied_output_dir),
                }
            )

        visual = outcome.evidence.visual  # type: ignore[union-attr]
        self.assertFalse(supplied_output_dir.exists())
        self.assertTrue(
            all(
                not Path(frame.path).is_relative_to(supplied_output_dir)
                for frame in visual.frames
            )
        )
        self.assertTrue(
            any("was not used" in warning for warning in outcome.warnings),
            outcome.warnings,
        )

    def test_visual_tool_failure_returns_metadata_partial_without_a_fake_frame(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            runtime = WatchEvidenceRuntime(
                command_runner=FailingSceneRunner(
                    duration_seconds=10.0, scene_times=()
                ),
                find_executable=lambda name: name,
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare({"sources": [str(source)]})

        self.assertEqual(outcome.state, "partial")
        self.assertIsNotNone(outcome.evidence.metadata)
        self.assertIsNone(outcome.evidence.visual)
        self.assertEqual(outcome.coverage.visual, "none")
        self.assertTrue(
            any("Visual preparation failed" in warning for warning in outcome.warnings)
        )

    def test_missing_source_dimensions_refuses_unverifiable_visual_frames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            source.write_bytes(b"synthetic fixture")
            runtime = WatchEvidenceRuntime(
                command_runner=RecordingMediaRunner(
                    duration_seconds=5.0,
                    scene_times=(1.0, 4.0),
                    source_width=None,
                    source_height=None,
                ),
                find_executable=lambda name: name,
                artifact_root=root / "artifacts",
            )

            outcome = runtime.prepare({"sources": [str(source)]})

        visual = outcome.evidence.visual  # type: ignore[union-attr]
        self.assertFalse(visual.frames)
        self.assertEqual(outcome.coverage.visual, "none")
        self.assertTrue(
            any("aspect-correct JPEG" in warning for warning in outcome.warnings),
            outcome.warnings,
        )


if __name__ == "__main__":
    unittest.main()
