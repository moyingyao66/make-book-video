---
name: make-book-video
description: "Create, regenerate, repair, or batch-produce a Chinese book sales/recommendation video from a title, page, cover, script, or existing project. Use when delivery requires BOTH a QA-verified MP4 and a genuinely editable ChatCut project, including later cover, visual, or caption changes. Trigger for 图书带货、卖书视频、视频号挂车、读书种草、书单推荐 and 书评短视频. Apply source/edition evidence, one-pass Doubao word timestamps, ChatCut readback, and delivery QA. Route MP4-only work to book-sales-video, generic cinematic ChatCut to book-sales-video-chatcut, and explicit HyperFrames work to HyperFrames. Do not trigger for upload/publish-only requests; in a combined request, use this Skill only for production and hand publishing to a separate workflow. Exclude script/article-only tasks, neutral explainers, and existing-footage recuts."
---

# Make Book Video

Deliver a verified editable editor project and a playable MP4 from the same source assets and provider-timestamp timeline. Treat research, script, storyboard, project shells, and previews as intermediate evidence.

## Non-negotiable defaults

- 9:16 at 1080x1920, 30 fps, H.264 plus AAC 48 kHz, unless the user approves another delivery contract.
- One approved `case.json` is content truth; one `render-manifest.json` is render truth.
- Every cover, scene, caption, narration, BGM, and SFX element stays independently editable in ChatCut. The flattened MP4 is never the primary timeline content.
- For a title-first Chinese video: `weread-skills` for research, `cognition-awakening-v1` for narrative, and the real cover from an attributable source. An image model never redraws cover typography, and book-source results are evidence rather than ready-made narration.
- Treat the approved narration as the creative spine. Keep body visuals simple, semantically matched, and free of recognizable human faces by default.
- One Doubao request for the complete narration; provider timestamps and actual audio duration are timing truth.
- Before research or initialization, collect both visual-source choices in one structured selection UI. Recommend Pexels video for the opening and GPT-generated images for the body, but never apply either choice silently.
- The confirmed visual-source choices live in `case.json` and hold for the whole run. No source, style, or count changes without a new explicit user decision.
- Secrets stay out of prompts, files, reports, shell history, and Git.
- Require content approval before paid full-length TTS or batch generation.
- Captions are reviewed bilingual by default; Chinese-only must be declared in `render-manifest.json`.
- Require a reopened, non-empty ChatCut project, human review of both the editor composition and actual MP4, and a current `renders/qa/delivery-ready.json` before reporting completion.
- End at verified local deliverables. Do not upload, host, overwrite, or publish media; route a later publishing request to a separate platform-specific workflow.

## Required production sequence

Read [references/production-workflow.md](references/production-workflow.md) before writing the narration or sourcing media. Use its default film grammar unless the user explicitly approves a `custom` narrative profile:

1. Confirm the edition, audience situation, and one main selling thesis from attributable evidence.
2. Write and validate the complete narration and semantic storyboard, then obtain copy/storyboard approval and authorization for three style previews.
3. Generate the same representative shot in three book-aware, simple styles; obtain the user's choice, then build the final package and obtain full TTS/batch-generation approval. Default to three shared body visuals across the five narrative roles.
4. Design a separate video cover image with only the book title and author by default. Keep the real attributable book cover as a distinct asset.
5. Open with visible moving video and the fixed phrase `今天分享的是。` when `pexels-video` was selected.
6. Follow with a short silent fast-flash carousel of real covers, then reveal the primary real cover while speaking the complete author and title.
7. Continue through narration-derived body scenes: viewer problem, alternative explanation, concrete example, practical boundary, and audience close.
8. Audition the voice, synthesize one full narration request, align scenes and captions to provider timestamps, and mix narration, optional BGM, and SFX on separate tracks.
9. Render the reference MP4, assemble the editor project from original components, reopen and read it back, then review, repair, and rerun validation until both deliveries pass.

Do not skip ahead from a title or article to media generation. At every gate use the loop `create -> validate -> inspect -> repair -> revalidate`; a generated artifact or automated PASS is not visual, editorial, or listening approval.

## Tell the user where they are

Every user-facing line is Chinese. Announce each step before starting it, and close it with the same three things every time, so the user always knows what exists, what to look at, and what their confirmation buys:

