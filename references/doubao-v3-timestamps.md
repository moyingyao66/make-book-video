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
- Exclude base64 audio payloads and credentials from JSON reports.
- Include timestamp configuration in the cache key. A prior audio-only cache entry must not satisfy a timestamped request.

Do not trim, time-stretch, or resample the raw WAV before applying provider timestamps. Resampling for the final mix is allowed after the timeline has been established because correct resampling preserves duration.

## Text alignment

The provider may omit punctuation or normalize text. Normalize Unicode width, whitespace, and punctuation before comparing. Require full normalized coverage. If numbers, Latin text, or symbols are transformed and exact coverage fails, repair the script or add an explicit reviewed mapping; never silently distribute timing by character count.

## Speech rate

Set `speech_rate` explicitly and record it. For a perceived slow voice, generate short auditions at modest positive values before paying for a full rerender. Use provider-side speech control rather than FFmpeg `atempo` unless the user explicitly requests post-processing.
