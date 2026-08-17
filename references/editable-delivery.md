# Editable delivery contract

The finished job has two linked deliverables: a verified editable timeline and a verified playable MP4. Build both from the same `case.json`, render manifest, provider-timestamp scene timeline, caption timeline, and source assets.

## Route selection

Use the editor named by the user. Otherwise prefer a ready local OpenChatCut installation; use ChatCut only when its connector is available and transferring the required media is permitted. Set `editable-delivery.json.route` to `openchatcut-local` or `chatcut` before assembly. Never leave `auto` in a final delivery.

For ChatCut, load `book-sales-video-chatcut`, `chatcut:chatcut-plugin-basics`, asset import, verification, and export instructions as their stages are reached. Treat the current MCP schema as authoritative.

For local OpenChatCut, run `scripts/openchatcut_mcp.py status` and `scripts/openchatcut_mcp.py list-tools`, then use `call` with arguments taken from the live schema. The reusable Skill-level bridge discovers the port at runtime, authenticates with the editor-issued bearer token, reuses its `Mcp-Session-Id`, and bypasses environment HTTP proxies for localhost. Keep the token outside the project. Do not copy the adapter into an individual book directory or hard-code a port, tool arguments, project ID, or application bundle path.

If neither route is ready, finish research, assets, provider timing, and the local reference render, but report the job as blocked before final delivery.

## Assembly rules

Do not import `renders/video.mp4` as the primary timeline content. Place the original components separately:

- each narrated scene or carousel cover as one or more editable visual items;
- the true main cover as an ordinary image item rather than generated typography;
- the complete timestamp-adjusted narration as one audio item;
- BGM and every SFX on separate audio items;
- every Chinese/English caption card as an editable caption key or editable text item;
- persistent title/author overlays as editable text or graphics when used.

Use semantic track roles rather than assuming numeric aliases remain stable: primary visuals, overlays, title/captions, narration, BGM, and SFX. Preserve the exact provider-derived frame ranges. The ordered scene timeline must start at frame 0, remain continuous without gaps or overlaps, and end at `totalFrames`. A carousel may have several items for one scene, but their ordered ranges must remain continuous and exactly cover that scene.

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

Final QA stores `editor-plan.json` plus its SHA-256 in the release marker. The release verifier rebuilds the plan from current inputs and requires exact JSON equality while still requiring the separate verified editable ledger and live readback evidence. A matching plan proves deterministic instructions and freshness only; it does not prove an editor executed them.

Every primary visual `sceneItems[]` record must include `sceneId`, item/asset/track IDs, exact frames, `sourcePath`, `sourceSha256`, and `editable: true`. `sourcePath` must be a project-relative source declared for that scene in `render-manifest.json`: `path` for image/video scenes, every entry under `items` for a carousel, and an exact empty string for a solid scene. `sourceSha256` must match the current referenced file; use an exact empty string for a source-free solid scene. This separates the primary scene continuity contract from overlays while making a later source-file replacement invalidate the delivery.

Record every `sceneAssets.<sceneId>.overlays[]` entry separately under `assembly.overlayItems`; never mix overlays into `sceneItems` or use them to satisfy primary-scene continuity. Bind each overlay one-to-one with the composite key `sceneId` plus zero-based `manifestIndex`. Each mapping must carry unique `itemId`, `assetId`, `trackId`, the full owning scene's `startFrame`/`endFrame`, exact project-relative `sourcePath` and current `sourceSha256`, `editable: true`, and the reference renderer's effective `layerRole`, `x`, `y`, `width`, `height`, and `fadeInSeconds`. The defaults are `layerRole: "overlay"`, `x: "(W-w)/2"`, `y: "(H-h)/2"`, width/height `0`, and fade `0.0`; store `x` and `y` as strings because the reference renderer passes them to FFmpeg as expressions. Width and height are non-negative JSON integers and fade is a non-negative finite JSON number. Overlay ranges may overlap their primary scene by design and are not part of the gap/overlap check for `sceneItems`.

Use `editable-delivery.json` version 2. Every caption mapping must carry `captionId`, a unique `editorKey`, `trackId`, exact `startFrame`/`endFrame`, and exact string values for both `zhText` and `enText`. Chinese-only cards still record `enText: ""`; whitespace and punctuation are not normalized during this comparison.

