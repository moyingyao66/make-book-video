---
name: make-book-video
description: "Turn a book title, book page, approved script, or notes into a source-checked Chinese vertical recommendation or sales video. For title-first 图书带货视频、读书种草视频、书单推荐视频 or 书评短视频, use WeRead-first research and the Cognition-Awakening-style audience narrative contract before one-pass Doubao timestamps, synchronized captions, local rendering, human review, and final MP4 QA. Use for creating, regenerating, batch-producing, or diagnosing book videos when the deliverable must be a playable MP4 rather than only a script or storyboard."
---

# Make Book Video

Deliver a playable MP4. Treat research, script, storyboard, assets, timelines, and previews as intermediate evidence.

## Non-negotiable defaults

- Produce 9:16 video at 1080x1920, 30 fps, H.264 plus AAC 48 kHz unless the user approves another delivery contract.
- Use one approved `case.json` as content truth and one `render-manifest.json` as render truth.
- For a title-first Chinese video, use `weread-skills` as the primary research route and `cognition-awakening-v1` as the default narrative profile.
- Treat book-source results as evidence, never as ready-made narration. Select one audience situation and one main thesis.
- Use one Doubao provider request for the complete narration. Use provider timestamps and actual audio duration as timing truth.
- Use the real cover from an attributable source. Never let an image model redraw cover typography.
- Prefer built-in image generation. Treat Pexels as optional and replaceable.
- Keep secrets out of prompts, files, reports, shell history, and Git.
- Require content approval before paid full-length TTS or batch generation.
- Require human review of the actual MP4 before reporting completion.

## 1. Initialize a portable project

Use a working Python 3.8 or newer, preferably from a project virtual environment. If the default `python3` command is broken or too old, locate a supported interpreter before running any Skill script. Install the pinned runtime dependencies from `requirements.txt`.

Run:

```bash
python3 <SKILL_DIR>/scripts/init_case.py <project> --title "<book>" --author "<author>"
```

This creates `case.json`, `render-manifest.json`, the human-review ledger, the research record, and stable project directories without overwriting existing files.

Read [references/project-schema.md](references/project-schema.md). Keep every asset path project-relative. Do not put book-specific paths, scene IDs, frame counts, or application paths in Skill scripts.

## 2. Research and approve content

Read [references/research.md](references/research.md) and [references/copywriting.md](references/copywriting.md). Record exact book identity, attributable cover source, review clusters, selected angle, claim categories, omissions, and downloaded-cover checksum.

Route the input explicitly:

- **Book title or book page:** use installed `weread-skills` first for identity, directory, popular highlights, and public reviews. Record its version, `bookId`, captured endpoints, and whether private notes were used. Use another attributable source only when WeRead is unavailable or lacks the required field, and record the fallback instead of silently substituting it.
- **Notes needing a script:** verify book claims, then write with the default narrative profile.
- **User-approved script:** preserve wording and order. Use research only to flag conflicts unless the user asks for rewriting. Set `narrativeProfile.id` to `preserve-approved-script` when the fixed profile should not be imposed.

When `WEREAD_API_KEY` is absent from the current process on macOS but was saved in Keychain, run WeRead commands through `scripts/with_weread_env.zsh`. The wrapper injects the credential only into that child process and must not print or persist it. For example, verify availability with `scripts/with_weread_env.zsh --check`; do not copy the key into a project file, shell profile, prompt, report, or command argument.

For new writing, follow `cognition-awakening-v1`: exact fixed opening, silent carousel, complete author/title reveal, concrete viewer situation, alternative explanation, one or two supporting examples, practical boundary, and a close that returns to the viewer. Default to 350–420 non-whitespace narration characters and an 80–95 second planning range unless the user specifies otherwise.

Write every narrated segment, source-claim mapping, and Chinese caption card in `case.json`. Require the concatenated caption text of each segment to exactly cover that segment's narration after punctuation normalization. Add English caption text only after reviewing the translation.

For an anticipation carousel, default to five different real covers at about nine frames each at 30 fps. Keep the whole title area visible at phone size. Use fewer only after readability review.

Run the draft validator before presenting the approval package. It must reject a conceptual hook before the fixed opening, a missing carousel boundary, a reveal without the title, a draft outside its declared length range, missing WeRead capture for a title-first route, or an incomplete copy-review ledger:

```bash
python3 <SKILL_DIR>/scripts/validate_case.py <project> --stage draft
```

