from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from watch_transcription import (  # noqa: E402
    BatchTranscriptionFailure,
    BatchTranscriptionModule,
    BatchTranscriptionSuccess,
    PreparedAudioUpload,
    ProviderCallError,
    ProviderChunkResult,
    ProviderDescriptor,
    ProviderSegment,
    development_transcription_registry,
    release_transcription_registry,
)


class RecordingAdapter:
    descriptor = ProviderDescriptor(
        provider="openai",
        model="fixture-model",
        destination="https://provider.example/v1/audio/transcriptions",
        privacy_url="https://provider.example/privacy",
        max_chunk_bytes=1_024,
        max_encoded_request_bytes=2_048,
    )

    def __init__(self) -> None:
        self.uploads: list[object] = []

    def transcribe_chunk(self, upload: object) -> ProviderChunkResult:
        self.uploads.append(upload)
        return ProviderChunkResult(
            language="en",
            segments=(ProviderSegment("Prepared audio only", 0.0, 1.0),),
        )


class RaisingAdapter(RecordingAdapter):
    def transcribe_chunk(self, upload: object) -> ProviderChunkResult:
        self.uploads.append(upload)
        raise RuntimeError("source=/private/workspace/video.mp4 credential=canary")


class BatchTranscriptionModuleTests(unittest.TestCase):
    def test_module_passes_only_prepared_audio_facts_to_adapter(self) -> None:
        adapter = RecordingAdapter()
        module = BatchTranscriptionModule(adapter)

        result = module.transcribe(
            PreparedAudioUpload(
                data=b"prepared-audio",
                filename="audio-chunk-0001.mp3",
                content_type="audio/mpeg",
            )
        )

        self.assertIsInstance(result, BatchTranscriptionSuccess)
        self.assertEqual(result.result.segments[0].text, "Prepared audio only")
        self.assertEqual(len(adapter.uploads), 1)
        upload = adapter.uploads[0]
        self.assertEqual(upload.data, b"prepared-audio")
        self.assertEqual(upload.filename, "audio-chunk-0001.mp3")
        self.assertEqual(upload.content_type, "audio/mpeg")
        self.assertFalse(hasattr(upload, "offset_seconds"))
        self.assertFalse(hasattr(upload, "duration_seconds"))
        self.assertFalse(hasattr(upload, "source"))
        self.assertFalse(hasattr(upload, "path"))

    def test_module_normalizes_unexpected_adapter_failure_without_raw_detail(self) -> None:
        module = BatchTranscriptionModule(RaisingAdapter())

        result = module.transcribe(
            PreparedAudioUpload(
                data=b"prepared-audio",
                filename="audio-chunk-0001.mp3",
                content_type="audio/mpeg",
            )
        )

        self.assertIsInstance(result, BatchTranscriptionFailure)
        self.assertEqual(result.category, "permanent")
        self.assertFalse(result.retryable)
        self.assertNotIn("/private/workspace", result.safe_detail)
        self.assertNotIn("canary", result.safe_detail)

    def test_provider_route_and_registries_are_immutable_and_release_empty(self) -> None:
        registry = development_transcription_registry()

        with self.assertRaises(TypeError):
            registry["other"] = RecordingAdapter()  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            RecordingAdapter.descriptor.model = "other"  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            registry["openai"].descriptor = RecordingAdapter.descriptor

        self.assertEqual(tuple(registry), ("openai", "groq", "mistral"))
        self.assertEqual(release_transcription_registry(), {})

    def test_module_refuses_a_route_rebound_after_construction(self) -> None:
        adapter = RecordingAdapter()
        module = BatchTranscriptionModule(adapter)
        original_descriptor = module.descriptor
        adapter.descriptor = ProviderDescriptor(
            provider="openai",
            model="replacement-model",
            destination="https://replacement.example/v1/audio/transcriptions",
            privacy_url="https://replacement.example/privacy",
            max_chunk_bytes=1_024,
            max_encoded_request_bytes=2_048,
        )

        result = module.transcribe(
            PreparedAudioUpload(
                data=b"prepared-audio",
                filename="audio-chunk-0001.mp3",
                content_type="audio/mpeg",
            )
        )

        self.assertIsInstance(result, BatchTranscriptionFailure)
        self.assertEqual(result.category, "permanent")
        self.assertFalse(result.retryable)
        self.assertEqual(module.descriptor, original_descriptor)
        self.assertEqual(adapter.uploads, [])

    def test_provider_call_error_is_normalized_without_adapter_detail(self) -> None:
        class TypedFailureAdapter(RecordingAdapter):
            def transcribe_chunk(self, upload: object) -> ProviderChunkResult:
                raise ProviderCallError(
                    category="authentication",
                    retryable=False,
                    safe_detail="adapter-private-detail-canary",
                )

        result = BatchTranscriptionModule(TypedFailureAdapter()).transcribe(
            PreparedAudioUpload(
                data=b"prepared-audio",
                filename="audio-chunk-0001.mp3",
                content_type="audio/mpeg",
            )
        )

        self.assertIsInstance(result, BatchTranscriptionFailure)
        self.assertEqual(result.category, "authentication")
        self.assertNotIn("canary", result.safe_detail)

    def test_module_normalizes_unknown_provider_failure_categories(self) -> None:
        class UnknownFailureAdapter(RecordingAdapter):
            def transcribe_chunk(self, upload: object) -> ProviderChunkResult:
                raise ProviderCallError(
                    category="unknown",  # type: ignore[arg-type]
                    retryable=True,
                    safe_detail="adapter-private-detail-canary",
                )

        result = BatchTranscriptionModule(UnknownFailureAdapter()).transcribe(
            PreparedAudioUpload(
                data=b"prepared-audio",
                filename="audio-chunk-0001.mp3",
                content_type="audio/mpeg",
            )
        )

        self.assertIsInstance(result, BatchTranscriptionFailure)
        self.assertEqual(result.category, "permanent")
        self.assertFalse(result.retryable)
        self.assertNotIn("canary", result.safe_detail)


if __name__ == "__main__":
    unittest.main()
