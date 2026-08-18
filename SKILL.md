---
name: make-book-video
description: "Create, regenerate, repair, batch-produce, or republish a Chinese book sales/recommendation video (图书带货、卖书视频、视频号挂车、读书种草、书单推荐、书评短视频) from a title, page, cover, product page, script, or existing project. Always use it when delivery needs BOTH a QA-verified MP4 and a genuine editable ChatCut/OpenChatCut project, including implicit plans to swap covers, visuals, or captions, reuse the production, revise, or republish; users need not name the Skill or editor. It applies source/edition evidence, one-pass Doubao word timestamps, editor readback, and release QA by default. Route MP4-only/no-project work to book-sales-video, generic cinematic ChatCut to book-sales-video-chatcut, and explicit or existing HyperFrames projects to HyperFrames. Exclude script/storyboard/article-only tasks, neutral or non-sales explainers, and existing-footage recuts."
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

## Stop-and-confirm gates

Stop and wait for an explicit user decision at each of these points, and never treat silence, an earlier blanket authorization, or the absence of objection as approval:

1. the two startup visual-source questions, before research or initialization;
2. content and storyboard approval plus paid-generation authorization, before any full-length TTS;
3. voice preview listening approval, before the paid full take;
4. human review of the reopened editor project and the actual MP4, before final QA;
5. publication, before any upload or overwrite.

When the user asks for a change, redo only that step and return to its own gate; do not restart the run or silently carry an old approval forward. Every approval is bound to the hashes recorded at that moment, so any later edit to narration, storyboard, voice config, or manifest semantics invalidates it and needs a new decision.

## 0. Collect all configuration choices first

Show the exact two-question startup form from [references/output-contracts.md](references/output-contracts.md) before research, initialization, or commands, in one structured-choice call with the recommended option first. If the host has no structured choice control, report that blocker and pause.

Record both answers immediately and never ask about visual sources again. Use established Skill defaults for everything that does not need a user choice. For an existing project, read `case.json` first and reuse a `confirmed` `visualSourcePolicy` unless the user explicitly asks to change sources.

## 1. Initialize a portable project

Prepare one pinned interpreter and use it for every later script; do not fall back to whatever `python3` resolves to mid-run:

```bash
python3 <SKILL_DIR>/scripts/prepare_env.py
```

It creates or reuses `<SKILL_DIR>/.venv`, installs the pinned `requirements.txt`, and ends with `ENV_PY=<path>`. Capture that path as `<ENV_PY>` and run every command below with it.

Resolve the metadata needed by the initializer before running it. A typed title may proceed directly. For a cover or product page without typed metadata, inspect the visible title and author after the startup choices, mark that extraction unverified, then confirm the exact edition through the WeRead-first research route or an attributable fallback. Only then pass the confirmed title/author to `init_case.py`; never invent placeholder metadata merely to initialize early.

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

Read [references/environment.md](references/environment.md), run the research dependency gate, and follow its `stageStates.research.nextAction`:

```bash
python3 <SKILL_DIR>/scripts/check_environment.py --project <project> --stage research
```

## 2. Research and approve content

Read [references/research.md](references/research.md) and [references/copywriting.md](references/copywriting.md). Record exact book identity, attributable cover source, review clusters, selected angle, claim categories, omissions, and downloaded-cover checksum.

Route the input explicitly:

- **Book title or book page:** use installed `weread-skills` first for identity, directory, popular highlights, and public reviews. Record its version, `bookId`, captured endpoints, and whether private notes were used. Use another attributable source only when WeRead is unavailable or lacks the required field, and record the fallback instead of silently substituting it.
- **Cover image or product page without typed metadata:** identify the visible title and author first, treat that extraction as unverified, then confirm the exact edition through the same WeRead-first route before initialization or script writing.
- **Notes needing a script:** verify book claims, then write with the default narrative profile.
- **User-approved script:** preserve wording and order. Use research only to flag conflicts unless the user asks for rewriting. Set `narrativeProfile.id` to `preserve-approved-script` when the fixed profile should not be imposed.

