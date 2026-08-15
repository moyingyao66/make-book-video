# Portable project contract

## Source-of-truth files

Keep exactly two editable control files:

- `case.json`: book identity, approval state, canvas, voice, claims, narrated segments, caption cards, and intentional holds.
- `render-manifest.json`: project-relative visual and audio assets plus encoding choices.

Generated files such as `narration.txt`, timing JSON, ASS, `build_report.json`, and rendered media must be rebuilt from those controls. Do not edit generated timing by hand.

## Approval and text rules

Set `case.status` to `approved`, `approved-for-generation`, or `ready` only after content approval. Each segment needs a unique ID, narration, and one or more uniquely identified caption cards. Concatenated Chinese caption text must exactly cover the segment narration after Unicode, case, whitespace, and punctuation normalization.

New title-first projects use:

- `inputMode: book-title`;
- `researchRoute.primary: weread-skills`, with Skill version, `bookId`, captured inputs, private-note status, and explicit fallbacks;
- `narrativeProfile.id: cognition-awakening-v1`, with declared narration-character and planning-duration ranges;
- `sourceClaimIds` on substantial explanation, example, and practical-boundary segments;
- a completed `copyReview` ledger before user approval;
- explicit `approval` booleans before paid generation.

Use `narrativeProfile.id: preserve-approved-script` when the user supplies approved wording that must not be reformatted. Use `custom` only when the user approves a different narrative structure and record that decision in the project.

Use `voice.resourceId: seed-tts-2.0`, an approved speaker, an explicit `speechRate`, `enableSubtitle: true`, and `requireSingleProviderRequest: true`.

## Timeline holds

Each `timelineHolds` item needs a unique ID, an existing `afterSegmentId`, and positive `durationFrames`. A hold becomes a separate render scene. It is valid only when the timeline builder finds and records a real PCM-silence insertion point.

## Render manifest

Require `render-manifest.canvas` to exactly match `case.canvas`. Keep all paths relative to the project and inside it. Map every segment and hold ID under `sceneAssets`.

Supported scene types:

- `image`: use `path`, `fit` (`cover`, `contain`, or `stretch`), optional `motion: slow-zoom`, and optional `overlays`.
- `video`: use `path`, optional `startSeconds`, `fit`, and `loop`.
- `carousel`: use two or more `items`; optionally set `itemFrames` or exact `framesPerItem`, `maxWidth`, `maxHeight`, `framePadding`, and `backgroundColor`.
- `solid`: use a color accepted by FFmpeg.

An image overlay accepts a project-relative `path`, optional `width` or `height`, `x`, `y`, and `fadeInSeconds`. Use this for a real cover over a separate generated background.

The carousel frame allocation must exactly equal the hold scene duration. For the default five-cover anticipation beat, use a 45-frame hold plus `itemFrames: 9`.

## Audio manifest

Set `audio.narration` to the timestamp-adjusted WAV. BGM is optional; when present, use a project-relative `path`, low `volume`, and fade durations. Each SFX item needs a path, volume, and either `startFrame` or `startSeconds`.

The renderer writes an AAC 48 kHz approved mix, copies it into the MP4, and records current hashes. Any rerender invalidates a human review tied to a previous video hash.

Set `captions.font`, `fontSize`, `englishFontSize`, and `positionY` in the render manifest. Use a locally installed Chinese font and verify the burned glyphs in the contact sheets; do not assume a macOS font exists on Linux or Windows.

## Stable directories

```text
project/
  case.json
  render-manifest.json
  research.md
  narration.txt
  audio/
  assets/covers/
  assets/stock/
  assets/music/
  assets/sfx/
  visuals/
  timing/
  renders/qa/
  output/
  build_report.json
```