```
第 4/7 步：素材已就绪。
产出：visuals/body-01.png（痛点处境）、visuals/body-02.png（新解释+例子）、visuals/body-03.png（边界+收尾）
请确认：每张图说的是不是它对应那几句旁白的意思。
确认后：我用这批素材渲染成片，这一步不花钱。
```

State the cost before the step that spends money, not after. Paid Doubao synthesis at gate 3 and image generation at gate 4 need an explicit go-ahead. Before gate 6, explain that uploads and manual editing are free while ChatCut Agent turns and cloud rendering can consume credits; use the live estimate as billing truth. While waiting for a confirmation, do nothing further — not the next step, and not "just the preparation" for it. When the user rejects something, say which step you are returning to and what you will redo, then stop at that same gate again.

## Stop-and-confirm gates

Stop after each step and wait for an explicit user decision. Never treat silence, an earlier blanket authorization, or the absence of objection as approval. Each gate names what the user looks at:

| Gate | Shown to the user | Blocks |
|---|---|---|
| 1. startup choices | the two-question form | research and initialization |
| 2. content approval | `approval-package.md` in full | any paid TTS |
| 3. voice preview | `audio/voice-preview.wav` | the paid full take |
| 4. visual assets | every sourced clip or generated image, listed by scene | rendering |
| 5. render review | `renders/video.mp4` plus the contact sheets | final QA |
| 6. editor review | the reopened project and the three composed frames | final delivery QA |

Produce the evidence, then hand the paths to the user; do not load rendered frames, contact sheets, or composed editor frames into your own context to grade them. One 1080×1920 frame costs more context than the whole text of this Skill, and a model self-assessment does not close a human gate anyway. Open an image yourself only when the user asks you to diagnose a specific problem they saw.

When the user asks for a change, redo only that step and return to its own gate; do not restart the run or silently carry an old approval forward. Every approval is bound to the hashes recorded at that moment, so any later edit to narration, storyboard, voice config, or manifest semantics invalidates it and needs a new decision.

## 0. Collect all configuration choices first

Show the exact two-question startup form from [references/output-contracts.md](references/output-contracts.md) before research, initialization, or commands, in one structured-choice call with the recommended option first. If the host has no structured choice control, report that blocker and pause.

Record both answers immediately and never ask about visual sources again. Use established Skill defaults for everything that does not need a user choice. For an existing project, read `case.json` first and reuse a `confirmed` `visualSourcePolicy` unless the user explicitly asks to change sources.

## 1. Initialize a portable project

Treat Python setup as the first automatic item in the Skill initialization checklist, not as a user prerequisite. Before running it, tell the user only which tools and libraries this workflow uses: Python 3.8+, the pinned `requests` and `urllib3` packages, FFmpeg/ffprobe, the selected research and visual providers, Doubao TTS, and ChatCut. Do not ask the user to run Python, create a virtual environment, or install packages.

Run the bundled bootstrap yourself before project initialization:

```bash
python3 <SKILL_DIR>/scripts/prepare_env.py
```

It checks the local interpreter, creates or repairs `<SKILL_DIR>/.venv`, installs any missing pinned requirements, and ends with `ENV_PY=<path>`. Capture that path as `<ENV_PY>` and run every later Skill script with it; do not fall back to whatever `python3` resolves to mid-run. If automatic preparation fails because the machine has no Python 3.8+ interpreter or package installation cannot reach its source, report that exact blocker and the affected tool or library instead of turning the bootstrap command into a manual user step.

Resolve the metadata needed by the initializer before running it. A typed title may proceed directly. For a cover or product page without typed metadata, inspect the visible title and author after the startup choices, mark that extraction unverified, then confirm the exact edition through the WeRead-first research route or an attributable fallback. Only then pass the confirmed title/author to `init_case.py`; never invent placeholder metadata merely to initialize early.

Run:

```bash
python3 <SKILL_DIR>/scripts/init_case.py <project> \
  --title "<book>" --author "<author>" \
  --opening-source <pexels-video|gpt-image> \
  --body-source <gpt-image|pexels-video> \
  [--body-visuals 3] [--carousel-covers 3]
```