When the preflight reports research `degraded` and `fallback-required`, attempt WeRead first, then add at least one authoritative HTTP(S) fallback source plus its reason. Continue research with that recorded evidence; do not treat a missing WeRead credential as permission to skip source checking. Custom and preserved-script profiles still require claims, segment mappings, and a completed copy-review ledger.

When `WEREAD_API_KEY` is absent from the current process on macOS but was saved in Keychain, run WeRead commands through `scripts/with_weread_env.zsh`. The wrapper injects the credential only into that child process and must not print or persist it. For example, verify availability with `scripts/with_weread_env.zsh --check`; do not copy the key into a project file, shell profile, prompt, report, or command argument.

For new writing, follow `cognition-awakening-v1`: exact fixed opening, silent carousel, complete author/title reveal, concrete viewer situation, alternative explanation, one or two supporting examples, practical boundary, and a close that returns to the viewer. Default to 350–420 non-whitespace narration characters and an 80–95 second planning range unless the user specifies otherwise.

Write every narrated segment, source-claim mapping, and Chinese caption card in `case.json`. Require the concatenated caption text of each segment to exactly cover that segment's narration after punctuation normalization. The default caption mode is `bilingual`: every card needs a reviewed `enText`. Use `mode: zh-only` only when Chinese-only output was intentionally selected; never label an empty-English timeline as bilingual.

For an anticipation carousel, default to five different real covers at about nine frames each at 30 fps. Keep the whole title area visible at phone size. Use fewer only after readability review.

Run the draft validator before presenting the approval package. It must reject a conceptual hook before the fixed opening, a missing carousel boundary, a reveal without the title, a draft outside its declared length range, missing WeRead capture for a title-first route, or an incomplete copy-review ledger:

```bash
python3 <SKILL_DIR>/scripts/validate_case.py <project> --stage draft
python3 <SKILL_DIR>/scripts/build_approval_package.py <project>
```

Show `approval-package.md` exactly as defined in [references/output-contracts.md](references/output-contracts.md); do not replace the full narration with a summary. Stop for content/storyboard approval and paid-generation authorization. After that approval, generate a short voice preview, obtain listening approval, and use the bundled approval recorder to bind the approved content, storyboard, voice settings, preview audio, and approval package to hashes. Never set `case.status` or approval booleans by hand.

Generate the preview with the same `resourceId`, `speaker`, `speechRate`, and subtitle setting stored in `case.json`; `doubao_tts.py` writes the required adjacent report automatically. After the user listens and approves it, record the receipt:

```bash
python3 <SKILL_DIR>/scripts/doubao_tts.py \
  --text "<short excerpt from the approved narration>" \
  --output <project>/audio/voice-preview.wav \
  --resource-id "<case.voice.resourceId>" \
  --speaker "<case.voice.speaker>" \
  --speech-rate <case.voice.speechRate>
python3 <SKILL_DIR>/scripts/record_approval.py <project> \
  --approved-by "<user or review channel>" \
  --voice-preview audio/voice-preview.wav
```

The recorder verifies the preview report against the WAV and current voice config. If the narration, storyboard, manifest semantics, voice config, preview/report, or approval package changes later, the receipt becomes invalid and a new review cycle is required.

Validate the recorded receipt again before any full-length paid call:

```bash
python3 <SKILL_DIR>/scripts/validate_case.py <project> --stage synthesis
```

## 3. Source visuals

Read [references/visuals.md](references/visuals.md). Use real covers for book identity and follow the startup `visualSourcePolicy` for the opening and narrated body scenes. Deterministic design remains appropriate for text and diagrams.

Before searching or generating assets, run the selected-source dependency gate:

```bash
python3 <SKILL_DIR>/scripts/check_environment.py --project <project> --stage visuals
```

