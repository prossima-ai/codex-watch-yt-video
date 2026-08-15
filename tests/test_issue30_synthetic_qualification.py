from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import json

from issue30_synthetic_media import (
    build_review_bundle,
    canonical_json_bytes,
    generate_synthetic_media,
    sha256_file,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "scripts"
TRUTH_TEMPLATE = REPOSITORY_ROOT / "tests" / "fixtures" / "issue30_truth_manifest.json"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from watch_evidence import (  # noqa: E402
    FrameEscalation,
    FrameInspection,
    WatchEvidenceRuntime,
)


class RecordingInspector:
    def __init__(self, *, request_detail: bool = False) -> None:
        self.request_detail = request_detail
        self.batches: list[tuple[object, ...]] = []
        self._requested = False

    def inspect(self, batches: tuple[tuple[object, ...], ...]) -> FrameInspection:
        self.batches.extend(batches)
        frames = tuple(frame for batch in batches for frame in batch)
        escalations = ()
        if self.request_detail and not self._requested and frames:
            self._requested = True
            first = frames[0]
            escalations = (
                FrameEscalation(
                    first.path, "The small material detail needs a closer inspection."
                ),
            )
        return FrameInspection(
            "complete",
            tuple(frame.path for frame in frames),
            escalations=escalations,
        )


def local_media_tool(name: str) -> str | None:
    return shutil.which(name) if name in {"ffmpeg", "ffprobe"} else None


LOCAL_MEDIA_TOOLS_AVAILABLE = all(
    shutil.which(name) is not None for name in ("ffmpeg", "ffprobe")
)


class SyntheticQualificationTests(unittest.TestCase):
    def test_versioned_truth_template_declares_construction_and_expected_conflict(self) -> None:
        template = json.loads(TRUTH_TEMPLATE.read_text(encoding="utf-8"))

        self.assertEqual(template["schema_version"], "issue30-synthetic-v1")
        self.assertEqual(template["seed"], "issue30-visible-ground-truth-20260815")
        self.assertIn("multi-track", template["fixture_roles"])
        self.assertEqual(
            template["deliberate_contradictions"][0]["transcript"],
            "The panel is green.",
        )
        self.assertEqual(
            template["expected_source_absolute_facts"][0]["fixture"], "multi-track"
        )
        self.assertLessEqual(template["construction"]["scale_frame_rate"], 2)
        self.assertEqual(template["hash_policy"], "generated-at-run-sha256")

    @unittest.skipUnless(
        LOCAL_MEDIA_TOOLS_AVAILABLE,
        "Issue #30 synthetic qualification is BLOCKED: ffmpeg and ffprobe are required.",
    )
    def test_generated_fixture_manifest_covers_the_required_fixture_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            generated = generate_synthetic_media(Path(directory))

        self.assertEqual(generated.manifest["schema_version"], "issue30-synthetic-v1")
        self.assertEqual(
            set(generated.manifest["fixture_roles"]),
            {
                "cut-heavy",
                "static",
                "held-slide-small-change",
                "portrait",
                "silent",
                "captioned-spoken-content",
                "multi-track",
                "scale",
            },
        )
        self.assertLessEqual(generated.manifest["construction"]["scale_frame_rate"], 2)

    @unittest.skipUnless(
        LOCAL_MEDIA_TOOLS_AVAILABLE,
        "Issue #30 synthetic qualification is BLOCKED: ffmpeg and ffprobe are required.",
    )
    def test_generated_sources_are_hashed_and_expose_the_expected_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            generated = generate_synthetic_media(Path(directory))
            sources = generated.manifest["sources"]
            self.assertEqual(
                sources["portrait"]["streams"]["video_geometry"], [[180, 320]]
            )
            self.assertEqual(sources["silent"]["streams"]["stream_types"], ["video"])
            self.assertEqual(
                sources["multi-track"]["streams"]["stream_types"],
                ["video", "audio", "audio", "subtitle"],
            )
            self.assertEqual(
                sources["multi-track"]["streams"]["audio_languages"],
                ["eng", "spa"],
            )
            self.assertEqual(
                sources["multi-track"]["streams"]["subtitle_languages"], ["eng"]
            )
            self.assertEqual(
                sources["cut-heavy"]["streams"]["video_sample_aspect_ratios"],
                ["1:1"],
            )
            self.assertEqual(
                sources["cut-heavy"]["streams"]["video_display_aspect_ratios"],
                ["16:9"],
            )
            for name, source in generated.sources.items():
                self.assertEqual(sources[name]["sha256"], sha256_file(source))
        self.assertEqual(
            generated.manifest["deliberate_contradictions"][0]["transcript"],
            "The panel is green.",
        )

    @unittest.skipUnless(
        LOCAL_MEDIA_TOOLS_AVAILABLE,
        "Issue #30 synthetic qualification is BLOCKED: ffmpeg and ffprobe are required.",
    )
    def test_two_fresh_generated_corpora_have_identical_canonical_truth_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as first_directory, tempfile.TemporaryDirectory() as second_directory:
            first = generate_synthetic_media(Path(first_directory))
            second = generate_synthetic_media(Path(second_directory))

        first_hashes = {
            name: record["sha256"] for name, record in first.manifest["sources"].items()
        }
        second_hashes = {
            name: record["sha256"] for name, record in second.manifest["sources"].items()
        }
        self.assertEqual(
            [name for name in first_hashes if first_hashes[name] != second_hashes[name]],
            [],
        )
        self.assertEqual(canonical_json_bytes(first.manifest), canonical_json_bytes(second.manifest))

    @unittest.skipUnless(
        LOCAL_MEDIA_TOOLS_AVAILABLE,
        "Issue #30 synthetic qualification is BLOCKED: ffmpeg and ffprobe are required.",
    )
    def test_s04_review_bundle_exposes_only_frame_identity_time_and_candidate_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = generate_synthetic_media(root / "generated")
            bundle = build_review_bundle(generated, root / "review-bundle")

            reviewed_frame = root / "review-bundle" / bundle["frames"][0]["relative_path"]
            self.assertTrue(reviewed_frame.is_file())
            self.assertEqual(bundle["frames"][0]["sha256"], sha256_file(reviewed_frame))
            self.assertEqual(generated.manifest["review_frame"]["fixture"], "multi-track")
            self.assertEqual(
                generated.manifest["deliberate_contradictions"][0]["fixture"],
                "multi-track",
            )
        rendered_bundle = json.dumps(bundle)
        self.assertNotIn("The panel is green.", rendered_bundle)
        self.assertEqual(bundle["frames"][0]["source_absolute_time_seconds"], 1)
        self.assertEqual(
            bundle["candidate_claims"],
            [
                {
                    "id": "visible-panel",
                    "claim": "At the cited time, the frame shows a blue field with a centered brighter blue rectangle.",
                }
            ],
        )

    @unittest.skipUnless(
        LOCAL_MEDIA_TOOLS_AVAILABLE,
        "Issue #30 synthetic qualification is BLOCKED: ffmpeg and ffprobe are required.",
    )
    def test_actual_local_extraction_is_jpeg_bounded_and_can_escalate_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = generate_synthetic_media(root / "generated")
            inspector = RecordingInspector(request_detail=True)
            runtime = WatchEvidenceRuntime(
                find_executable=local_media_tool,
                frame_inspector=inspector,
                artifact_root=root / "runtime-artifacts",
            )
            try:
                outcome = runtime.prepare(
                    {
                        "sources": [str(generated.sources["cut-heavy"])],
                        "detail": "balanced",
                        "max_frames": 3,
                        "question": "What is the small material detail?",
                    }
                )
            finally:
                runtime.close()

        self.assertIsNotNone(outcome.evidence, outcome.report_markdown)
        self.assertIsNotNone(outcome.evidence.visual, outcome.report_markdown)  # type: ignore[union-attr]
        visual = outcome.evidence.visual  # type: ignore[union-attr]
        self.assertTrue(visual.frames)
        self.assertTrue(all(frame.format == "jpeg" for frame in visual.frames))
        ordinary_frames = [frame for frame in visual.frames if frame.resolution_reason is None]
        detail_frames = [frame for frame in visual.frames if frame.resolution_reason]
        self.assertTrue(ordinary_frames)
        self.assertEqual(len(detail_frames), 1)
        self.assertTrue(all(frame.width <= 768 for frame in ordinary_frames))
        self.assertTrue(all(frame.width <= 1024 for frame in detail_frames))
        self.assertTrue(all(frame.resolution_reason for frame in detail_frames))
        self.assertEqual(visual.inspection_state, "complete")
        self.assertTrue(all(len(batch) <= 8 for batch in visual.inspection_batches))
        self.assertEqual(
            [frame.chronological_position for frame in visual.frames],
            list(range(1, len(visual.frames) + 1)),
        )

    @unittest.skipUnless(
        LOCAL_MEDIA_TOOLS_AVAILABLE,
        "Issue #30 synthetic qualification is BLOCKED: ffmpeg and ffprobe are required.",
    )
    def test_scale_modes_have_exact_caps_and_chronological_batches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = generate_synthetic_media(root / "generated")
            results = {}
            for detail in ("transcript", "efficient", "balanced", "token-burner"):
                inspector = RecordingInspector()
                runtime = WatchEvidenceRuntime(
                    find_executable=local_media_tool,
                    frame_inspector=inspector,
                    artifact_root=root / f"runtime-{detail}",
                )
                request = {
                    "sources": [str(generated.sources["scale"])],
                    "detail": detail,
                    "focus": [0, 339],
                    "keep_duplicates": True,
                    "question": "Which visual states appear over time?",
                }
                if detail == "token-burner":
                    request["cues"] = [0]
                try:
                    results[detail] = runtime.prepare(request)
                finally:
                    runtime.close()

        visuals = {detail: outcome.evidence.visual for detail, outcome in results.items()}
        self.assertEqual(len(visuals["transcript"].frames), 0)
        self.assertEqual(len(visuals["efficient"].frames), 50)
        self.assertEqual(len(visuals["balanced"].frames), 100)
        self.assertGreaterEqual(len(visuals["token-burner"].frames), 251)
        self.assertTrue(
            any("More than 250 selected frames" in warning for warning in results["token-burner"].warnings)
        )
        self.assertTrue(
            any(
                frame.timestamp_seconds == 0
                and frame.selection_reason == "transcript-cue"
                for frame in visuals["token-burner"].frames
            )
        )
        for visual in visuals.values():
            self.assertTrue(all(len(batch) <= 8 for batch in visual.inspection_batches))
            times = [frame.timestamp_seconds for frame in visual.frames]
            self.assertEqual(times, sorted(times))


if __name__ == "__main__":
    unittest.main()
