---
name: make-book-video
description: "Create, regenerate, repair, batch-produce, or republish a Chinese book sales/recommendation video from a title, page, cover, product page, script, or existing project. Always use this Skill when delivery requires BOTH a QA-verified MP4 and a genuine editable ChatCut/OpenChatCut project, including implicit plans to swap covers, visuals, or captions, reuse the production, revise, or republish. Users need not name the Skill or editor. Prefer this specific workflow over generic video fallbacks. Trigger for 图书带货、卖书视频、视频号挂车、读书种草、书单推荐 and 书评短视频. It applies source/edition evidence, one-pass Doubao word timestamps, editor readback, and release QA by default. Route MP4-only/no-project work to book-sales-video; generic cinematic ChatCut without this contract to book-sales-video-chatcut; explicit or existing HyperFrames projects to HyperFrames. Exclude script/storyboard/article-only tasks, neutral or non-sales explainers, and existing-footage recuts."
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

Read [references/output-contracts.md](references/output-contracts.md) and show its exact two-question startup form before research, initialization, or commands. Use the host's direct structured choice UI in one call; never turn it into prose or typed input. Put the recommended option first, but do not silently apply it. If the host lacks a structured choice control, report that blocker and pause before initialization.

Record both answers immediately and do not ask about visual sources again later. Content/storyboard approval and voice listening review remain later evidence gates, not startup configuration questions. Use established Skill defaults for settings that do not require a user choice.

For an existing project, read `case.json` first. If `visualSourcePolicy.selectionStatus` is already `confirmed`, reuse it and do not ask the startup questions again unless the user explicitly requests a source change.

## 1. Initialize a portable project

Use a working Python 3.8 or newer, preferably from a project virtual environment. If the default `python3` command is broken or too old, locate a supported interpreter before running any Skill script. Install the pinned runtime dependencies from `requirements.txt`.

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

Treat `editor-plan.json` as the deterministic adapter-neutral assembly source. It freezes the current control/timing hashes, stable item order, carousel splits, original asset hashes, effective visual/audio/caption parameters, and pending operation/readback checklist. Rebuild it whenever a bound input or source asset changes. It is a plan, not evidence that an editor was opened or changed; never mark its pending stages complete by hand and never use it in place of live editor readback.

The editor preflight normally reports `local-present-live-unverified` until an adapter authenticates, writes, reopens, and reads the project. Use that state as the handoff to the live editor route; stop only for `blocked-local-prerequisite-missing`. The later readback validator, not local app discovery, closes this gate.

Use the installed editor-specific Skill and its current tool schema. For ChatCut, load `book-sales-video-chatcut`, `chatcut:chatcut-plugin-basics`, asset import, verification, and export instructions as their stages are reached. For local OpenChatCut, run this Skill's reusable `scripts/openchatcut_mcp.py`; it dynamically discovers the port and schema, authenticates with the editor-issued bearer token, reuses `Mcp-Session-Id`, and bypasses HTTP proxies for localhost. Keep credentials outside the project. Never create a book-specific bridge or hard-code a port, application path, project ID, or stale tool arguments.

Build the editor timeline from original components, not `renders/video.mp4`:

- each scene and each carousel cover as independent visual items;
- the true main cover as an ordinary image item;
- narration, BGM, and SFX as separate audio items;
- every Chinese/English card as an editable caption key or text item;
- persistent title/author overlays as editable items when used.

Translate the stable `planId` records and semantic track roles from `editor-plan.json` into the live adapter's current schema; do not recalculate ranges, carousel allocation, source hashes, or effective parameters in the model. Preserve the exact provider-derived frame ranges. Reopen the returned project ID and read back the live assets, tracks, timeline items, and captions. Normalize those IDs and at least three composed-frame checks into `editable-delivery.json`, freeze current source hashes, then run:

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

Immediately before upload, verify every current release artifact rather than trusting an old marker:

```bash
python3 <SKILL_DIR>/scripts/verify_release.py <project>
```

## Completion report

Use the fixed completion format in [references/output-contracts.md](references/output-contracts.md). Report the confirmed opening/body visual sources, absolute MP4 path, duration, format, editor route and project URL/ID, narration provider and speech rate, timestamp source, QA result, publication URL when applicable, and any remaining publisher judgment.

## Evaluation loop

Use [evals/skill-evals.json](evals/skill-evals.json) after changing routing or workflow contracts. Keep 8–10 realistic should-trigger prompts, including at least three natural prompts that imply editability without naming a Skill or editor, plus 8–10 hard negative prompts. Run every prompt three times in the target host and score the recorded booleans:

```bash
python3 <SKILL_DIR>/scripts/score_trigger_evals.py
python3 <SKILL_DIR>/scripts/score_trigger_evals.py --init-results <results.json>
python3 <SKILL_DIR>/scripts/score_trigger_evals.py --results <results.json>
python3 <SKILL_DIR>/scripts/score_execution_evals.py <project> --stage <draft|synthesis|render|release>
python3 -m unittest discover -s <SKILL_DIR>/tests -v
```

Do not tune for one book. Change a rule only when it generalizes across the eval set, then rerun unit tests plus the same repeated trigger suite. The acceptance thresholds are stored in the eval file rather than improvised per run.

## Bundled resources

- `scripts/init_case.py`: create a non-overwriting portable project.
- `scripts/check_environment.py`: stage-aware dependency and credential availability checks.
- `scripts/validate_case.py`: fail closed on content, caption, manifest, or asset errors.
- `scripts/build_approval_package.py`: deterministic full narration/evidence/storyboard review output.
- `scripts/record_approval.py`: atomically record a user approval receipt bound to current content, voice preview, and hashes.
- `scripts/build_video.py`: generic approved-case orchestrator.
- `scripts/doubao_tts.py`: one-pass Seed TTS 2.0 synthesis with provider timestamps.
- `scripts/build_timestamp_timeline.py`: strict timing alignment and acoustic-safe holds.
- `scripts/render_video.py`: manifest-driven FFmpeg renderer without book-specific code.
- `scripts/build_editor_plan.py`: atomically freeze a deterministic adapter-neutral original-component assembly plan; it never claims editor execution.
- `scripts/search_pexels_videos.py`: Keychain-aware portrait stock search for user-selected Pexels routes.
- `scripts/qa_video.py`: deterministic media and evidence QA.
- `scripts/verify_release.py`: fail closed when any release-bound artifact changed after QA.
- `scripts/validate_editable_delivery.py`: reject flattened, empty, stale, or incompletely mapped editor projects.
- `scripts/openchatcut_mcp.py`: reusable authenticated local OpenChatCut discovery and current-schema calls.
- `scripts/score_trigger_evals.py`: validate and score three-run routing observations.
- `scripts/score_execution_evals.py`: score objective project gates at draft, synthesis, render, or release.
- `assets/`: portable case, render, editable-delivery, and human-review templates.
- `evals/skill-evals.json`: balanced implicit trigger and hard-negative evaluation suite.
- `references/environment.md`: staged dependencies, network surfaces, and secret handling.
- `references/output-contracts.md`: exact startup, approval, completion, and routing examples.
- `references/examples.md`: filled startup, approval, and fail-closed output examples; never treat them as execution evidence.
- `references/copywriting.md`: WeRead-to-narration separation, the default narrative profile, length policy, anti-patterns, and editorial review ledger.
- `references/editable-delivery.md`: editor routing, independent-item assembly, readback proof, and MP4 relationship.
- `references/`: research, schema, provider timing, visual, and QA contracts.
