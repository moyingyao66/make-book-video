# Editable delivery contract

The finished job has two linked deliverables: a verified editable timeline and a verified playable MP4. Build both from the same `case.json`, render manifest, provider-timestamp scene timeline, caption timeline, and source assets.

## Contents

- Route selection
- Assembly rules
- Deterministic editor plan
- Readback proof
- MP4 relationship
- Revision routing

## ChatCut route

ChatCut is the only editable-delivery route. Set `editable-delivery.json.route` to `chatcut` during initialization and never leave `auto` in a project.

Load `book-sales-video-chatcut`, `chatcut:chatcut-plugin-basics`, `chatcut:asset-import`, `chatcut:verification`, and `chatcut:product-help` as their stages are reached. Treat the current MCP schema and in-product estimate as authoritative. Authenticate through the supported connector, import only approved project assets, write the timeline from `editor-plan.json`, reopen the returned project, and read it back.

Uploading media does not consume ChatCut credits, but ChatCut Agent turns and cloud rendering may. Before a credit-bearing ChatCut action, show the live estimate and obtain approval. The default workflow does not ask ChatCut to generate images, voice, music, or the final MP4: those assets already exist, and FFmpeg produces the reviewed local render.

If the ChatCut connector is unavailable, unauthenticated, or media transfer is denied, finish the approved local reference render but report the dual-delivery job as blocked before completion. Do not substitute another editor.

## Assembly rules

Do not import `renders/video.mp4` as the primary timeline content. Place the original components separately:

- each narrated scene or carousel cover as one or more editable visual items;
- the true main cover as an ordinary image item rather than generated typography;
- the complete timestamp-adjusted narration as one audio item;
- BGM and every SFX on separate audio items;
- every Chinese/English caption card as an editable caption key or editable text item;
- persistent title/author overlays as editable text or graphics when used.

Use semantic track roles rather than assuming numeric aliases remain stable: primary visuals, overlays, title/captions, narration, BGM, and SFX. Preserve the exact provider-derived frame ranges. The ordered scene timeline must start at frame 0, remain continuous without gaps or overlaps, and end at `totalFrames`. A carousel may have several items for one scene, but their ordered ranges must remain continuous and exactly cover that scene.

For version 4, each short body shot is a separate case segment, manifest scene, editor-plan item, and editor timeline item. Do not flatten several semantic panels into one 15–20 second image. This lets a creator replace one idea, reorder one example, or adjust one crop without rebuilding adjacent visuals.

## Deterministic editor plan

After the provider-derived timing and reference render exist, but before calling an editor adapter, generate the assembly plan:

```bash
python3 <SKILL_DIR>/scripts/build_editor_plan.py <project>
```

`editor-plan.json` is a deterministic, adapter-neutral instruction artifact. It atomically binds `case.json`, `render-manifest.json`, the scene/caption timelines, and the alignment report by project-relative path and SHA-256. It also freezes the canvas, total frames, stable semantic track roles, source-asset hashes, effective manifest parameters, and stable `planId` order for:

- every primary image/video/solid scene, with each carousel cover split into its own exact frame range;
- every manifest overlay with its effective transform and fade;
- every exact Chinese/English caption card and style;
- narration, BGM, and each SFX with effective range, volume, fades, and duration-derived end frame.

The builder rejects unknown scene types, discontinuous or out-of-range timing, stale aligned narration, missing or project-escaping assets, and `renders/` or `output/` media used as primary visual sources. It also rejects a copied source whose bytes match `renders/video.mp4`. A failed rebuild leaves the previous plan untouched.

The Python implementation uses only the standard library. WAV durations are read directly; the existing editor/FFmpeg environment must provide `ffprobe` when a video or non-WAV audio duration is needed for a bounds check.

Use the plan to remove per-run model improvisation: the editor adapter translates each `planId` and semantic `trackRole` to the live editor's current IDs and commands without recalculating timing or media parameters. Follow `operations.stages` in order, then satisfy `readback.requiredPlanIds` with IDs from the reopened project. Rebuild the plan after any bound JSON or source-asset change.

The plan deliberately remains `status: "planned-not-executed"`, `editorExecutionClaimed: false`, and every operation remains pending. It is not editor evidence, must not be hand-edited to claim completion, and cannot replace the independent reopened-project readback, composed-frame captures, `editable-delivery.json`, or its validator.

Delivery QA stores `editor-plan.json` plus its SHA-256 in the delivery marker. The delivery verifier rebuilds the plan from current inputs while still requiring the separate verified editable ledger and live readback evidence. A matching plan proves deterministic instructions and freshness only; it does not prove ChatCut executed them.

## Binding editor IDs to the plan