This creates `case.json`, `render-manifest.json`, `editable-delivery.json`, the human-review ledger, the research record, and stable project directories without overwriting existing files.

Both source flags are required and must come from the startup selection form. Initialization writes them to `visualSourcePolicy`, materializes matching scene assets and Pexels evidence ledgers, and refuses to guess when either answer is missing.

A one-minute video does not need one generated image per segment. `--body-visuals` defaults to 3 shared body visuals across the five narrated roles, split in narrative order. The split is recorded in `visualSourcePolicy.visualPlan` and enforced by the validator, so the run cannot quietly grow back to one asset per scene; raise it only when the user asks or a group genuinely spans two situations one still cannot carry. `--carousel-covers` stays at 5: those are real covers that `weread-skills` already returns, so they cost almost nothing to collect.

Keep every asset path project-relative. Do not put book-specific paths, scene IDs, frame counts, or application paths in Skill scripts. Read [references/project-schema.md](references/project-schema.md) only when you need a field-level rule or a validator rejects a control file.

Read [references/environment.md](references/environment.md), run the research dependency gate, and follow its `stageStates.research.nextAction`:

```bash
python3 <SKILL_DIR>/scripts/check_environment.py --project <project> --stage research
```

## 2. Research and approve content

Read [references/research.md](references/research.md), [references/copywriting.md](references/copywriting.md), and the narration section of [references/production-workflow.md](references/production-workflow.md). Record exact book identity, attributable cover source, review clusters, selected angle, claim categories, omissions, and downloaded-cover checksum.

Route the input explicitly:

- **Book title or book page:** use installed `weread-skills` first for identity, directory, popular highlights, and public reviews. Record its version, `bookId`, captured endpoints, and whether private notes were used. Use another attributable source only when WeRead is unavailable or lacks the required field, and record the fallback instead of silently substituting it.
- **Cover image or product page without typed metadata:** identify the visible title and author first, treat that extraction as unverified, then confirm the exact edition through the same WeRead-first route before initialization or script writing.
- **Notes needing a script:** verify book claims, then write with the default narrative profile.
- **User-approved script:** preserve wording and order. Use research only to flag conflicts unless the user asks for rewriting. Set `narrativeProfile.id` to `preserve-approved-script` when the fixed profile should not be imposed.

When the preflight reports research `degraded` and `fallback-required`, attempt WeRead first, then add at least one authoritative HTTP(S) fallback source plus its reason. Continue research with that recorded evidence; do not treat a missing WeRead credential as permission to skip source checking. Custom and preserved-script profiles still require claims, segment mappings, and a completed copy-review ledger.

When `WEREAD_API_KEY` is absent from the current process on macOS but was saved in Keychain, run WeRead commands through `scripts/with_weread_env.zsh`. The wrapper injects the credential only into that child process and must not print or persist it. For example, verify availability with `scripts/with_weread_env.zsh --check`; do not copy the key into a project file, shell profile, prompt, report, or command argument.

For new writing, follow `cognition-awakening-v1`: exact fixed opening, silent carousel, complete author/title reveal, concrete viewer situation, alternative explanation, one or two supporting examples, practical boundary, and a close that returns to the viewer. Default to 260–320 non-whitespace narration characters and a 60–75 second planning range unless the user specifies otherwise; a sales video loses the viewer after about a minute.

Write every narrated segment, source-claim mapping, and Chinese caption card in `case.json`. Require the concatenated caption text of each segment to exactly cover that segment's narration after punctuation normalization. The default caption mode is `bilingual`: every card needs a reviewed `enText`. Use `mode: zh-only` only when Chinese-only output was intentionally selected; never label an empty-English timeline as bilingual.

For an anticipation carousel, use `visualPlan.carouselCovers` different real covers (default 5) at about nine frames each at 30 fps, matching the 45-frame hold, and keep the whole title area visible at phone size.

Before generating style previews, run the copy-only gate, show the complete narration and semantic storyboard, and obtain copy/storyboard approval plus authorization for exactly three preview generations:

```bash
python3 <SKILL_DIR>/scripts/validate_case.py <project> --stage copy-preview
```

After the three previews are generated and the user chooses one, record `visualStyleProfile`, then run the final draft gate and approval-package builder below. The later paid-generation authorization covers the full TTS and batch visual run, not merely the three previews.

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

