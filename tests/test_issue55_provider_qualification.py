from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from watch_transcription import (  # noqa: E402
    BatchTranscriptionFailure,
    BatchTranscriptionModule,
    MistralTranscriptionProvider,
    PreparedAudioUpload,
    development_transcription_registry,
    release_transcription_registry,
)


class Issue55ProviderQualificationTests(unittest.TestCase):
    @staticmethod
    def _prepared_upload() -> PreparedAudioUpload:
        return PreparedAudioUpload(
            data=b"prepared-audio",
            filename="audio-chunk-0001.mp3",
            content_type="audio/mpeg",
        )

    def test_mistral_is_development_only_and_every_provider_is_release_unavailable(self) -> None:
        development_registry = development_transcription_registry()

        self.assertIsInstance(
            development_registry["mistral"], MistralTranscriptionProvider
        )
        self.assertEqual(release_transcription_registry(), {})

    def test_mistral_malformed_response_becomes_a_redacted_typed_failure(self) -> None:
        class MalformedResponseTransport:
            def send_encoded(self, *_args: object, **_kwargs: object) -> object:
                return {
                    "model": "voxtral-mini-2602",
                    "usage": {"prompt_audio_seconds": "usage-canary"},
                    "segments": "not-segments",
                }

        result = BatchTranscriptionModule(
            MistralTranscriptionProvider(
                credential_reader=lambda _name: "provider-secret",
                transport=MalformedResponseTransport(),
            )
        ).transcribe(self._prepared_upload())

        self.assertIsInstance(result, BatchTranscriptionFailure)
        self.assertEqual(result.category, "permanent")
        self.assertFalse(result.retryable)
        self.assertNotIn("usage-canary", result.safe_detail)
        self.assertNotIn("provider-secret", result.safe_detail)

    def test_mistral_untyped_transport_failure_becomes_a_redacted_typed_failure(self) -> None:
        class RaisingTransport:
            def send_encoded(self, *_args: object, **_kwargs: object) -> object:
                raise RuntimeError(
                    "remote-file=https://provider.example/secret source=/private/video.mp4"
                )

        result = BatchTranscriptionModule(
            MistralTranscriptionProvider(
                credential_reader=lambda _name: "provider-secret",
                transport=RaisingTransport(),
            )
        ).transcribe(self._prepared_upload())

        self.assertIsInstance(result, BatchTranscriptionFailure)
        self.assertEqual(result.category, "permanent")
        self.assertFalse(result.retryable)
        self.assertNotIn("remote-file", result.safe_detail)
        self.assertNotIn("/private/video.mp4", result.safe_detail)


if __name__ == "__main__":
    unittest.main()