Never hand-author `editable-delivery.json` or the readback evidence JSON. Both are projections of the frozen plan, so retyping caption text, frame ranges, source paths, or SHA-256 values only creates drift. Save each live editor response to a project-relative JSON file as it arrives, reopen the project, read back assets/tracks/items/captions, then run:

```bash
python3 <SKILL_DIR>/scripts/bind_editor_readback.py <project> --emit-binding-template
python3 <SKILL_DIR>/scripts/bind_editor_readback.py <project> \
  --editor-response renders/qa/editor-response.json --status verified
```

`editor-binding.json` carries only editor-derived facts:

```json
{
  "version": 1,
  "route": "chatcut",
  "projectId": "", "timelineId": "", "editorUrl": "",
  "readback": {"source": "ChatCut project + timeline + caption readback",
               "capturedAt": "2026-01-01T00:00:00Z"},
  "trackIds": {"primary-visuals": "", "overlays": "", "captions": "",
               "narration": "", "bgm": "", "sfx": ""},
  "items": {"primary-0000-0000": {"itemId": "", "assetId": ""},
            "caption-0000": {"editorKey": ""}},
  "verificationFrames": [{"frame": 0, "evidencePath": "renders/qa/editor-open.png", "notes": ""}]
}
```

The binder fails closed when the plan is stale against its bound inputs, when a `planId` is missing, unknown, or given an unsupported field, when a track role has no ID, when the three composed frames do not cover opening/middle/ending as distinct in-range PNGs, and — with `--editor-response` — when any bound ID never appears in a recorded editor response. `--status verified` requires at least one such capture. It writes the evidence JSON first, then `editable-delivery.json` with the evidence hash, both atomically.

Set `confirmedBy` to the person who inspected the reopened project and the three composed frames against the reference MP4, and supply `--status verified` only after they confirm. The binder refuses a verified delivery with an empty `confirmedBy`, and the name is carried into `editable-delivery.json`.

## Readback proof

The generated ledger records route, project/timeline identity, editor URL, canvas, capture time, current hashes of the case, manifest, alignment report, scene timeline, caption timeline, and narration, the four mapping arrays, `readback.evidencePath` plus its SHA-256, and the three composed-frame PNG checks. Opening, middle, and ending are the first, second, and final thirds of `totalFrames`.

Then run the independent gate:

```bash
python3 <SKILL_DIR>/scripts/validate_editable_delivery.py <project>
```

The validator rejects a flattened final video, missing or non-contiguous primary scenes, stale primary or overlay source hashes, missing/duplicate/unknown overlays, overlay transforms that differ from the reference manifest, altered caption text, unknown or non-bijective audio mappings, stale source/readback/evidence hashes, readback JSON that differs from the mappings, an empty project, and a project ID that was not reopened and read back. Each composed-frame evidence file must be a decodable, non-interlaced 8-bit PNG with valid chunk CRCs and zlib data whose IHDR dimensions match the delivery canvas; a renamed text file or wrong-size screenshot fails.

## MP4 relationship

The deterministic FFmpeg render remains the reviewed delivery MP4. Visually compare the ChatCut composition with that MP4 at the opening, a middle scene, and the ending. If the ChatCut project is changed after delivery, the previous MP4 and delivery marker are stale; rerender locally and repeat the affected media and human checks. Any new render attempt or QA run removes the previous `renders/qa/delivery-ready.json` before validation. Only successful delivery QA atomically recreates that marker.

An editor export may be recorded under `optionalEditorExport`, but it does not replace final decode, subtitle, audio, visual, and human-review checks.

The offline ledger and hash validators detect missing, stale, substituted, or internally inconsistent evidence. They do not prove that an unsigned readback JSON came from ChatCut. Perform the live authenticate/write/reopen/readback calls in the current run and let the reviewer inspect the ChatCut UI before completion.

## Revision routing

Route changes by the earliest source of truth they affect:

| Requested change | Rebuild |
|---|---|
| swap one image/clip, crop, motion, poster, BGM, SFX, or mix level | update source/manifest, run `--render-only`, rebuild editor plan, update editor item, reopen/read back, rerun media and visual QA |
| change selected style or face policy while narration stays fixed | reopen content/style approval, regenerate affected visual assets, render-only, rebuild editor plan and readback |
| edit caption translation without changing spoken Chinese | rebuild caption artifacts, render, editor caption items, readback, caption QA |
| change Chinese narration, voice, speech rate, or spoken order | new approval and voice preview, full TTS, provider alignment, scene/caption timelines, render, editor plan, readback, all downstream QA |

Never pay for full narration regeneration to repair a visual-only issue. Never claim a visual-only patch is complete while the editor timeline still points at the old source hash.
