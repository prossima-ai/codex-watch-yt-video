"""Hermetic contract checks for the repository's public watch documentation."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
README = REPOSITORY_ROOT / "README.md"
SECURITY_AND_PRIVACY = REPOSITORY_ROOT / "docs" / "security-and-privacy.md"
SETUP_AND_TROUBLESHOOTING = REPOSITORY_ROOT / "docs" / "setup-and-troubleshooting.md"
THIRD_PARTY_NOTICES = REPOSITORY_ROOT / "THIRD_PARTY_NOTICES.md"
PROVENANCE = REPOSITORY_ROOT / "docs" / "provenance.md"
SPECIFICATION = REPOSITORY_ROOT / "docs" / "spec" / "watch-skill.md"
WATCH_SKILL = REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "SKILL.md"
DOMAIN_CONTEXT = REPOSITORY_ROOT / "CONTEXT.md"
PUBLIC_DOCUMENTS = (
    README,
    SETUP_AND_TROUBLESHOOTING,
    SECURITY_AND_PRIVACY,
    THIRD_PARTY_NOTICES,
    PROVENANCE,
)
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


class DocumentationContractTests(unittest.TestCase):
    def test_security_and_privacy_is_a_classified_public_artifact(self) -> None:
        document = self._collapsed(SECURITY_AND_PRIVACY)

        self.assertIn("# Security and privacy", document)
        self.assertIn("`confirmed`", document)
        self.assertIn("`implementation requirement`", document)
        self.assertIn("`unsupported/out of scope`", document)
        self.assertIn(
            "docs/security-and-privacy.md", README.read_text(encoding="utf-8")
        )

    def test_security_document_discloses_source_and_local_processing_boundary(
        self,
    ) -> None:
        document = self._collapsed(SECURITY_AND_PRIVACY)

        for disclosure in (
            "yt-dlp-compatible HTTP(S) URL",
            "one lawful local video",
            "metadata, captions, frames, media, and audio locally",
            "Native captions and visual evidence remain local by default",
            "No skill-controlled telemetry, analytics, or crash uploads",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, document)
        self.assertRegex(
            document,
            r"Private, authenticated,\s+DRM-protected,\s+live,\s+playlist,\s+"
            r"ambiguous, and multiple sources",
        )
        self.assertRegex(
            document,
            r"`yt-dlp` may contact the\s+named source host only after separate "
            r"command-network approval",
        )
        self.assertRegex(
            document,
            r"Codex, installed tools, a source site,\s+or a selected provider",
        )

    def test_public_url_scope_requires_ytdlp_compatible_http_or_https(self) -> None:
        for document_path in (README, SECURITY_AND_PRIVACY):
            with self.subTest(document=document_path.name):
                self.assertIn(
                    "yt-dlp-compatible HTTP(S) URL",
                    document_path.read_text(encoding="utf-8"),
                )

    def test_docs_distinguish_media_download_and_caption_contact_paths(self) -> None:
        readme = README.read_text(encoding="utf-8")
        security = self._collapsed(SECURITY_AND_PRIVACY)

        self.assertRegex(
            readme, r"not a general-purpose downloader\s+or\s+export tool"
        )
        self.assertRegex(
            security,
            r"directly retrieves the selected public HTTPS caption resource",
        )
        self.assertIn("not every source contact goes through `yt-dlp`", security)
        self.assertIn("release/spec gate", security)

    def test_direct_caption_network_action_has_a_separate_bound_receipt_contract(
        self,
    ) -> None:
        specification = self._collapsed(SPECIFICATION)
        security = self._collapsed(SECURITY_AND_PRIVACY)
        setup = self._collapsed(SETUP_AND_TROUBLESHOOTING)
        skill = self._collapsed(WATCH_SKILL)

        for disclosure in (
            "separate, explicit approval-gated caption-network action",
            "opaque, single-use approval receipt",
            "five minutes or request end, whichever comes first",
            "same Watch request, source, runtime session, workspace",
            "selected caption track, supported format, byte cap",
            "exact normalized HTTPS origin",
            "Receipt verification MUST occur before any DNS or HTTP request",
            "zero outbound caption HTTP attempts",
            "Failure, cancellation, denial, or retry invalidates",
            "`urllib.request` HTTPS path",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, specification)

        for disclosure in (
            "caption hostname, purpose, selected track, format, and byte cap",
            "must not display, log, persist as evidence, or accept back as user input",
            "raw signed caption URL",
            "query strings, credentials, tokens",
            "user-facing outcome, exception, diagnostic, snapshot, or log",
            "sealed Python `urllib.request` HTTPS path",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, security)

        self.assertIn("caption_network_approval", skill)
        self.assertIn("separate native-caption network action", setup)
        self.assertIn("only action handle", specification)

    def test_direct_caption_network_policy_is_fail_closed_and_never_transcribes(
        self,
    ) -> None:
        specification = self._collapsed(SPECIFICATION)
        security = self._collapsed(SECURITY_AND_PRIVACY)

        for disclosure in (
            "public HTTPS",
            "embedded credentials",
            "IP literals",
            "nonstandard ports",
            "all resolved IPv4 and IPv6 addresses",
            "revalidated at every redirect hop",
            "strict redirect limit of three",
            "redirect loop",
            "HTTPS-to-HTTP downgrade",
            "new otherwise-public origin returns `decision_required`",
            "Never forward sensitive authorization information",
            "Content-Length",
            "actual streamed bytes",
            "exact byte-cap boundary",
            "partial caption data as success",
            "never invokes transcription",
            "provider credential",
            "provider client",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, specification)

        for disclosure in (
            "success (`ready`)",
            "denial (`stopped`)",
            "unavailability (`partial`)",
            "failure (`partial`)",
            "does not fall back to transcription",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, security)

    def test_domain_context_names_the_caption_network_action_and_release_disabled_transcription(self) -> None:
        context = self._collapsed(DOMAIN_CONTEXT)

        for disclosure in (
            "direct caption-network action",
            "Caption-network action",
            "Native-caption approval receipt",
            "single-use same-session receipt",
            "Release-facing transcription is disabled",
            "does not offer `transcription`",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, context)

    def test_transcription_is_release_disabled_pending_effective_request_size_gate(
        self,
    ) -> None:
        specification = self._collapsed(SPECIFICATION)
        security = self._collapsed(SECURITY_AND_PRIVACY)
        notices = self._collapsed(THIRD_PARTY_NOTICES)
        skill = self._collapsed(WATCH_SKILL)

        for document in (specification, security, notices, skill):
            with self.subTest(document=document[:40]):
                self.assertIn("release-disabled", document)
                self.assertIn("multipart/form-data", document)
                self.assertIn("not merely nominal media-file size", document)
                self.assertIn("separate explicit human approval", document)

        self.assertIn("No release-facing action surface may invoke", specification)
        self.assertIn("provider credentials or provider clients", specification)

    def test_provenance_has_a_decision_44_pending_evidence_record(self) -> None:
        provenance = self._collapsed(PROVENANCE)

        for disclosure in (
            "Decision #44 implementation evidence record",
            "35a0c29bc9e264f533837adf40424aa95e55dcc1",
            "PENDING — final local implementation commit has not yet been created",
            "PENDING root final validation",
            "Live public-caption validation | `BLOCKED`",
            "Human release decision | `PENDING`",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, provenance)

    def test_security_document_requires_distinct_provider_and_secret_gates(
        self,
    ) -> None:
        document = self._collapsed(SECURITY_AND_PRIVACY)

        for disclosure in (
            "`decision_required`",
            "`consent_required`",
            "Only bounded extracted audio chunks may be uploaded",
            "No automatic audio upload",
            "`OPENAI_API_KEY` and `GROQ_API_KEY`",
            "never request secrets in chat",
            "scan `.env`",
            "persist or log a credential",
            "probe an unselected provider",
            "silently fall back",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, document)
        self.assertRegex(
            document,
            r"Provider selection, audio-track selection, fresh provider-specific "
            r"audio-upload consent, and provider-network approval are distinct gates",
        )
        self.assertRegex(
            document,
            r"never receives\s+video bytes, video paths, workspace paths, unrelated "
            r"tracks, or another\s+provider's state",
        )

    def test_security_document_explains_outcomes_reuse_and_fail_closed_cleanup(
        self,
    ) -> None:
        document = SECURITY_AND_PRIVACY.read_text(encoding="utf-8")

        for disclosure in (
            "`decision_required` and `consent_required` are nonterminal",
            "`stopped`, `failed`, and `canceled` are terminal",
            "same-task-only evidence reuse",
            "no automatic source reacquisition or automatic deletion",
            "Explicit, validated, fail-closed cleanup only",
            "`cleanup_deferred`",
            "`cleanup_refused`",
            "`cleanup_incomplete`",
            "`cleanup_succeeded`",
            "`cleanup_already_absent`",
            "macOS",
            "preserves the workspace rather than risking deletion",
            "any already-eligible same-task reuse remains eligible",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, document)
        self.assertRegex(
            document, r"no global media library or cross-task evidence\s+cache"
        )

    def test_readme_states_classified_scope_and_verification_limits(self) -> None:
        readme = self._collapsed(README)

        for disclosure in (
            "Claim classification",
            "`confirmed`",
            "`implementation requirement`",
            "`unsupported/out of scope`",
            "v0.1 is macOS Codex Desktop only, private, and unlicensed for "
            "redistribution",
            "Captions-first",
            "does not prove live Desktop discovery",
            "docs/setup-and-troubleshooting.md",
            "docs/security-and-privacy.md",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, readme)
        self.assertRegex(
            readme.casefold(), r"source-host and\s+provider-network approvals are separate"
        )

    def test_setup_preserves_manual_refusals_and_explains_approval_flow(self) -> None:
        setup = self._collapsed(SETUP_AND_TROUBLESHOOTING)

        for disclosure in (
            "Claim classification",
            "`confirmed`",
            "`implementation requirement`",
            "`unsupported/out of scope`",
            "[ -e \"$target\" ] || [ -L \"$target\" ]",
            "Do not use `ln -f`",
            "Do not use a bare `ln -s`",
            "no executable installation command",
            "no duplicate-name precedence",
            "Never copy the package to a personal location",
            "Never self-install",
            "Never self-update",
            "Never overwrite, remove, repair, force",
            "Do not mutate global configuration",
            "Do not install or update a dependency",
            "Transcription is release-disabled",
            "provider-network approval",
            "No live Desktop probe, personal installation, media acquisition, or "
            "provider request was performed for #28",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, setup)
        self.assertRegex(
            setup, r"source-host command-network\s+approval"
        )

    def test_third_party_notices_bound_licenses_and_current_provider_claims(
        self,
    ) -> None:
        notices = THIRD_PARTY_NOTICES.read_text(encoding="utf-8")

        for disclosure in (
            "`confirmed`",
            "`implementation requirement`",
            "`unsupported/out of scope`",
            "yt-dlp",
            "Unlicense",
            "FFmpeg",
            "`ffprobe`",
            "--enable-gpl",
            "--enable-version3",
            "GPL-3.0-or-later",
            "inspection environment only, not a supported minimum",
            "Python 3.13.3",
            "PSF-2.0",
            "OpenAI `whisper-1`",
            "Groq `whisper-large-v3`",
            "Checked: 2026-08-14",
            "not a live transcription request",
            "25,165,823",
            "25,000,000",
            "release gate",
            "bradautomates/claude-video",
            "83da59fa78c3eee9e20f515fe75c438bb5166efd",
            "MIT",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, notices)
        self.assertRegex(
            notices, r"no\s+third-party code, binary, or license text is bundled"
        )

    def test_security_document_records_date_bound_provider_disclosures_and_gate(
        self,
    ) -> None:
        document = SECURITY_AND_PRIVACY.read_text(encoding="utf-8")

        for disclosure in (
            "Provider documentation checked: 2026-08-14",
            "OpenAI `whisper-1`",
            "Groq `whisper-large-v3`",
            "https://developers.openai.com/api/docs/guides/your-data#"
            "default-usage-policies-by-endpoint",
            "https://console.groq.com/docs/your-data",
            "not a live transcription request",
            "not a blanket claim about OpenAI, ChatGPT, or other endpoints",
            "temporary reliability/abuse logs up to 30 days",
            "usage metadata is always collected",
            "25,165,823",
            "25,000,000",
            "disable that provider for release",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, document)

    def test_provenance_records_pinned_history_boundary_and_release_gates(self) -> None:
        provenance = PROVENANCE.read_text(encoding="utf-8")

        for disclosure in (
            "0f1f224e818f52853d4d9e8356abf7be14c172a1",
            "858b139873aeff3b22a7338acbd14511078f0b33",
            "83da59fa78c3eee9e20f515fe75c438bb5166efd",
            "Independent reimplementation",
            "Python 3.13.3",
            "FFmpeg/ffprobe 9.0",
            "ordinary 768 px JPEG frames",
            "targeted 1024 px escalation",
            "chronological batches of at most eight",
            "Issue #13",
            "Issue #9",
            "Clean-room review status",
            "remaining live/release gates",
            "future immutable release commit",
            "`implementation requirement`",
            "Neither the upstream project nor OpenAI, Groq, or other providers "
            "endorse or are affiliated with this project",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, provenance)
        self.assertRegex(
            provenance, r"no upstream\s+implementation, tests, or assets were copied"
        )

    def test_security_document_does_not_promise_a_public_response_channel(self) -> None:
        document = SECURITY_AND_PRIVACY.read_text(encoding="utf-8")

        self.assertIn("v0.1 makes no public security-response promise", document)
        self.assertIn(
            "A designated private reporting channel is required before public "
            "distribution",
            document,
        )

    def test_related_record_evidence_names_the_current_worktree(self) -> None:
        document = SECURITY_AND_PRIVACY.read_text(encoding="utf-8")

        self.assertIn("Issue #29 worktree/diff", document)
        self.assertRegex(
            document,
            r"does not claim those files existed at the\s+pinned implementation base",
        )

    def test_public_document_artifacts_are_classified_and_internally_linked(
        self,
    ) -> None:
        for document_path in PUBLIC_DOCUMENTS:
            with self.subTest(document=document_path.name):
                document = document_path.read_text(encoding="utf-8")
                self.assertIn("Claim classification", document)
                self.assertIn("`confirmed`", document)
                self.assertIn("`implementation requirement`", document)
                self.assertIn("`unsupported/out of scope`", document)
                self._assert_valid_internal_links(document_path, document)

        for source, destination in (
            (README, "docs/setup-and-troubleshooting.md"),
            (README, "docs/security-and-privacy.md"),
            (README, "THIRD_PARTY_NOTICES.md"),
            (README, "docs/provenance.md"),
            (SECURITY_AND_PRIVACY, "../THIRD_PARTY_NOTICES.md"),
            (SECURITY_AND_PRIVACY, "provenance.md"),
            (THIRD_PARTY_NOTICES, "docs/provenance.md"),
        ):
            with self.subTest(source=source.name, destination=destination):
                self.assertIn(destination, source.read_text(encoding="utf-8"))

    def _assert_valid_internal_links(self, document_path: Path, document: str) -> None:
        for raw_destination in MARKDOWN_LINK.findall(document):
            destination = raw_destination.split(maxsplit=1)[0].strip("<>")
            if "://" in destination or destination.startswith("mailto:"):
                continue
            relative_target, _, anchor = destination.partition("#")
            target = (
                document_path
                if not relative_target
                else document_path.parent / relative_target
            )
            with self.subTest(document=document_path.name, destination=destination):
                self.assertTrue(target.is_file(), f"missing internal target: {target}")
                if anchor:
                    self.assertIn(anchor, self._heading_slugs(target))

    @staticmethod
    def _collapsed(document_path: Path) -> str:
        return re.sub(r"\s+", " ", document_path.read_text(encoding="utf-8"))

    @staticmethod
    def _heading_slugs(document_path: Path) -> set[str]:
        seen: dict[str, int] = {}
        slugs: set[str] = set()
        for line in document_path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
            if match is None:
                continue
            slug = re.sub(r"[^a-z0-9 -]", "", match.group(1).casefold())
            slug = re.sub(r"\s+", "-", slug).strip("-")
            occurrence = seen.get(slug, 0)
            seen[slug] = occurrence + 1
            slugs.add(slug if occurrence == 0 else f"{slug}-{occurrence}")
        return slugs


if __name__ == "__main__":
    unittest.main()
