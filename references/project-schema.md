# Portable project contract

## Contents

- Source-of-truth files
- Approval and text rules
- Provider timing evidence chain
- Startup visual-source policy
- Post-copy visual-style profile
- Short editable body shots
- Timeline holds
- Render manifest
- Audio manifest
- Stable directories

## Source-of-truth files

Keep exactly two authoring control files:

- `case.json`: book identity, startup visual-source policy, approval state, canvas, voice, claims, narrated segments, caption cards, and intentional holds.
- `render-manifest.json`: project-relative visual and audio assets plus encoding choices.

Keep `editable-delivery.json` as a generated delivery ledger. It is not an alternative timeline authoring source: it records the current editor route, project/timeline identity, source hashes, normalized item mappings, and live readback proof.

Generated files such as `narration.txt`, timing JSON, ASS, `build_report.json`, and rendered media must be rebuilt from those controls. Do not edit generated timing by hand.

## Approval and text rules

Set `case.status` to `approved`, `approved-for-generation`, or `ready` only after content approval. Each segment needs a unique ID, narration, and one or more uniquely identified caption cards. Concatenated Chinese caption text must exactly cover the segment narration after Unicode, case, whitespace, and punctuation normalization.

New title-first projects use:

- `inputMode: book-title`;
- `researchRoute.primary: weread-skills`, with Skill version, private-note status, and either `status: captured` plus `bookId`/captured inputs, or `status: unavailable-with-fallback` plus attributable fallback objects containing `sourceUrl` and `reason`;
- `narrativeProfile.id: cognition-awakening-v1`, with declared narration-character and planning-duration ranges;
- `sourceClaimIds` on substantial explanation, example, and practical-boundary segments;
- a completed `copyReview` ledger before user approval;
- an approval receipt produced by `record_approval.py`, binding the reviewed case/manifest semantics, current voice config, listened preview WAV/report, and deterministic approval package before paid full-length generation.

Use `narrativeProfile.id: preserve-approved-script` when the user supplies approved wording that must not be reformatted. Use `custom` only when the user approves a different narrative structure and record that decision in the project.

Both custom profiles still require the same `researchRoute`, source-checked `claims`, per-segment `sourceClaimIds`, and completed `copyReview` evidence as the default profile. A custom structure changes copy order; it never bypasses research or editorial review.

Use `voice.resourceId: seed-tts-2.0`, an approved speaker, an explicit `speechRate`, `enableSubtitle: true`, and `requireSingleProviderRequest: true`.

## Provider timing evidence chain

Generate the full narration once with one actual Doubao HTTP attempt. Run the timeline builder with `--case case.json`; it reopens the raw WAV and provider report and rejects any mismatch in `audioSha256`, provider identity, HTTP-200 request/attempt evidence, request word counts, resource ID, speaker, speech rate, subtitle flag, request/attempt counts, provider log IDs, or canonical sequential `timestamps.words` keys, text, and ranges. Final QA reruns this builder in a temporary project directory and compares the rebuilt PCM, scene/caption/word timelines, alignment semantics, and ASS against the delivery candidates.

The generated `timing/alignment-report.json`, `build_report.json`, final QA report, and `renders/qa/delivery-ready.json` bind these three source artifacts by project-relative path and SHA-256:

- `rawNarrationAudio` / `rawNarrationAudioSha256`;
- `ttsReport` / `ttsReportSha256`;
- `wordTimeline` / `wordTimelineSha256`.

Final QA reopens all three artifacts, reruns the report/WAV/case reconciliation, and compares every word-timeline character to the provider words. Copied fields in an alignment or build report are not sufficient delivery evidence.

## Startup visual-source policy

Collect both media choices together in a direct selection UI before research or initialization. Do not accept typed substitutes and do not infer omitted answers. New projects use:

```json
{
  "visualSourcePolicy": {
    "selectionStatus": "confirmed",
    "selectionMethod": "host-structured-choice",
    "selectedAtProjectStart": true,
    "openingSource": "pexels-video",
    "bodySource": "gpt-image",
    "silentFallbackAllowed": false
  }
}
```

