---
name: make-book-video
description: "Turn a book title, book page, approved script, or notes into a source-checked Chinese vertical recommendation or sales video with both a verified editable ChatCut/OpenChatCut timeline and a playable MP4. For title-first 图书带货视频、读书种草视频、书单推荐视频 or 书评短视频, use WeRead-first research and the Cognition-Awakening-style audience narrative contract before one-pass Doubao timestamps, synchronized bilingual captions, editable assembly, local rendering, human review, and final media QA. Use for creating, regenerating, batch-producing, or diagnosing book videos when the deliverable must remain可剪辑 and publishable rather than only a script, storyboard, project shell, or flattened draft."
---

# Make Book Video

Deliver a verified editable editor project and a playable MP4 from the same source assets and provider-timestamp timeline. Treat research, script, storyboard, project shells, and previews as intermediate evidence.

## Non-negotiable defaults

- Produce 9:16 video at 1080x1920, 30 fps, H.264 plus AAC 48 kHz unless the user approves another delivery contract.
- Use one approved `case.json` as content truth and one `render-manifest.json` as render truth.
- Keep every cover, scene, caption, narration, BGM, and SFX element independently editable in the final editor timeline. Never import the flattened MP4 as the primary timeline content.
- For a title-first Chinese video, use `weread-skills` as the primary research route and `cognition-awakening-v1` as the default narrative profile.
- Treat book-source results as evidence, never as ready-made narration. Select one audience situation and one main thesis.
- Use one Doubao provider request for the complete narration. Use provider timestamps and actual audio duration as timing truth.
- Use the real cover from an attributable source. Never let an image model redraw cover typography.
- Before research or initialization, collect both visual-source choices in one structured selection UI. Recommend Pexels video for the opening and GPT-generated images for the body, but never apply either choice silently.
- Persist the confirmed visual-source choices in `case.json` and follow them throughout the run. Never replace a selected source without a new explicit user decision.
- Keep secrets out of prompts, files, reports, shell history, and Git.
- Require content approval before paid full-length TTS or batch generation.
- Default to reviewed bilingual captions. Chinese-only output must be declared explicitly in `render-manifest.json`.
- Require a reopened, non-empty editor project, human review of both the editor composition and actual MP4, and a current `renders/qa/release-ready.json` before reporting completion or publishing.

## 0. Collect all configuration choices first

Before running commands, researching the book, or creating project files, show one structured selection form containing both questions below. Use the host's direct choice UI, preferably one `request_user_input` call with two questions. Do not ask either question as prose and do not require the user to type an answer.

Use these exact choices and enum mappings:

1. `opening_media`, header `开场素材`
   - `Pexels 动态视频 (Recommended)` -> `pexels-video`: search and review a real portrait-motion clip for the narrated opening.
   - `GPT 静态图片` -> `gpt-image`: generate a semantic still image; a subtle deterministic push-in is allowed during editing.
2. `body_media`, header `正文素材`
   - `GPT 生图 (Recommended)` -> `gpt-image`: generate a distinct semantic image for each narrated body segment.
   - `Pexels 动态视频` -> `pexels-video`: search, frame-review, attribute, and use a distinct relevant live-action clip for each narrated body segment.

The structured call should be equivalent to:

```yaml
questions:
  - header: 开场素材
    id: opening_media
    question: 开头前几秒使用哪种素材？
    options:
      - label: Pexels 动态视频 (Recommended)
        description: 使用经检索和逐帧审核的真实竖屏动态视频。
      - label: GPT 静态图片
        description: 使用语义匹配的生成静态图并允许轻微推拉。
  - header: 正文素材
    id: body_media
    question: 书籍内容介绍部分使用哪种素材？
    options:
      - label: GPT 生图 (Recommended)
        description: 为每段旁白生成独立且语义匹配的正文图。
      - label: Pexels 动态视频
        description: 为每段旁白检索并审核独立的真实动态视频。
```

The form should ask:

- `开头前几秒使用哪种素材？`
- `书籍内容介绍部分使用哪种素材？`

Put the recommended option first in each selection. Treat “default” as the clearly marked recommended choice shown to the user, not permission to skip the selection. If the current host cannot display a structured selection UI, state that the required selection control is unavailable and pause before project initialization; never fall back to free-form/manual input.

Record both answers immediately and do not ask about visual sources again later. Content/storyboard approval and voice listening review remain later evidence gates, not startup configuration questions. Use established Skill defaults for settings that do not require a user choice.

## 1. Initialize a portable project

Use a working Python 3.8 or newer, preferably from a project virtual environment. If the default `python3` command is broken or too old, locate a supported interpreter before running any Skill script. Install the pinned runtime dependencies from `requirements.txt`.

