---
name: make-book-video
description: Turn a book title, book page, approved script, or notes into a complete Chinese vertical book recommendation or sales video with source-checked claims, a real cover, optional licensed stock footage, built-in image generation, one-pass Doubao Seed TTS 2.0 narration, provider word timestamps, bilingual captions, local rendering, and media QA. Use when the user asks to create, regenerate, batch-produce, or diagnose 图书带货视频、读书种草视频、书单推荐视频、书评短视频, especially when the deliverable must be a playable MP4 rather than only a script or storyboard.
---

# Make Book Video

Deliver the playable MP4. Treat a script, storyboard, timeline, or preview as intermediate work.

## Defaults

- Produce Chinese 9:16 video at 1080x1920, 30 fps, H.264 plus AAC 48 kHz.
- Use the real narration duration and provider timestamps as timeline truth.
- Use local FFmpeg or an available video framework; do not require ChatCut.
- Prefer Codex built-in image generation for illustrations. Do not require a paid image API.
- Treat Pexels as an optional, replaceable source for licensed stock footage.
- Never put API keys in prompts, source files, reports, shell history, or Git.
- Ask for a content gate before paid batch generation unless the user already approved the script and generation.

## Workflow

### 1. Create the case record

Copy `assets/case-template.json` into the task directory as `case.json`. Record the exact book, audience, angle, claims, narration segments, caption cards, visuals, and optional timeline holds.

Read [references/research.md](references/research.md) before researching a new book. Separate:

- bibliographic facts;
- attributed book or author ideas;
- public reader reactions;
- creator interpretation;
- unsupported claims to omit.

Use a real cover from an attributable source. Never regenerate the cover title with an image model.

### 2. Approve the narrative and storyboard

Make the opening legible at normal phone size. For an anticipation-style fast carousel, use five different real covers, keep each cover compact enough that the title is captured at a glance, and start around 9 frames per cover at 30 fps. Use fewer covers only when readability testing proves the titles need more time.

For every narration segment, define its visual purpose and asset source. Keep review statements attributed and avoid invented quotations, rankings, screenshots, guarantees, and scientific certainty.

### 3. Generate one timestamped narration

Read [references/doubao-v3-timestamps.md](references/doubao-v3-timestamps.md). Generate the approved narration with:

```bash
python3 <SKILL_DIR>/scripts/doubao_tts.py \
  --text-file <task>/narration.txt \
  --output <task>/audio/narration.raw.wav \
  --resource-id seed-tts-2.0 \
  --speaker "$DOUBAO_TTS_SPEAKER" \
  --speech-rate 20
```

The script always sends `enable_subtitle: true`. Require non-empty, monotonic provider word timestamps. Do not substitute silence detection, character weighting, or an ASR pass when the provider timestamps are expected but absent.

Keep `--max-request-bytes` at its default `0` for an approved production narration. Require `requestMode: single` and `providerRequestCount: 1` in the TTS report; do not silently assemble several independently generated performances and call them one-pass narration.

Audition speech-rate variants on a short excerpt before regenerating a long approved narration. For `zh_male_cixingjieshuonan_uranus_bigtts`, use `+20` as the current production starting point, then judge the actual take. Prefer provider-side `speech_rate` over FFmpeg `atempo` so the TTS model controls prosody.

### 4. Build the timestamp timeline

Run:

```bash
python3 <SKILL_DIR>/scripts/build_timestamp_timeline.py \
  --audio <task>/audio/narration.raw.wav \
  --tts-report <task>/audio/narration.raw.wav.json \
  --storyboard <task>/storyboard.json \
  --captions <task>/subtitle-pairs.json \
  --output-dir <task>/timing \
  --fps 30
```

Add `--hold-after <segment-id> --hold-frames <frames>` when a silent visual beat such as a cover carousel must be inserted. The script must locate a real quiet interval in the PCM waveform, insert at its verified center, record the search interval, threshold, guard-window RMS, and chosen sample, then shift all later provider timestamps without stretching speech. Never insert at the midpoint between two provider timestamps: a low-confidence word start can lag the actual phoneme and make that midpoint cut through speech.

Require exact normalized text coverage between narration, caption cards, and returned provider words. A mismatch is a content error; stop and repair the text instead of guessing.

Treat the raw WAV, its TTS report, `X-Tt-Logid`, final silence-adjusted WAV, caption timeline, scene timeline, and ASS file as one frozen evidence chain. Record their hashes in `build_report.json`; never reuse timestamps from a different TTS take, even when the text and speaker are unchanged.

### 5. Source and generate visuals

Read [references/visuals.md](references/visuals.md). Use:

- book-source research for the main real cover;
- web search with source records for other real covers;
- Pexels only when stock footage materially helps the opening;
- built-in image generation for illustrative body scenes;
- deterministic typography and shapes when generation adds no value.

If Pexels is used, run `scripts/search_pexels_videos.py`, inspect candidates visually, save the page and creator attribution, and download only the selected file.

### 6. Render from frozen assets

Keep all render media local. Build scene boundaries from `timing/scene-timeline.json` and captions from `timing/caption-timeline.json`. Do not recalculate timing from script length.

Read [references/render-and-qa.md](references/render-and-qa.md). Save:

- `renders/video.mp4`;
- `renders/audio_mix.m4a`;
- `build_report.json` with total duration and scene boundaries;
- `renders/qa/human-review.json` after visual review.

Also save SHA-256 values for `timing/alignment-report.json`, `timing/caption-timeline.json`, `timing/scene-timeline.json`, `timing/subtitles.ass`, and the final timestamped narration in `build_report.json`. Build every visual segment from `scene-timeline.json`; a hard-coded prior duration is stale by definition.

### 7. Complete media QA

Run:

```bash
python3 <SKILL_DIR>/scripts/qa_video.py <task>
```

Require correct streams, full decode, duration agreement, approved-audio packet match, contact sheets, boundary frames, caption visibility, readable covers, acoustic-safe hold evidence, and recorded human review. Audition the opening transition in the rendered mix to confirm that no syllable is duplicated, clipped, or split around the inserted hold. Automated PASS is structural evidence, not proof that the visuals or speech sound right.

The QA command must fail when narration is not one provider request, text coverage is below 100%, any caption lacks provider word keys, any narrated scene is marked `derived`, an inserted hold lacks verified PCM-silence evidence, the narration or timing-artifact hashes differ, or the ASS event count differs from the caption ledger.

### 8. Publish only when requested

Uploading or overwriting a hosted version requires explicit user direction. Prefer a stable site with one video path per asset instead of consuming one subdomain per video. Preserve attribution and report the exact published URL.

## Completion report

Report the absolute final MP4 path, duration, format, timestamp source, QA result, publication URL when applicable, and any remaining human publishing judgment.

## Resources

- `scripts/check_environment.py`: secret-safe preflight.
- `scripts/doubao_tts.py`: one-pass Seed TTS 2.0 synthesis with word timestamps.
- `scripts/build_timestamp_timeline.py`: strict text-to-provider-time alignment and acoustically verified silent holds.
- `scripts/search_pexels_videos.py`: optional portrait stock-footage search.
- `scripts/qa_video.py`: deterministic media QA and evidence generation.
- `references/`: detailed research, timing, visual, and render contracts.
- `assets/case-template.json`: reusable task schema.