Allowed opening values are `pexels-video` and `gpt-image`; allowed body values are `gpt-image` and `pexels-video`. The recommended defaults are Pexels video for the opening and GPT images for the narrated body. These are UI recommendations, not permission to initialize without a confirmed selection.

The opening choice governs the `fixed-opening` segment. The body choice governs `audience-problem`, `alternative-explanation`, `concrete-example`, `practical-boundary`, and `audience-close`. It does not govern the real-cover carousel or book-reveal scene. The segment `asset`, its `render-manifest.sceneAssets` entry, `type`, and `sourceProvider` must agree with the policy.

For each Pexels scene, require a project-relative video and `sourceRecord`. The source record must identify the scene, query, Pexels page, creator, selected file URL and dimensions, attribution, downloaded file path and checksum, and a passed three-point/boundary frame review. A selected Pexels route is a build requirement; never replace it silently when unavailable.

## Post-copy visual-style profile

Version 4 projects require `case.visualStyleProfile` before approval. It records:

- `status: confirmed` and `selectionMethod: post-copy-three-option-preview`;
- the book category and representative `previewSceneId`;
- exactly three candidates with unique IDs, rationale, and project-relative preview paths;
- a `selectedStyleId` that matches one candidate;
- `facePolicy: avoid-recognizable-faces` by default;
- `principles.narrationFirst: true`, `simpleComposition: true`, `generatedTextAllowed: false`, and `maxPrimarySubjects` of one or two.

Use `approved-visible-face-exception` only with a non-empty reason and approver. The complete profile belongs to the approval-relevant case projection, so changing it invalidates a previous approval receipt.

## Short editable body shots

The five body roles remain the conceptual structure, but version 4 allows and expects repeated role values across distinct segment IDs. Use 12–18 body segments total, normally two to four consecutive segments per role, and keep each at no more than 36 non-whitespace Chinese characters. The compressed role order must remain `audience-problem -> alternative-explanation -> concrete-example -> practical-boundary -> audience-close`.

Each segment has its own narration, `visualIntent`, caption cards, claim mapping, and source path. The existing render and editor pipelines map segment IDs one-to-one to scene items, so this structure creates independently replaceable timeline media without a flattened multi-panel container.

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

The renderer stages the MP4 and audio mix under the project before replacing previous outputs. `build_report.json` version 4 records both `videoSha256` and `audioMixSha256` plus `renderInputInventory`. The inventory is canonical and role-addressed: every entry contains a project-relative `path` and current `sha256` for case/manifest controls, timing JSON, ASS, provider artifacts, scene primary/carousel/overlay files, BGM/SFX, source records, and version-3+ approval evidence. The renderer rebuilds it before and after FFmpeg work. Final QA and delivery independently reconstruct it; replacing an input requires a rerender.

Reject absolute paths, `..`, symlink files, symlink directory components, and any path whose resolved target escapes the project. Apply this rule to fixed names such as `case.json`, `render-manifest.json`, `build_report.json`, `editor-plan.json`, `editable-delivery.json`, and the delivery marker as well as manifest-declared assets.

The renderer writes an AAC 48 kHz approved mix, copies it into the MP4, and records current hashes. Any rerender invalidates a human review tied to a previous video hash.

Set `captions.mode`, `requireEnglish`, `font`, `fontSize`, `englishFontSize`, `positionY`, and `safeBottomPx` in the render manifest. The default 1080×1920 contract is bilingual, 72 px Chinese, 40 px English, y=1500, and a 360 px bottom safe area. Chinese-only output must explicitly use `mode: zh-only`. Use a locally installed Chinese font and verify the burned glyphs in the contact sheets; do not assume a macOS font exists on Linux or Windows.
Chinese and English lines must be wrapped separately before ASS output. A positioned ASS event must not depend on renderer-specific automatic wrapping.

## Stable directories

```text
project/
  case.json
  render-manifest.json
  editable-delivery.json
  editor-plan.json
  research.md
  narration.txt
  audio/
  assets/covers/
  assets/pexels/
  assets/stock/
  assets/music/
  assets/sfx/
  visuals/
  timing/
  renders/qa/
  output/
  build_report.json
```
