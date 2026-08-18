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
  "route": "openchatcut-local",
  "projectId": "", "timelineId": "", "editorUrl": "",
  "readback": {"source": "openchatcut read_project + read_timeline + read_captions",
               "capturedAt": "2026-01-01T00:00:00Z"},
  "trackIds": {"primary-visuals": "", "overlays": "", "captions": "",
               "narration": "", "bgm": "", "sfx": ""},
  "items": {"primary-0000-0000": {"itemId": "", "assetId": ""},
            "caption-0000": {"editorKey": ""}},
  "verificationFrames": [{"frame": 0, "evidencePath": "renders/qa/editor-open.png", "notes": ""}]
}
```

The binder fails closed when the plan is stale against its bound inputs, when a `planId` is missing, unknown, or given an unsupported field, when a track role has no ID, when the three composed frames do not cover opening/middle/ending as distinct in-range PNGs, and — with `--editor-response` — when any bound ID never appears in a recorded editor response. `--status verified` requires at least one such capture. It writes the evidence JSON first, then `editable-delivery.json` with the evidence hash, both atomically.

Supply `--status verified` only after the reopened project has nonzero assets and timeline items, every expected mapping is present, and the opening/middle/ending composed pixels have been inspected against the reference MP4.

## Readback proof

The generated ledger records route, project/timeline identity, editor URL, canvas, capture time, current hashes of the case, manifest, alignment report, scene timeline, caption timeline, and narration, the four mapping arrays, `readback.evidencePath` plus its SHA-256, and the three composed-frame PNG checks. Opening, middle, and ending are the first, second, and final thirds of `totalFrames`.

Then run the independent gate:

```bash
python3 <SKILL_DIR>/scripts/validate_editable_delivery.py <project>
```

The validator rejects a flattened final video, missing or non-contiguous primary scenes, stale primary or overlay source hashes, missing/duplicate/unknown overlays, overlay transforms that differ from the reference manifest, altered caption text, unknown or non-bijective audio mappings, stale source/readback/evidence hashes, readback JSON that differs from the mappings, an empty project, and a project ID that was not reopened and read back. Each composed-frame evidence file must be a decodable, non-interlaced 8-bit PNG with valid chunk CRCs and zlib data whose IHDR dimensions match the delivery canvas; a renamed text file or wrong-size screenshot fails.

## MP4 relationship

The deterministic FFmpeg render remains the reviewed reference MP4 and publication artifact unless an editor export is explicitly selected. Visually compare the editor composition with that MP4 at the opening, a middle scene, and the ending. If the editor project is changed after release, the previous MP4 and release marker are stale; export or rerender and repeat media and human QA. Any new render attempt or QA run removes the previous `renders/qa/release-ready.json` before validation. Only a successful final QA atomically recreates that marker.

An editor export may be recorded under `optionalEditorExport`, but it does not replace final decode, subtitle, audio, visual, and human-review checks.

The offline ledger and hash validators detect missing, stale, substituted, or internally inconsistent evidence. They do not cryptographically prove that an unsigned readback JSON was emitted by ChatCut/OpenChatCut rather than authored by a person. The operating agent must therefore perform the live authenticate/write/reopen/readback calls in the current run and the reviewer must inspect the editor UI; use a signed editor receipt or immediate live re-read at release when the chosen editor exposes one.