Run:

```bash
python3 <SKILL_DIR>/scripts/init_case.py <project> \
  --title "<book>" --author "<author>" \
  --opening-source <pexels-video|gpt-image> \
  --body-source <gpt-image|pexels-video>
```

This creates `case.json`, `render-manifest.json`, `editable-delivery.json`, the human-review ledger, the research record, and stable project directories without overwriting existing files.

Both source flags are required and must come from the startup selection form. Initialization writes them to `visualSourcePolicy`, materializes matching scene assets and Pexels evidence ledgers, and refuses to guess when either answer is missing.

Read [references/project-schema.md](references/project-schema.md). Keep every asset path project-relative. Do not put book-specific paths, scene IDs, frame counts, or application paths in Skill scripts.

## 2. Research and approve content

Read [references/research.md](references/research.md) and [references/copywriting.md](references/copywriting.md). Record exact book identity, attributable cover source, review clusters, selected angle, claim categories, omissions, and downloaded-cover checksum.

Route the input explicitly:

- **Book title or book page:** use installed `weread-skills` first for identity, directory, popular highlights, and public reviews. Record its version, `bookId`, captured endpoints, and whether private notes were used. Use another attributable source only when WeRead is unavailable or lacks the required field, and record the fallback instead of silently substituting it.
- **Notes needing a script:** verify book claims, then write with the default narrative profile.
- **User-approved script:** preserve wording and order. Use research only to flag conflicts unless the user asks for rewriting. Set `narrativeProfile.id` to `preserve-approved-script` when the fixed profile should not be imposed.

When `WEREAD_API_KEY` is absent from the current process on macOS but was saved in Keychain, run WeRead commands through `scripts/with_weread_env.zsh`. The wrapper injects the credential only into that child process and must not print or persist it. For example, verify availability with `scripts/with_weread_env.zsh --check`; do not copy the key into a project file, shell profile, prompt, report, or command argument.

For new writing, follow `cognition-awakening-v1`: exact fixed opening, silent carousel, complete author/title reveal, concrete viewer situation, alternative explanation, one or two supporting examples, practical boundary, and a close that returns to the viewer. Default to 350–420 non-whitespace narration characters and an 80–95 second planning range unless the user specifies otherwise.

Write every narrated segment, source-claim mapping, and Chinese caption card in `case.json`. Require the concatenated caption text of each segment to exactly cover that segment's narration after punctuation normalization. The default caption mode is `bilingual`: every card needs a reviewed `enText`. Use `mode: zh-only` only when Chinese-only output was intentionally selected; never label an empty-English timeline as bilingual.

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

Read [references/visuals.md](references/visuals.md). Use real covers for book identity and follow the startup `visualSourcePolicy` for the opening and narrated body scenes. Deterministic design remains appropriate for text and diagrams.

For every scene assigned to Pexels, run `scripts/search_pexels_videos.py` with a scene-specific query, inspect actual frames, then complete that scene's source ledger with the selected page, creator, file URL, dimensions, attribution, downloaded-file hash, and review decision. Pexels is optional only when the user selected the GPT route. If the user selected Pexels and it is unavailable or no candidate is semantically acceptable, report the blocker; do not silently substitute a still image or generated asset.

For every scene assigned to GPT image generation, use the built-in `imagegen` Skill/tool and save a distinct semantic still at the path already materialized in the manifest. Do not use Pexels as a fallback without an explicit source-policy change.

Map every narrated segment and intentional hold to an asset in `render-manifest.json`. Use the generic `image`, `video`, `carousel`, or `solid` scene types. Use image overlays to place a true book cover over a designed background.

For every body scene, compare the actual image or sampled video frames with that segment's narration and `visualIntent`. Reject attractive but generic reading media, unexplained repeated actions, or an asset whose main action belongs to another segment. Record per-scene semantic review before the final render.

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

Default 1080×1920 subtitle delivery uses Chinese 72 px, English 40 px, a baseline around y=1500, and at least 360 px of bottom safe area. Treat these as minimum readability defaults, then confirm them on phone-size frames.
Wrap Chinese and English independently before ASS rendering; do not rely on libass to wrap long positioned captions. Inspect at least one of the longest Chinese cards and longest English cards at full 1080×1920 resolution for horizontal clipping.

Use `--force-tts` only when deliberately paying to regenerate the approved take. Use `--render-only` after changing only local visual or audio-mix assets.

## 5. Assemble and verify the editable timeline

Read [references/editable-delivery.md](references/editable-delivery.md). Use the editor named by the user; otherwise prefer a ready local OpenChatCut route and use ChatCut only when its connector is available and media transfer is permitted.

