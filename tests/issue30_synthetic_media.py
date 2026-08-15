"""Deterministic, temporary media fixtures for Issue #30 qualification.

The generator deliberately writes no media into the repository.  Its callers
must provide a controlled temporary directory and may commit only the schema,
construction inputs, and hashes it returns.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping


GENERATOR_SCHEMA = "issue30-synthetic-v1"
GENERATOR_SEED = "issue30-visible-ground-truth-20260815"
_FFMPEG = "ffmpeg"
_FFPROBE = "ffprobe"


@dataclass(frozen=True)
class SyntheticMedia:
    root: Path
    manifest: dict[str, Any]
    sources: Mapping[str, Path]
    review_frame: Path


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_synthetic_media(root: Path) -> SyntheticMedia:
    """Generate a compact oracle corpus using only local FFmpeg/ffprobe calls."""

    _require_local_media_tools()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    images = root / "ppm"
    sources_directory = root / "sources"
    review_directory = root / "review"
    images.mkdir(exist_ok=True)
    sources_directory.mkdir(exist_ok=True)
    review_directory.mkdir(exist_ok=True)

    _write_cut_sequence(images / "cut", count=6, width=1024, height=576)
    _write_ppm(images / "static.ppm", 320, 180, (30, 120, 80))
    _write_held_slide(images / "held-000.ppm", images / "held-001.ppm")
    _write_ppm(images / "portrait.ppm", 180, 320, (120, 35, 120))
    _write_ppm(images / "silent.ppm", 320, 180, (35, 35, 35))
    _write_cut_sequence(images / "scale", count=340, width=128, height=72)
    captions = root / "spoken-contradiction.srt"
    captions.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nThe panel is green.\n",
        encoding="utf-8",
    )

    sources = {
        "cut-heavy": sources_directory / "cut-heavy.mp4",
        "static": sources_directory / "static.mp4",
        "held-slide-small-change": sources_directory / "held-slide-small-change.mp4",
        "portrait": sources_directory / "portrait.mp4",
        "silent": sources_directory / "silent.mp4",
        "multi-track": sources_directory / "multi-track.mp4",
        "scale": sources_directory / "scale.mp4",
    }
    _encode_sequence(images / "cut-%03d.ppm", sources["cut-heavy"], frame_count=6)
    _encode_still(images / "static.ppm", sources["static"], seconds=3)
    _encode_sequence(
        images / "held-%03d.ppm", sources["held-slide-small-change"], frame_count=2
    )
    _encode_still(images / "portrait.ppm", sources["portrait"], seconds=3)
    _encode_still(images / "silent.ppm", sources["silent"], seconds=3)
    _encode_multi_track(images / "cut-%03d.ppm", captions, sources["multi-track"])
    _encode_sequence(
        images / "scale-%03d.ppm",
        sources["scale"],
        frame_count=340,
        all_intra=True,
    )

    review_frame = review_directory / "visible-claim.jpg"
    _run_ffmpeg(
        [
            "-ss",
            "1",
            "-i",
            str(sources["multi-track"]),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-an",
            "-sn",
            "-dn",
            "-vf",
            "scale=320:-2,setsar=1",
            "-q:v",
            "2",
            "-f",
            "image2",
            str(review_frame),
        ]
    )

    fixture_roles = (
        "cut-heavy",
        "static",
        "held-slide-small-change",
        "portrait",
        "silent",
        "captioned-spoken-content",
        "multi-track",
        "scale",
    )
    source_records = {
        name: {
            "relative_path": str(path.relative_to(root)),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "streams": _stream_summary(path),
        }
        for name, path in sources.items()
    }
    manifest: dict[str, Any] = {
        "schema_version": GENERATOR_SCHEMA,
        "seed": GENERATOR_SEED,
        "fixture_roles": fixture_roles,
        "construction": {
            "image_format": "ppm-p6",
            "cut_geometry": [1024, 576],
            "portrait_geometry": [180, 320],
            "scale_geometry": [128, 72],
            "scale_duration_seconds": 340,
            "scale_frame_rate": 1,
            "caption_track_format": "srt",
        },
        "sources": source_records,
        "expected_source_absolute_facts": [
            {
                "fixture": "multi-track",
                "time_seconds": 1,
                "stream": "visual",
                "fact": "A blue field contains a centered brighter blue rectangle.",
            },
            {
                "fixture": "held-slide-small-change",
                "time_seconds": 1,
                "stream": "visual",
                "fact": "The held purple slide adds one small yellow square.",
            },
            {
                "fixture": "multi-track",
                "time_seconds": 1,
                "stream": "transcript",
                "fact": "The panel is green.",
            },
        ],
        "cue_times_seconds": [1, 4],
        "deliberate_contradictions": [
            {
                "fixture": "multi-track",
                "transcript": "The panel is green.",
                "visible_fact": "The matching generated visual is a blue field with a centered brighter blue rectangle.",
            }
        ],
        "expected_frame_selection": {
            "ordinary_max_width": 768,
            "detail_max_width": 1024,
            "batch_size": 8,
            "scale_modes": {
                "transcript": 0,
                "efficient": 50,
                "balanced": 100,
                "token-burner_minimum": 251,
            },
        },
        "review_frame": {
            "fixture": "multi-track",
            "relative_path": str(review_frame.relative_to(root)),
            "sha256": sha256_file(review_frame),
            "time_seconds": 1,
        },
    }
    (root / "truth-manifest.json").write_bytes(canonical_json_bytes(manifest))
    return SyntheticMedia(root, manifest, sources, review_frame)


def build_review_bundle(generated: SyntheticMedia, directory: Path) -> dict[str, Any]:
    """Create the reviewer-visible S-04 input without oracle/transcript leakage."""

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    frame = directory / "frame-001.jpg"
    shutil.copyfile(generated.review_frame, frame)
    bundle = {
        "schema_version": "issue30-s04-review-input-v1",
        "frames": [
            {
                "id": "frame-001",
                "relative_path": frame.name,
                "source_absolute_time_seconds": 1,
                "sha256": sha256_file(frame),
            }
        ],
        "candidate_claims": [
            {
                "id": "visible-panel",
                "claim": "At the cited time, the frame shows a blue field with a centered brighter blue rectangle.",
            }
        ],
    }
    (directory / "review-input.json").write_bytes(canonical_json_bytes(bundle))
    return bundle


def _require_local_media_tools() -> None:
    missing = tuple(name for name in (_FFMPEG, _FFPROBE) if shutil.which(name) is None)
    if missing:
        raise RuntimeError(
            "Issue #30 synthetic qualification is BLOCKED: missing local tool(s) "
            + ", ".join(missing)
            + "."
        )


def _write_cut_sequence(prefix: Path, *, count: int, width: int, height: int) -> None:
    palette = ((215, 35, 35), (30, 70, 210), (35, 150, 85), (235, 180, 30))
    for index in range(count):
        background = palette[index % len(palette)]
        pixels = bytearray(background * (width * height))
        rectangle = (20, 80, 235) if index in {1, 5} else (245, 245, 245)
        _paint_rectangle(
            pixels,
            width,
            height,
            left=width // 3,
            top=height // 3,
            right=2 * width // 3,
            bottom=2 * height // 3,
            colour=rectangle,
        )
        _write_ppm_bytes(Path(f"{prefix}-{index:03d}.ppm"), width, height, pixels)


def _write_held_slide(first: Path, second: Path) -> None:
    width, height = 320, 180
    pixels = bytearray((100, 55, 180) * (width * height))
    _write_ppm_bytes(first, width, height, pixels)
    _paint_rectangle(
        pixels,
        width,
        height,
        left=148,
        top=76,
        right=160,
        bottom=88,
        colour=(250, 230, 35),
    )
    _write_ppm_bytes(second, width, height, pixels)


def _write_ppm(path: Path, width: int, height: int, colour: tuple[int, int, int]) -> None:
    _write_ppm_bytes(path, width, height, bytearray(colour * (width * height)))


def _write_ppm_bytes(path: Path, width: int, height: int, pixels: bytearray) -> None:
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + bytes(pixels))


def _paint_rectangle(
    pixels: bytearray,
    width: int,
    height: int,
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
    colour: tuple[int, int, int],
) -> None:
    for y in range(max(0, top), min(height, bottom)):
        for x in range(max(0, left), min(width, right)):
            start = (y * width + x) * 3
            pixels[start : start + 3] = bytes(colour)


def _encode_sequence(pattern: Path, output: Path, *, frame_count: int, all_intra: bool = False) -> None:
    arguments = [
        "-framerate",
        "1",
        "-start_number",
        "0",
        "-i",
        str(pattern),
        "-frames:v",
        str(frame_count),
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "setsar=1",
        "-threads",
        "1",
        "-metadata",
        "creation_time=1970-01-01T00:00:00Z",
    ]
    if all_intra:
        arguments.extend(("-g", "1"))
    arguments.append(str(output))
    _run_ffmpeg(arguments)


def _encode_still(image: Path, output: Path, *, seconds: int) -> None:
    _run_ffmpeg(
        [
            "-loop",
            "1",
            "-framerate",
            "1",
            "-i",
            str(image),
            "-t",
            str(seconds),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "setsar=1",
            "-threads",
            "1",
            "-metadata",
            "creation_time=1970-01-01T00:00:00Z",
            str(output),
        ]
    )


def _encode_multi_track(pattern: Path, captions: Path, output: Path) -> None:
    _run_ffmpeg(
        [
            "-framerate",
            "1",
            "-start_number",
            "0",
            "-i",
            str(pattern),
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=8000:duration=6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:sample_rate=8000:duration=6",
            "-i",
            str(captions),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map",
            "2:a:0",
            "-map",
            "3:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "setsar=1",
            "-threads",
            "1",
            "-c:a",
            "aac",
            "-c:s",
            "mov_text",
            "-metadata:s:a:0",
            "language=eng",
            "-metadata:s:a:1",
            "language=spa",
            "-metadata:s:s:0",
            "language=eng",
            "-metadata",
            "creation_time=1970-01-01T00:00:00Z",
            "-t",
            "6",
            str(output),
        ]
    )


def _run_ffmpeg(arguments: list[str]) -> None:
    try:
        completed = subprocess.run(
            [_FFMPEG, "-nostdin", "-y", "-v", "error", *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=45,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("FFmpeg fixture generation exceeded its 45-second bound.") from error
    if completed.returncode != 0:
        raise RuntimeError(f"FFmpeg fixture generation failed: {completed.stderr.strip()}")


def _stream_summary(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            _FFPROBE,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"FFprobe fixture validation failed: {completed.stderr.strip()}")
    payload = json.loads(completed.stdout)
    streams = payload.get("streams", [])
    if not isinstance(streams, list):
        raise RuntimeError("FFprobe did not return a stream list.")
    return {
        "stream_types": [
            stream.get("codec_type")
            for stream in streams
            if isinstance(stream, dict) and isinstance(stream.get("codec_type"), str)
        ],
        "video_geometry": [
            [stream.get("width"), stream.get("height")]
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ],
        "video_sample_aspect_ratios": [
            stream.get("sample_aspect_ratio")
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ],
        "video_display_aspect_ratios": [
            stream.get("display_aspect_ratio")
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ],
        "audio_languages": [
            stream.get("tags", {}).get("language")
            for stream in streams
            if isinstance(stream, dict)
            and stream.get("codec_type") == "audio"
            and isinstance(stream.get("tags"), dict)
        ],
        "subtitle_languages": [
            stream.get("tags", {}).get("language")
            for stream in streams
            if isinstance(stream, dict)
            and stream.get("codec_type") == "subtitle"
            and isinstance(stream.get("tags"), dict)
        ],
    }