Read [references/visuals.md](references/visuals.md), [references/visual-style-profiles.md](references/visual-style-profiles.md), and the video-cover/opening sections of [references/production-workflow.md](references/production-workflow.md). Use real covers for book identity and follow the startup `visualSourcePolicy` for the opening and narrated body scenes. Deterministic design remains appropriate for video-cover typography, text, and diagrams.

Do not select the image style at startup. Select it only after the narration and semantic storyboard exist. Present exactly three book-appropriate preview styles made from the same representative scene, recommend the strongest semantic fit, and persist the user's choice under `visualStyleProfile` before batch generation. Default to `avoid-recognizable-faces`, one main semantic anchor, no more than two primary subjects, reserved caption space, and no generated text.

Before searching or generating assets, run the selected-source dependency gate:

```bash
python3 <SKILL_DIR>/scripts/check_environment.py --project <project> --stage visuals
```

If its visual state is `local-present-live-unverified`, perform the named live imagegen check through the current host, retain the generated asset and semantic review, and then continue. Treat `blocked-local-prerequisite-missing` as a blocker. Do not misreport a required live check as a missing local installation.

For every asset assigned to Pexels, run `scripts/search_pexels_videos.py` with a query built from the segments that share it, then complete that asset's source ledger with the selected page, creator, file URL, dimensions, attribution, downloaded-file hash, and review decision. Pexels is optional only when the user selected the GPT route. If the user selected Pexels and it is unavailable or no candidate is semantically acceptable, report the blocker; do not silently substitute a still image or generated asset.

For every scene assigned to GPT image generation, use the built-in `imagegen` Skill/tool and save a distinct semantic still at the path already materialized in the manifest. Do not use Pexels as a fallback without an explicit source-policy change.

Embed `case.visualSourcePolicy.visualStyle.promptContract` verbatim in every image prompt, and add only that scene's subject and action on top of it. The style is frozen for the whole project so the scenes read as one series; changing it mid-run requires a new user decision and regeneration of the scenes already made under the old style. After each image returns, check it against `visualStyle.forbidden` — rendered text of any kind is an automatic reject, because burned-in Chinese characters cannot be corrected downstream.

Map every narrated segment and intentional hold to an asset in `render-manifest.json`. Use the generic `image`, `video`, `carousel`, or `solid` scene types. Use image overlays to place a true book cover over a designed background.

When every asset exists, list them for the user by group — path, the segments it covers, and the narration those segments carry — and stop at gate 4 for confirmation. The user decides whether the image says what the narration says; record their decision as the per-scene semantic review. Judge an asset only against the segments in its own `visualPlan` group: a shared visual must fit all of them, which is the point of the group boundary. Reject attractive but generic reading media without asking.

## 4. Generate, align, and render

Read [references/doubao-v3-timestamps.md](references/doubao-v3-timestamps.md). Read [references/render-and-qa.md](references/render-and-qa.md) at the review gate, or earlier if an automated check fails.

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

Default 1080×1920 subtitle delivery uses Chinese 72 px, English 40 px, a baseline around y=1500, and at least 360 px of bottom safe area. Wrap Chinese and English independently before ASS rendering; do not rely on libass to wrap long positioned captions. The render writes a frame for the longest Chinese and English cards; show those paths at gate 5 so the user checks horizontal clipping at phone size.

Use `--force-tts` only when deliberately paying to regenerate the approved take. Use `--render-only` after changing only local visual or audio-mix assets.

## 5. Assemble and verify the editable timeline

Read [references/editable-delivery.md](references/editable-delivery.md). ChatCut is the only editable-delivery route. Before transferring project media, explain that uploads are free but ChatCut Agent turns and cloud rendering can consume ChatCut credits; use the live in-product estimate as billing truth.

Before editor assembly, run:

```bash
python3 <SKILL_DIR>/scripts/check_environment.py --project <project> --stage editor
python3 <SKILL_DIR>/scripts/build_editor_plan.py <project>
```

`editor-plan.json` is the deterministic adapter-neutral assembly source: stable `planId` order, carousel splits, provider-derived frame ranges, original source hashes, and effective visual/audio/caption parameters. Rebuild it whenever a bound input or source asset changes. It is a plan, not evidence that an editor was opened or changed; never mark its pending stages complete by hand.

