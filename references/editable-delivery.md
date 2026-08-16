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

Use semantic track roles rather than assuming numeric aliases remain stable: primary visuals, overlays, title/captions, narration, BGM, and SFX. Preserve the exact provider-derived frame ranges. A carousel may have several items for one scene, but their combined range must exactly cover that scene.

## Readback proof

After assembly, save the normalized state in `editable-delivery.json`. Reopen the returned project ID, then read the live project and timeline again. Record:

- route, project ID, timeline ID, editor URL, canvas, and capture time;
- current hashes of the case, manifest, alignment report, scene timeline, caption timeline, and narration;
- scene-to-item, caption-to-editor-key, and audio-to-item mappings;
- the live readback asset, track, item, and caption identifiers;
- at least three composed-frame checks covering opening, middle, and ending.

Set `status: verified` only after the reopened project has nonzero assets and timeline items and all expected mappings are present. Run:

```bash
python3 <SKILL_DIR>/scripts/validate_editable_delivery.py <project>
```

The validator rejects a flattened final video, missing scenes or captions, stale source hashes, mismatched frame ranges, an empty project, and a project ID that was not reopened and read back.

## MP4 relationship

The deterministic FFmpeg render remains the reviewed reference MP4 and publication artifact unless an editor export is explicitly selected. Visually compare the editor composition with that MP4 at the opening, a middle scene, and the ending. If the editor project is changed after release, the previous MP4 and release marker are stale; export or rerender and repeat media and human QA.

An editor export may be recorded under `optionalEditorExport`, but it does not replace final decode, subtitle, audio, visual, and human-review checks.
