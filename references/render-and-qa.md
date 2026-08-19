# Render and delivery-QA contract

Use this reference when rendering the local MP4 or closing the final delivery gate. The goal is to catch broken or stale deliverables, not to turn ordinary book-video production into a publication system.

## Contents

- Local render
- Automated delivery checks
- Human review
- Delivery marker

## Local render

Render `renders/video.mp4` and `renders/audio_mix.m4a` locally with FFmpeg from the approved `case.json`, `render-manifest.json`, provider-derived scene/caption timelines, and original media. Never estimate final scene timing from character count and never use a ChatCut cloud export as the default MP4.

Keep narration, optional BGM, and SFX distinct in the manifest and ChatCut project. Burn the reviewed captions into the local MP4, preserve the approved audio mix, and invalidate the previous delivery marker before every rerender.

## Automated delivery checks

Require these checks before completion:

- `renders/video.mp4` exists, has H.264 video and AAC 48 kHz audio, and fully decodes;
- width, height, frame rate, and duration match the approved project contract;
- the final MP4, approved audio mix, case, manifest, narration, provider timing, scene timeline, caption timeline, and editor plan are current rather than stale;
- provider words cover the complete narration and caption text;
- every declared source asset exists and remains inside the project;
- `editable-delivery.json` proves a reopened, non-empty ChatCut project built from independent original visuals, captions, narration, BGM, and SFX rather than a flattened MP4;
- the reviewed video SHA-256 matches the actual MP4.

The bundled scripts may retain extra integrity checks when they are deterministic and cheap to run. Do not expose those internal checks as additional user confirmation gates.

## Human review

The user reviews the actual MP4, a whole-film contact sheet, boundary frames, and the reopened ChatCut project. Record `renders/qa/human-review.json` only after checking:

- no unintended black, blank, frozen, distorted, or clipped frames;
- real covers remain readable and the fast-flash pace works on a phone;
- captions are readable, synchronized, and outside platform UI risk zones;
- narration pace and narration/BGM/SFX balance sound intentional;
- every generated image or sourced clip matches its own narration segment;
- opening, middle, and ending ChatCut compositions match the local MP4;
- the ChatCut timeline keeps original visuals, captions, and audio independently editable;
- claims and CTA do not overpromise.

Automated PASS does not replace this judgment. The model must not mark the human ledger as passed on the user's behalf.

## Delivery marker

A successful non-preflight QA run writes `renders/qa/delivery-ready.json` with:

- `version: 2`;
- `contract: make-book-video-delivery-v1`;
- the exact MP4 and approved audio-mix hashes;
- the ChatCut project and timeline IDs;
- hashes for the current QA report, human review, editable-delivery ledger, and editor plan.

Run `scripts/verify_delivery.py <project>` before reporting completion. It fails when a bound artifact changes after review. A later upload, hosting request, or social-platform publication is outside this Skill.