If its visual state is `local-present-live-unverified`, perform the named live imagegen check through the current host, retain the generated asset and semantic review, and then continue. Treat `blocked-local-prerequisite-missing` as a blocker. Do not misreport a required live check as a missing local installation.

For every scene assigned to Pexels, run `scripts/search_pexels_videos.py` with a scene-specific query, inspect actual frames, then complete that scene's source ledger with the selected page, creator, file URL, dimensions, attribution, downloaded-file hash, and review decision. Pexels is optional only when the user selected the GPT route. If the user selected Pexels and it is unavailable or no candidate is semantically acceptable, report the blocker; do not silently substitute a still image or generated asset.

For every scene assigned to GPT image generation, use the built-in `imagegen` Skill/tool and save a distinct semantic still at the path already materialized in the manifest. Do not use Pexels as a fallback without an explicit source-policy change.

Embed `case.visualSourcePolicy.visualStyle.promptContract` verbatim in every image prompt, and add only that scene's subject and action on top of it. The style is frozen for the whole project so the scenes read as one series; changing it mid-run requires a new user decision and regeneration of the scenes already made under the old style. After each image returns, check it against `visualStyle.forbidden` — rendered text of any kind is an automatic reject, because burned-in Chinese characters cannot be corrected downstream.

Map every narrated segment and intentional hold to an asset in `render-manifest.json`. Use the generic `image`, `video`, `carousel`, or `solid` scene types. Use image overlays to place a true book cover over a designed background.

For every body scene, compare the actual image or sampled video frames with that segment's narration and `visualIntent`. Reject attractive but generic reading media, unexplained repeated actions, or an asset whose main action belongs to another segment. Record per-scene semantic review before the final render.

## 4. Generate, align, and render

Read [references/doubao-v3-timestamps.md](references/doubao-v3-timestamps.md) and [references/render-and-qa.md](references/render-and-qa.md).

Set the approved speaker in `case.json`. For `zh_male_cixingjieshuonan_uranus_bigtts`, start at provider `speechRate: 20`, audition a short excerpt, and record any approved change. Prefer provider-side rate control over FFmpeg `atempo`.

Run the generic pipeline:

```bash
python3 <SKILL_DIR>/scripts/check_environment.py --project <project> --stage production
python3 <SKILL_DIR>/scripts/build_video.py <project>
```

The pipeline must:

1. Revalidate content approval.
2. Generate the complete narration in one Doubao Seed TTS 2.0 V3 request with `enable_subtitle: true`.
3. Run full narration with `--retries 1`, then require non-empty, monotonic `sentence.words`, `X-Tt-Logid`, `requestMode: single`, `providerRequestCount: 1`, and actual `providerAttemptCount: 1`; never hide a retry inside one reported request.
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

Before editor assembly, run:

```bash
python3 <SKILL_DIR>/scripts/check_environment.py --project <project> --stage editor
python3 <SKILL_DIR>/scripts/build_editor_plan.py <project>
```

`editor-plan.json` is the deterministic adapter-neutral assembly source: stable `planId` order, carousel splits, provider-derived frame ranges, original source hashes, and effective visual/audio/caption parameters. Rebuild it whenever a bound input or source asset changes. It is a plan, not evidence that an editor was opened or changed; never mark its pending stages complete by hand.

The editor preflight normally reports `local-present-live-unverified` until an adapter authenticates, writes, reopens, and reads the project. Use that state as the handoff to the live editor route; stop only for `blocked-local-prerequisite-missing`.

Use the installed editor-specific Skill and its current tool schema. For ChatCut, load `book-sales-video-chatcut`, `chatcut:chatcut-plugin-basics`, asset import, verification, and export instructions as their stages are reached. For local OpenChatCut, run this Skill's reusable `scripts/openchatcut_mcp.py`; it discovers the port and schema at runtime, authenticates with the editor-issued bearer token, reuses `Mcp-Session-Id`, and bypasses HTTP proxies for localhost. Keep credentials outside the project. Never create a book-specific bridge or hard-code a port, application path, project ID, or stale tool arguments.

