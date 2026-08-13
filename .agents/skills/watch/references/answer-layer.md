# Evidence-grounded answer layer

Use this branch after evidence preparation has produced a terminal outcome. The answer compiler checks evidence identities and writes the user-facing Markdown; it does not acquire evidence or interpret an unseen frame.

## Build the answer request

Pass one JSON object to `python3 -B scripts/answer_watch.py` on standard input without shell-composing its contents. This is a complete, compiler-valid metadata example:

```json
{
  "outcome": {
    "state": "ready",
    "coverage": {
      "metadata": "complete",
      "transcript": "none",
      "visual": "none",
      "overall": "partial"
    },
    "evidence": {
      "metadata": {"title": "Launch update"},
      "transcript": null,
      "visual": null
    },
    "warnings": []
  },
  "question": "What is the source title?",
  "answerability": "supported",
  "relevant_streams": ["metadata"],
  "claims": [
    {
      "id": "source-title",
      "text": "The source title is Launch update.",
      "evidence": [{"stream": "metadata", "field": "title"}]
    }
  ]
}
```

In use, supply the exact decoded JSON outcome returned by the evidence runtime; do not trim or reconstruct it from this small example. `relevant_streams` is required and must name every stream material to the question. The compiler rejects a `supported` answer unless each declared stream has a grounded claim. `claims` is always a list; use an empty list only when a truthful `uncertain` or `unsupported` answer has no supported finding.

Optional request fields are `question`, `visual_observations`, `conflicts`, and `raw_transcript_requested`. Free-form answer reasons and caller-written citation fields are not accepted.

Each material claim needs one or more evidence references:

- Metadata references use a present runtime field: `title`, `uploader`, `duration_seconds`, `container`, `size_bytes`, `video_codec`, `audio_codec`, `width`, `height`, or `is_live`. Metadata citations are source-wide because source time is not applicable.
- transcript segment positions are 1-based in the returned immutable `segments` order. The compiler derives the absolute start/end time and exact provenance.
- A Visual observation is eligible only after the selected frame has been opened and inspected. Bind `frame_position` to the frame's returned `chronological_position`; write `description` from only what was actually visible. The compiler derives the frame's absolute time and selection reason.

Caller-written citation times are invalid. Keep timestamps, provenance, selection reasons, paths, and stream labels out of claim and observation fields. Keep distinct transcript, visual, and metadata findings as distinct claims even when the final conclusion synthesizes them.

Use `supported` only when cited evidence from every declared relevant stream establishes the requested conclusion. Use `uncertain` for a material conflict, ambiguity, or relevant gap. Use `unsupported` when no allowed evidence establishes the conclusion. Record cross-stream conflicts by the two cited claim IDs; a conflict requires `uncertain`.

For a Visual observation, add `visual_observations` with exact objects shaped as `{"id": "unique-id", "frame_position": 4, "description": "only what was visible"}`. A visual claim then cites `{"stream": "visual", "observation": "unique-id"}`. Never create an observation for an unreadable or unopened frame. Valid post-runtime observations upgrade visual coverage from `none` to `partial`; they never downgrade `partial` or `complete` coverage.

Set `raw_transcript_requested` to `true` only when the user explicitly asks for the full Raw transcript. A normal answer that reproduces every transcript segment is invalid.

## Read the result

- For state: `answered`, return `markdown` to the user. It contains compiler-derived citations, Answerability, evidence coverage, gaps, warnings, and safe mitigations.
- For state: `withheld`, return `markdown`. Cancellation, failure, and stop outcomes suppress every proposed evidence claim and report only the applicable state and retention/disposal facts.
- For state: `invalid`, do not expose rejected claim text. Read `problem.code` and `problem.message`, correct the answer request from the inspected evidence, and compile again. If the evidence cannot support a valid request, return the compiler's invalid Markdown without improvising a conclusion.

The compiler proves structural grounding: every citation resolves to returned evidence and every visual reference resolves to a selected frame plus a Visual observation. The agent remains responsible for declaring every question-relevant stream and for making each claim a faithful description or paraphrase of inspected evidence. The compiler does not infer semantic relevance from keywords.