Every audio mapping must carry `role`, zero-based `manifestIndex`, item/asset/track IDs, `sourcePath`, `sourceSha256`, `startFrame`, `endFrame`, `volume`, `fadeInSeconds`, `fadeOutSeconds`, and `editable: true`. Only `narration`, `bgm`, and `sfx` roles are allowed. Narration and BGM use `manifestIndex: 0`; each SFX uses its array index from `render-manifest.json.audio.sfx`. Narration and BGM cover the complete timeline. SFX start frames follow manifest `startFrame`, or the renderer's millisecond-rounded `startSeconds`; end frames are derived from the hashed source audio duration and clipped at `totalFrames`. The reference renderer applies SFX fade-in before delay and applies fade-out with reverse/fade/reverse before delay, so nonzero fade values affect both the reference mix and the editable mapping contract. Paths, hashes, ranges, volume, and fades must exactly match the effective manifest values. Frame/index fields must be JSON integers, and volume/fade fields must be non-negative finite JSON numbers; numeric strings, booleans, negative values, NaN, infinity, and fractional frames are invalid. A manifest with no BGM must have no editable BGM item, and every SFX must have exactly one item.

## Readback proof

After assembly, save the normalized state in `editable-delivery.json`. Reopen the returned project ID, then read the live project and timeline again. Save that normalized live response as an independent project-relative JSON evidence file; do not copy self-declared ID arrays into the delivery ledger. Record:

- route, project ID, timeline ID, editor URL, canvas, and capture time;
- current hashes of the case, manifest, alignment report, scene timeline, caption timeline, and narration;
- scene-to-item, overlay-to-item, caption-to-editor-key, and audio-to-item mappings;
- `readback.evidencePath` and `readback.sha256` for the independent normalized JSON evidence;
- at least three distinct composed-frame PNG checks covering opening, middle, and ending. For each record, store `position` (`opening`, `middle`, or `ending`), the exact zero-based `frame`, a distinct project-relative `evidencePath`, and that PNG's `sha256`. Opening, middle, and ending are the first, second, and final thirds of `totalFrames`.

The readback evidence JSON uses this normalized contract:

```json
{
  "version": 2,
  "source": "openchatcut read_project + read_timeline + read_captions",
  "capturedAt": "2026-01-01T00:00:00Z",
  "projectReopened": true,
  "projectId": "returned-project-id",
  "timelineId": "returned-timeline-id",
  "canvas": {"width": 1080, "height": 1920, "fps": 30},
  "assetIds": [],
  "trackIds": [],
  "itemIds": [],
  "captionKeys": [],
  "sceneItems": [],
  "overlayItems": [],
  "captionItems": [],
  "audioItems": []
}
```

Populate the arrays from the reopened editor response. ID arrays must contain exactly the IDs used by the mappings, with neither duplicates nor extras. The four mapping arrays must reproduce the normalized assembly mappings exactly, including every primary/overlay source hash, overlay transform, caption string, and audio path/hash/range/mix field. Freeze this JSON first, then place its current SHA-256 in `editable-delivery.json.readback.sha256`.

Set `status: verified` only after the reopened project has nonzero assets and timeline items and all expected mappings are present. Run:

```bash
python3 <SKILL_DIR>/scripts/validate_editable_delivery.py <project>
```

The validator rejects a flattened final video, missing or non-contiguous primary scenes, stale primary or overlay source hashes, missing/duplicate/unknown overlays, overlay transforms that differ from the reference manifest, altered caption text, unknown or non-bijective audio mappings, stale source/readback/evidence hashes, readback JSON that differs from the mappings, an empty project, and a project ID that was not reopened and read back. Each composed-frame evidence file must be a decodable, non-interlaced 8-bit grayscale/RGB/grayscale-alpha/RGBA PNG with valid chunk CRCs, valid zlib image data and scanline lengths, and IHDR dimensions exactly matching the delivery canvas; a renamed text file, CRC-correct invalid payload, or wrong-size screenshot fails.

## MP4 relationship

The deterministic FFmpeg render remains the reviewed reference MP4 and publication artifact unless an editor export is explicitly selected. Visually compare the editor composition with that MP4 at the opening, a middle scene, and the ending. If the editor project is changed after release, the previous MP4 and release marker are stale; export or rerender and repeat media and human QA. Any new render attempt or QA run removes the previous `renders/qa/release-ready.json` before validation. Only a successful final QA atomically recreates that marker.

An editor export may be recorded under `optionalEditorExport`, but it does not replace final decode, subtitle, audio, visual, and human-review checks.

The offline ledger and hash validators detect missing, stale, substituted, or internally inconsistent evidence. They do not cryptographically prove that an unsigned readback JSON was emitted by ChatCut/OpenChatCut rather than authored by a person. The operating agent must therefore perform the live authenticate/write/reopen/readback calls in the current run and the reviewer must inspect the editor UI; use a signed editor receipt or immediate live re-read at release when the chosen editor exposes one.