Build the editor timeline from original components, never from `renders/video.mp4`: every scene and carousel cover, the true main cover, narration/BGM/SFX, every Chinese/English caption card, and any persistent title/author overlay as independent editable items. Translate each `planId` and semantic track role into the adapter's current schema; do not recalculate ranges, carousel allocation, source hashes, or effective parameters in the model.

Save every live editor response to a project-relative JSON file as you receive it, reopen the returned project ID, and read back the live assets, tracks, timeline items, and captions. Then bind those IDs instead of retyping the ledger:

```bash
python3 <SKILL_DIR>/scripts/bind_editor_readback.py <project> --emit-binding-template
python3 <SKILL_DIR>/scripts/bind_editor_readback.py <project> \
  --editor-response renders/qa/editor-response.json --status verified
python3 <SKILL_DIR>/scripts/validate_editable_delivery.py <project>
```

Fill `editor-binding.json` with only what the editor returned: route, project/timeline IDs, editor URL, readback source and capture time, one track ID per semantic role, one editor ID per `planId`, and the three composed-frame PNGs. The binder projects every caption string, frame range, source path, and SHA-256 from the frozen plan into `editable-delivery.json` and its readback evidence, and refuses a stale plan, a missing or unknown `planId`, or any ID that never appeared in a recorded editor response. Pass `--status verified` only after the reopened project is non-empty, every expected mapping is present, and opening/middle/ending composed pixels have been inspected. Never hand-edit either generated file.

## 6. Review and finalize QA

Review `renders/video.mp4`, the whole-film contact sheet, and every scene boundary against the editor composition. Then complete `renders/qa/human-review.json`: every key under `checks`, the per-scene `sceneSemanticReview`, the reviewer, and the reviewed video hash. [references/render-and-qa.md](references/render-and-qa.md) defines what each key means; never set `passed: true` before verifying each one on the actual media.

Then run:

```bash
python3 <SKILL_DIR>/scripts/build_video.py <project> --qa-only
```

Require correct streams, full decode, exact duration agreement, approved-audio packet equality, complete provider timing provenance, current artifact hashes, acoustic-safe holds, a valid `editable-delivery.json`, all human checks, and a human-review video hash matching the MP4. A successful final QA writes `renders/qa/release-ready.json` containing both the video hash and editor project/timeline identity. Its hashes must match the files being delivered or published. Preflight removes any stale release marker. Automated PASS proves structure, not subjective quality.

An optional editor export does not bypass this Skill's final media and human-review gates. If the editor project changes after release, treat the previous MP4 and release marker as stale, then export or rerender and repeat the review.

## 7. Publish only when requested

Upload or overwrite a hosted version only after explicit user direction and only when `renders/qa/release-ready.json` matches the exact MP4 SHA-256. Prefer one stable site with one path per video instead of a subdomain per video. Preserve attribution and report the exact URL.

Immediately before upload, verify every current release artifact rather than trusting an old marker:

```bash
python3 <SKILL_DIR>/scripts/verify_release.py <project>
```

## Completion report

Use the fixed completion format in [references/output-contracts.md](references/output-contracts.md). Report the confirmed opening/body visual sources, absolute MP4 path, duration, format, editor route and project URL/ID, narration provider and speech rate, timestamp source, QA result, publication URL when applicable, and any remaining publisher judgment.

## Maintenance

After changing routing or workflow contracts, follow [evals/README.md](evals/README.md); do not tune any rule for one book.

## Bundled resources

`scripts/` holds the staged tools this workflow calls by name above; every one fails closed and prints a compact summary. `assets/` holds portable JSON templates, `references/` the stage contracts, and `evals/` the routing suite. Run any script with `--help` rather than reading its source.