Use the installed editor-specific Skill and its current tool schema. For ChatCut, load `book-sales-video-chatcut`, `chatcut:chatcut-plugin-basics`, asset import, verification, and export instructions as their stages are reached. For local OpenChatCut, run this Skill's reusable `scripts/openchatcut_mcp.py`; it dynamically discovers the port and schema, authenticates with the editor-issued bearer token, reuses `Mcp-Session-Id`, and bypasses HTTP proxies for localhost. Keep credentials outside the project. Never create a book-specific bridge or hard-code a port, application path, project ID, or stale tool arguments.

Build the editor timeline from original components, not `renders/video.mp4`:

- each scene and each carousel cover as independent visual items;
- the true main cover as an ordinary image item;
- narration, BGM, and SFX as separate audio items;
- every Chinese/English card as an editable caption key or text item;
- persistent title/author overlays as editable items when used.

Preserve the exact provider-derived frame ranges. Reopen the returned project ID and read back the live assets, tracks, timeline items, and captions. Normalize those IDs and at least three composed-frame checks into `editable-delivery.json`, freeze current source hashes, then run:

```bash
python3 <SKILL_DIR>/scripts/validate_editable_delivery.py <project>
```

Do not set `status: verified` until the reopened project and timeline IDs match, the project is non-empty, every expected scene/caption/audio mapping is present, and opening/middle/ending composed pixels have been inspected.

## 6. Review and finalize QA

Review `renders/video.mp4`, the whole-film contact sheet, and every scene boundary. Complete every check in `renders/qa/human-review.json`; do not set `passed: true` before verifying:

- whole-film and boundary frames;
- subtitle synchronization and commerce-safe placement;
- cover readability and carousel pace;
- opening source compliance and real visible motion when Pexels was selected;
- body source compliance and scene-by-scene semantic fit;
- opening speech continuity across any silent hold;
- narration pace and audio balance;
- generated-image semantics and spatial logic;
- editable timeline structure and editor-versus-MP4 visual parity;
- claim and CTA boundaries.

Then run:

```bash
python3 <SKILL_DIR>/scripts/build_video.py <project> --qa-only
```

Require correct streams, full decode, exact duration agreement, approved-audio packet equality, complete provider timing provenance, current artifact hashes, acoustic-safe holds, a valid `editable-delivery.json`, all human checks, and a human-review video hash matching the MP4. A successful final QA writes `renders/qa/release-ready.json` containing both the video hash and editor project/timeline identity. Its hashes must match the files being delivered or published. Preflight removes any stale release marker. Automated PASS proves structure, not subjective quality.

An optional editor export does not bypass this Skill's final media and human-review gates. If the editor project changes after release, treat the previous MP4 and release marker as stale, then export or rerender and repeat the review.

## 7. Publish only when requested

Upload or overwrite a hosted version only after explicit user direction and only when `renders/qa/release-ready.json` matches the exact MP4 SHA-256. Prefer one stable site with one path per video instead of a subdomain per video. Preserve attribution and report the exact URL.

## Completion report

Report the confirmed opening/body visual sources, absolute MP4 path, duration, format, editor route and project URL/ID, narration provider and speech rate, timestamp source, QA result, publication URL when applicable, and any remaining publisher judgment.

## Bundled resources

- `scripts/init_case.py`: create a non-overwriting portable project.
- `scripts/validate_case.py`: fail closed on content, caption, manifest, or asset errors.
- `scripts/build_video.py`: generic approved-case orchestrator.
- `scripts/doubao_tts.py`: one-pass Seed TTS 2.0 synthesis with provider timestamps.
- `scripts/build_timestamp_timeline.py`: strict timing alignment and acoustic-safe holds.
- `scripts/render_video.py`: manifest-driven FFmpeg renderer without book-specific code.
- `scripts/search_pexels_videos.py`: Keychain-aware portrait stock search for user-selected Pexels routes.
- `scripts/qa_video.py`: deterministic media and evidence QA.
- `scripts/validate_editable_delivery.py`: reject flattened, empty, stale, or incompletely mapped editor projects.
- `scripts/openchatcut_mcp.py`: reusable authenticated local OpenChatCut discovery and current-schema calls.
- `assets/`: portable case, render, editable-delivery, and human-review templates.
- `references/copywriting.md`: WeRead-to-narration separation, the default narrative profile, length policy, anti-patterns, and editorial review ledger.
- `references/editable-delivery.md`: editor routing, independent-item assembly, readback proof, and MP4 relationship.
- `references/`: research, schema, provider timing, visual, and QA contracts.
