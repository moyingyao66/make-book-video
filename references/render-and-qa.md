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
- duration matches `build_report.json` within tolerance;
- final audio packet hash matches `renders/audio_mix.m4a`;
- TTS report proves exactly one provider request and retains `X-Tt-Logid`;
- text coverage is exactly `1.0` and every caption has non-empty provider word keys;
- timestamped narration, alignment report, scene timeline, caption timeline, and ASS hashes match `build_report.json`;
- `case.json` and `render-manifest.json` hashes match `build_report.json`;
- ASS dialogue count equals the caption ledger count;
- every inserted visual hold uses `boundaryMethod: verified-pcm-silence`, meets its minimum quiet duration, and has a guard-window RMS at or below the recorded threshold;
- whole-film and scene-boundary contact sheets exist.
- every human-review template check is explicitly passed and the reviewed video SHA-256 matches the MP4.

An audio/video stream duration match does not prove caption synchronization when captions are burned into video frames. Treat provider-timing provenance and artifact hashes as a separate required gate.

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
- the CTA and claims do not overpromise.
