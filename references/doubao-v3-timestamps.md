# Doubao V3 narration and timestamp contract

Official references:

- Single-direction HTTP synthesis: https://www.volcengine.com/docs/6561/2528925?lang=zh
- Seed TTS product overview: https://www.volcengine.com/docs/6561/1257543?lang=zh

Use the V3 endpoint:

`POST https://openspeech.bytedance.com/api/v3/tts/unidirectional`

Send `enable_subtitle: true` inside `req_params.audio_params` with Seed TTS 2.0. The response returns timing items under `sentence.words`; current V3 items use `word`, `startTime`, `endTime`, and `confidence`.

Treat `startTime` and `endTime` as seconds and convert them to milliseconds in the saved report. Preserve the original values for auditability.

## Required gates

- Require at least one timing item for non-empty narration.
- Require finite, non-negative, monotonic timestamps with `end >= start`.
- Require the final word to fit within the WAV duration, allowing only a small codec/container tolerance.
- Keep the provider `X-Tt-Logid` in the report for support diagnostics.
- Require `provider: doubao-direct-v3`, HTTP 200 on both the logical request and its sole attempt, and `wordCount` equal to the number of timestamp words assigned to that request.
- Preserve the generated `word-0001`, `word-0002`, ... key sequence exactly. Missing, duplicate, skipped, or reordered keys invalidate the provider ledger and every downstream key reference.
- Exclude base64 audio payloads and credentials from JSON reports.
- Include timestamp configuration in the cache key. A prior audio-only cache entry must not satisfy a timestamped request.

For approved full narration, set `--retries 1`. The workflow requires one actual provider attempt, not merely one logical text chunk; an automatic retry would spend another attempt and then fail the final `providerAttemptCount: 1` gate. Treat the WAV and adjacent report as one pair. The script replaces each file atomically and refuses an incomplete or hash-mismatched cached pair unless `--force` is deliberately supplied for paid regeneration.

Do not trim, time-stretch, or resample the raw WAV before applying provider timestamps. Resampling for the final mix is allowed after the timeline has been established because correct resampling preserves duration.

Final QA does not accept the saved alignment documents on their own. It runs `build_timestamp_timeline.py` again in an isolated directory from canonical `audio/narration.raw.wav`, its adjacent provider report, `case.json`, and the caption style in `render-manifest.json`. It then requires byte-identical final narration PCM and ASS plus deterministic JSON equality for the scene, caption, word, and alignment artifacts after normalizing only the temporary output paths. This replay rejects a replaced raw WAV, shifted words, changed caption or scene frames, or forged downstream hashes.

## Text alignment

The provider may omit punctuation or normalize text. Normalize Unicode width, whitespace, and punctuation before comparing. Require full normalized coverage. If numbers, Latin text, or symbols are transformed and exact coverage fails, repair the script or add an explicit reviewed mapping; never silently distribute timing by character count.

When one provider timing item contains several normalized characters, do not place a scene or caption boundary inside that item. Merge the caption or move the boundary so every visible transition remains on an actual provider item edge.

## Speech rate

Set `speech_rate` explicitly and record it. For a perceived slow voice, generate short auditions at modest positive values before paying for a full rerender. Use provider-side speech control rather than FFmpeg `atempo` unless the user explicitly requests post-processing.

For `zh_male_cixingjieshuonan_uranus_bigtts`, the current tested production starting point is `speech_rate: 20`. This is a workflow default, not a universal quality guarantee; preserve the exact value in the TTS and alignment reports.

## Silent visual holds

Provider word timestamps remain the source of truth for caption and scene alignment, but they are not safe waveform edit points by themselves. A low-confidence timestamp can begin after the phoneme is already audible. When inserting a silent carousel or title beat between narrated segments, search the actual 16-bit PCM gap at `-38 dBFS` in 10 ms windows, require at least 120 ms of quiet audio, choose the center, and verify an 80 ms guard on both sides. Record this evidence in `alignment-report.json` and fail instead of falling back to a timestamp midpoint.
