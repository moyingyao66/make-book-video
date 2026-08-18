# Render and QA contract

## Frozen inputs

Before rendering, freeze:

- approved narration text;
- timestamped raw WAV and provider report;
- scene and caption timelines derived from provider words;
- real covers and their source records;
- selected stock footage and attribution;
- generated visuals;
- BGM and SFX licenses or local origins.
- approved `case.json` and `render-manifest.json`.
- reopened editable-project readback and `editable-delivery.json`.

The final release sentinel is `renders/qa/release-ready.json` using `make-book-video-release-v2`. It is created only by a successful non-preflight QA run and must identify the exact video, approved audio mix, raw narration WAV, provider TTS report, provider word timeline, QA report, build report, human-review ledger, editable-delivery ledger, and deterministic `editor-plan.json` SHA-256 values. It also copies the render-input inventory frozen in `build_report.json`. Its ordered `humanEvidence` entries bind every file listed in `human-review.json.evidence` by project-relative path and current SHA-256. Every QA or render attempt removes a stale sentinel before it can fail; only a complete successful final QA recreates it atomically. Older markers without the complete artifact chain must be regenerated.

Render only local files. Build scenes from timing JSON; never re-estimate duration from text length.

Run `scripts/render_video.py <project>` through `scripts/build_video.py`. Map every timeline scene to `image`, `video`, `carousel`, or `solid` in the render manifest. Keep all paths project-relative; never store an application bundle path or a book-specific absolute path.

Use `timing/scene-timeline.json`, `timing/caption-timeline.json`, `timing/subtitles.ass`, and `timing/narration.timestamped.final.wav` from the same build. Do not point a renderer at a previous `subtitles.ass`, narration WAV, hard-coded frame list, or total duration.

## Audio

Keep narration intelligible and BGM low. Save the approved final audio mix separately as `renders/audio_mix.m4a`. When muxing, copy its AAC stream if possible so packet-hash verification can prove the final video contains the approved mix.

## Required automated QA

- non-empty playable MP4;
- H.264 video, 1080x1920, 30 fps;
- AAC audio at 48 kHz;
- full FFmpeg decode succeeds;
- duration plus final video/audio-mix SHA-256 values match `build_report.json`;
- `build_report.json` contains the canonical, project-relative path and SHA-256 inventory for every render-time control, timing file, ASS subtitle, scene primary/carousel/overlay asset, narration/BGM/SFX input, provider artifact, Pexels source record, and version-3+ approval preview/report/package; the renderer hashes it before and after rendering and refuses a mid-render change;
- final QA and `verify_release.py` independently rebuild that inventory from the current case, manifest, alignment report, and filesystem; changing a source without rerendering invalidates release even if an editable ledger is rewritten;
- final audio packet hash matches `renders/audio_mix.m4a`;
- the release marker and QA report bind the exact SHA-256 of `renders/audio_mix.m4a`;
- TTS report proves `provider: doubao-direct-v3`, exactly one provider request and one HTTP-200 attempt, retains `X-Tt-Logid`, and reconciles each request `wordCount` with canonical sequential provider keys;
- text coverage is exactly `1.0` and every caption has non-empty provider word keys;
- final QA independently reruns the timestamp builder from the canonical raw WAV, provider report, case, and manifest caption settings; the rebuilt narration PCM, scene timeline, caption timeline, word timeline, alignment report, and ASS must match the release candidates (only replay-temp output paths are normalized);
- timestamped narration, alignment report, scene timeline, caption timeline, and ASS hashes match `build_report.json`;
- `case.json` and `render-manifest.json` hashes match `build_report.json`;
- ASS dialogue count equals the caption ledger count;
- every inserted visual hold uses `boundaryMethod: verified-pcm-silence`, meets its minimum quiet duration, and has a guard-window RMS at or below the recorded threshold;
- the fixed `renders/qa/final-contact-sheet.png` and `renders/qa/boundary-contact-sheet.png` are valid PNGs, are listed once in `human-review.json.evidence`, remain inside the project, and are hash-bound in the release marker; the release verifier independently re-extracts both from the current MP4 and compares their bytes;
- every human-review template check is explicitly passed and the reviewed video SHA-256 matches the MP4.
- `editable-delivery.json` proves a non-empty reopened ChatCut/OpenChatCut project, exact scene/caption frame mappings, separate narration/BGM/SFX items, current source hashes, and at least three composed-frame checks.
- `human-review.json.editableDeliverySha256` binds subjective editor inspection to the same editable ledger that final QA validates; changing the editor ledger requires a new human review.
- `scripts/verify_release.py` reruns strict editable-delivery validation, including readback and nested evidence hashes; changing a referenced source, readback record, or composed frame invalidates publication even when `editable-delivery.json` itself is unchanged.
- final release requires `case.version >= 3`, reruns approved-case plus full manifest validation, and reopens the hash-bound voice preview, preview report, and approval package;
- `editor-plan.json` remains `planned-not-executed` and never substitutes for editor execution evidence; release binds its hash and rejects it unless a fresh deterministic `build_editor_plan(project)` replay is byte-for-byte equivalent as JSON;
- every fixed or recorded project input path is normalized, project-relative, contained by the resolved project root, and free of symlink components.

An audio/video stream duration match does not prove caption synchronization when captions are burned into video frames. Treat provider-timing provenance and artifact hashes as a separate required gate.

Local SHA-256 chains prove freshness and internal consistency; they are not a cryptographic provider, editor, or human identity attestation. A determined actor can rewrite an entire unsigned ledger. Keep the real provider response metadata, perform editor readback live, and retain named human review evidence. Prefer signed receipts or online revalidation when a provider/editor offers them, but never claim that an unsigned local fixture proves an external call.

## Required human QA

Review the actual MP4 and record `renders/qa/human-review.json` with `passed: true` only after checking:

- no blank or frozen unintended frames;
- no cover distortion or unreadable carousel titles;
- the opening cover flash has the intended pace and every flashed title is capturable at a glance;
- opening narration is auditioned across the hold boundary with no duplicated, clipped, or split syllable;
- narration pace sounds intentional at normal playback speed rather than merely passing duration checks;
- captions are visible, synchronized, and outside commerce UI zones;
- scene changes occur on meaningful narration boundaries;
- generated images make semantic and spatial sense;
- BGM, SFX, and narration balance is acceptable;
- the editor timeline remains composed from independent source items and its opening, middle, and ending match the reviewed MP4;
- the CTA and claims do not overpromise.