The editor preflight normally reports `connector-present-live-unverified` until ChatCut authenticates, writes, reopens, and reads the project. Use that state as the handoff to the live connector; stop only for `blocked-local-prerequisite-missing`. The later readback validator, not local Skill discovery, closes this gate.

Load `book-sales-video-chatcut`, `chatcut:chatcut-plugin-basics`, `chatcut:asset-import`, `chatcut:verification`, and `chatcut:product-help` as their stages are reached. Use the current ChatCut MCP schema and live credit estimate as runtime truth. Authenticate through the supported connector, transfer only approved project media, and keep credentials outside the project. Do not invoke ChatCut generation tools for assets already created by this Skill. Do not export from ChatCut unless the user explicitly asks and accepts the live credit estimate; the default MP4 remains the local FFmpeg render.

Build the editor timeline from original components, never from `renders/video.mp4`: every scene and carousel cover, the true main cover, narration/BGM/SFX, every Chinese/English caption card, and any persistent title/author overlay as independent editable items. Translate each `planId` and semantic track role into the adapter's current schema; do not recalculate ranges, carousel allocation, source hashes, or effective parameters in the model.

Save every live editor response to a project-relative JSON file as you receive it, reopen the returned project ID, and read back the live assets, tracks, timeline items, and captions. Then bind those IDs instead of retyping the ledger:

```bash
python3 <SKILL_DIR>/scripts/bind_editor_readback.py <project> --emit-binding-template
python3 <SKILL_DIR>/scripts/bind_editor_readback.py <project> \
  --editor-response renders/qa/editor-response.json --status verified
python3 <SKILL_DIR>/scripts/validate_editable_delivery.py <project>
```

Fill `editor-binding.json` with only what the editor returned: route, project/timeline IDs, editor URL, readback source and capture time, one track ID per semantic role, one editor ID per `planId`, and the three composed-frame PNGs. The binder projects every caption string, frame range, source path, and SHA-256 from the frozen plan into `editable-delivery.json` and its readback evidence, and refuses a stale plan, a missing or unknown `planId`, or any ID that never appeared in a recorded editor response. Set `confirmedBy` to the person who looked at the reopened project and the three composed frames, and pass `--status verified` only after they confirm at gate 6. The binder refuses a verified delivery without that name. Never hand-edit either generated file.

## 6. Review and finalize QA

Hand the user `renders/video.mp4`, the whole-film contact sheet, and the boundary sheet, and walk them through the checks in [references/render-and-qa.md](references/render-and-qa.md). Then record their answers in `renders/qa/human-review.json`: every key under `checks`, the per-scene `sceneSemanticReview`, `reviewer`, `confirmationSource: user-confirmed`, and the reviewed video hash. Final QA rejects any other `confirmationSource`, so a ledger you filled in yourself cannot close this gate.

Then run:

```bash
python3 <SKILL_DIR>/scripts/build_video.py <project> --qa-only
```

Require a playable full decode, correct video/audio streams, current narration and timing artifacts, no missing source assets, a valid non-flattened `editable-delivery.json`, all human checks, and a human-review video hash matching the MP4. A successful final QA writes `renders/qa/delivery-ready.json` containing the exact video hash and ChatCut project/timeline identity. Preflight removes any stale delivery marker. Automated PASS proves structure, not subjective quality.

If the ChatCut project changes after delivery QA, treat the previous MP4 and delivery marker as stale, then rerender locally and repeat the affected checks. A later upload or platform publication is outside this Skill.

## Completion report

Use the fixed completion format in [references/output-contracts.md](references/output-contracts.md). Report the confirmed opening/body visual sources, absolute MP4 path, duration, format, ChatCut project URL/ID, narration provider and speech rate, timestamp source, delivery-QA result, ChatCut credit-bearing actions actually used, and any remaining creator judgment.

## Maintenance

After changing routing or workflow contracts, follow [evals/README.md](evals/README.md); do not tune any rule for one book.

## Bundled resources

`scripts/` holds the staged tools this workflow calls by name above; every one fails closed and prints a compact summary. `assets/` holds portable JSON templates, `references/` the stage contracts, and `evals/` the routing suite. Run any script with `--help` rather than reading its source.
