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

Render only local files. Build scenes from timing JSON; never re-estimate duration from text length.

## Audio

Keep narration intelligible and BGM low. Save the approved final audio mix separately as `renders/audio_mix.m4a`. When muxing, copy its AAC stream if possible so packet-hash verification can prove the final video contains the approved mix.

## Required automated QA

- non-empty playable MP4;
- H.264 video, 1080x1920, 30 fps;
- AAC audio at 48 kHz;
- full FFmpeg decode succeeds;
- duration matches `build_report.json` within tolerance;
- final audio packet hash matches `renders/audio_mix.m4a`;
- whole-film and scene-boundary contact sheets exist.

## Required human QA

Review the actual MP4 and record `renders/qa/human-review.json` with `passed: true` only after checking:

- no blank or frozen unintended frames;
- no cover distortion or unreadable carousel titles;
- captions are visible, synchronized, and outside commerce UI zones;
- scene changes occur on meaningful narration boundaries;
- generated images make semantic and spatial sense;
- BGM, SFX, and narration balance is acceptable;
- the CTA and claims do not overpromise.
