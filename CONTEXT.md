# Codex Video Analysis

This context defines the language for specifying a Codex Desktop skill that can inspect video evidence and answer questions grounded in what was shown and said.

## Language

**Upstream watch skill**:
The MIT-licensed `bradautomates/claude-video` skill used as the behavioral reference for this effort.
_Avoid_: Original skill, Claude skill, source skill

**Codex-native watch skill**:
The skill specified for Codex Desktop, preserving the upstream watch skill's user-visible behavior while conforming to Codex's interaction and permission model.
_Avoid_: Clone, conversion, Codex port

**Canonical skill source**:
The authoritative, repository-owned definition of the Codex-native watch skill from which personal installations are tested.
_Avoid_: Global copy, installed copy

**Behavioral parity**:
Equivalent user-visible capabilities and outcomes without requiring identical host-specific instructions or internal structure.
_Avoid_: Exact copy, file parity, implementation parity

**Implementation-ready specification**:
The Wayfinder destination: a specification with no unresolved product, workflow, safety, packaging, or acceptance decisions needed before implementation can begin.
_Avoid_: Implementation plan, working skill, prototype

**Parity baseline**:
The user-visible behavior of the upstream watch skill against which the Codex-native watch skill is specified and later evaluated; it is not the implementation source.
_Avoid_: Source template, codebase baseline, upstream implementation

**Parity snapshot**:
Upstream watch skill release `v0.2.0` at commit `83da59fa78c3eee9e20f515fe75c438bb5166efd`, fixed as the reference for this specification effort.
_Avoid_: Latest upstream, upstream main

**Independent reimplementation**:
A newly written implementation whose requirements and acceptance cases may be informed by upstream documentation, observable behavior, and tests, without copying or adapting upstream implementation code.
_Avoid_: Clean-room implementation, fork, source port

**Watch request**:
A conversational request to inspect exactly one public `yt-dlp`-compatible video URL or one local video file, together with an optional question and any focus, detail, or cue preferences. It may select `watch` explicitly with `$watch` or match implicitly only when the user clearly asks Codex to inspect, analyze, summarize, or answer from that video.
_Avoid_: Video job, playlist request, watch invocation

**Detail mode**:
One of the four user-facing evidence-density choices: `transcript`, `efficient`, `balanced`, or `token-burner`.
_Avoid_: Quality setting, frame mode

**Focus interval**:
An optional, contiguous source-absolute time range that limits the portion of a video considered by one watch request.
_Avoid_: Clip, trim window, segment

**Cue**:
A source-absolute timestamp that expresses the user's intent to inspect a particular visual moment as pinned evidence.
_Avoid_: Screenshot request, frame marker

**Evidence stream**:
One of the distinct sources from which an answer may draw claims: visual evidence, transcript evidence, or source metadata. Evidence streams may be synthesized but never silently conflated.
_Avoid_: Modality, data source

**Visual observation**:
A plain description of what the host actually saw in one selected frame, recorded only after inspection and bound to that frame's chronological position. It does not carry a caller-written timestamp or become evidence for another frame.
_Avoid_: Visual inference, frame caption, image guess

**Grounded claim**:
One material user-facing finding whose evidence references resolve to inspected metadata, Raw transcript segments, or visual observations. Its stream labels and source-absolute citations are derived from that evidence.
_Avoid_: Draft claim, answer sentence, model assertion

**Evidence reference**:
A structural identity for one metadata field, Raw transcript segment position, or visual observation. It carries no caller-written timestamp, provenance, selection reason, or artifact path.
_Avoid_: Citation string, source link, evidence pointer

**Raw transcript**:
The normalized, timestamped source text derived from captions or an optional transcription provider, not the original VTT, provider response, or unprocessed rolling-caption cues.
_Avoid_: Caption file, provider JSON, verbatim transcript

**Current source**:
The most recent single, unambiguous video URL or resolved local video path established by a watch request in the same task. It remains current even when later acquisition or processing fails, until another source replaces it.
_Avoid_: Active video, cached video, last upload

**Choice kind**:
The category of pending user selection in a `decision_required` outcome: caption track, audio track, or transcription.
_Avoid_: Decision type, selection category

**Decision handle**:
An opaque task-session token emitted with a `decision_required` outcome. It binds sanitized choices to that session only; it neither selects a choice nor authorizes cross-task reuse.
_Avoid_: Session key, persistent token, reusable cache key

**Evidence coverage**:
The extent to which an evidence stream covers the scope requested by the user: `complete`, `partial`, or `none`.
_Avoid_: Confidence, completeness score

**Answerability**:
Whether trustworthy available evidence supports the requested conclusion: `supported`, `uncertain`, or `unsupported`. Answerability is independent of evidence coverage.
_Avoid_: Coverage, confidence score

**Audio-upload consent**:
Fresh, provider-specific authorization to send extracted audio for exactly one watch request. It is distinct from provider selection and separate host command-network approval.
_Avoid_: API permission, network consent, persistent opt-in

**Watch workspace**:
A uniquely identified temporary directory containing the intermediate media and evidence for one watch request and eligible for removal only through validated cleanup.
_Avoid_: Temp folder, work dir, cache