Show the complete narration, source boundary, storyboard summary, character count, and planned duration. Set `case.status` to `approved` only after the user approves the narrative and storyboard. Validate again before any paid call:

```bash
python3 <SKILL_DIR>/scripts/validate_case.py <project> --stage synthesis
```

## 3. Source visuals

Read [references/visuals.md](references/visuals.md). Use real covers for book identity, built-in image generation for semantic body scenes, deterministic design for text and diagrams, and optional Pexels footage only when it improves the opening.

If Pexels is used, run `scripts/search_pexels_videos.py`, inspect actual frames, then save the selected page, creator, file URL, dimensions, and attribution. Do not stop production merely because Pexels is unavailable.

Map every narrated segment and intentional hold to an asset in `render-manifest.json`. Use the generic `image`, `video`, `carousel`, or `solid` scene types. Use image overlays to place a true book cover over a designed background.

## 4. Generate, align, and render

Read [references/doubao-v3-timestamps.md](references/doubao-v3-timestamps.md) and [references/render-and-qa.md](references/render-and-qa.md).

Set the approved speaker in `case.json`. For `zh_male_cixingjieshuonan_uranus_bigtts`, start at provider `speechRate: 20`, audition a short excerpt, and record any approved change. Prefer provider-side rate control over FFmpeg `atempo`.

Run the generic pipeline:

```bash
python3 <SKILL_DIR>/scripts/check_environment.py --project <project>
python3 <SKILL_DIR>/scripts/build_video.py <project>
```

The pipeline must:

1. Revalidate content approval.
2. Generate the complete narration in one Doubao Seed TTS 2.0 V3 request with `enable_subtitle: true`.
3. Require non-empty, monotonic `sentence.words`, `X-Tt-Logid`, `requestMode: single`, and `providerRequestCount: 1`.
4. Require 100% normalized text coverage across narration, segments, caption cards, and provider words.
5. Insert an intentional visual hold only at verified 16-bit PCM silence, then shift later provider timestamps without stretching speech.
6. Freeze the adjusted WAV, alignment report, scene timeline, caption timeline, ASS, case, and render manifest with hashes.
7. Render every timeline scene from `render-manifest.json`; never recalculate scene timing from text length.
8. Save `renders/video.mp4`, `renders/audio_mix.m4a`, `build_report.json`, and a human-review ledger tied to the video SHA-256.

Use `--force-tts` only when deliberately paying to regenerate the approved take. Use `--render-only` after changing only local visual or audio-mix assets.

## 5. Review and finalize QA

Review `renders/video.mp4`, the whole-film contact sheet, and every scene boundary. Complete every check in `renders/qa/human-review.json`; do not set `passed: true` before verifying:

- whole-film and boundary frames;
- subtitle synchronization and commerce-safe placement;
- cover readability and carousel pace;
- opening speech continuity across any silent hold;
- narration pace and audio balance;
- generated-image semantics and spatial logic;
- claim and CTA boundaries.

Then run:

```bash
python3 <SKILL_DIR>/scripts/build_video.py <project> --qa-only
```

Require correct streams, full decode, exact duration agreement, approved-audio packet equality, complete provider timing provenance, current artifact hashes, acoustic-safe holds, all human checks, and a human-review video hash matching the MP4. Automated PASS proves structure, not subjective quality.

## 6. Publish only when requested

Upload or overwrite a hosted version only after explicit user direction. Prefer one stable site with one path per video instead of a subdomain per video. Preserve attribution and report the exact URL.

## Completion report

Report the absolute MP4 path, duration, format, narration provider and speech rate, timestamp source, QA result, publication URL when applicable, and any remaining publisher judgment.

## Bundled resources

- `scripts/init_case.py`: create a non-overwriting portable project.
- `scripts/validate_case.py`: fail closed on content, caption, manifest, or asset errors.
- `scripts/build_video.py`: generic approved-case orchestrator.
- `scripts/doubao_tts.py`: one-pass Seed TTS 2.0 synthesis with provider timestamps.
- `scripts/build_timestamp_timeline.py`: strict timing alignment and acoustic-safe holds.
- `scripts/render_video.py`: manifest-driven FFmpeg renderer without book-specific code.
- `scripts/search_pexels_videos.py`: optional portrait stock search.
- `scripts/qa_video.py`: deterministic media and evidence QA.
- `assets/`: portable case, render, and human-review templates.
- `references/copywriting.md`: WeRead-to-narration separation, the default narrative profile, length policy, anti-patterns, and editorial review ledger.
- `references/`: research, schema, provider timing, visual, and QA contracts.
