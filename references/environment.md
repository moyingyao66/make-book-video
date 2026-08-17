# Environment and dependency contract

Read this reference after project initialization and whenever preflight reports a missing dependency. Run checks before the stage that needs them; do not discover a missing service after paid generation starts.

## Local runtime

- Python 3.8 or newer.
- Packages pinned in `requirements.txt`: `requests` and Monterey-compatible `urllib3`.
- `ffmpeg` and `ffprobe` with the ASS filter, `libx264`, and AAC encoder.
- A readable Chinese font for burned subtitles.

On Intel macOS Monterey, prefer `/usr/bin/python3` for lightweight standard-library checks. Use a project virtual environment when `requests` is unavailable. Do not rely on a broken `/usr/local/bin/python3`.

## Skills and tools

- `weread-skills` plus `WEREAD_API_KEY` for uncaptured title-first research.
- Built-in `imagegen` when either selected visual route is `gpt-image`.
- Pexels API access when either route is `pexels-video`.
- Doubao Seed TTS 2.0 V3 credentials, resource ID, and speaker for synthesis.
- A ready local OpenChatCut route or available ChatCut connector before final editable delivery.

The preflight can verify local Skill files and credentials, but it cannot prove that a runtime image-generation tool or editor authentication is usable. Perform those live checks before batch generation or editor assembly. Read `stageStates` and `requiredLiveChecks` as the authoritative handoff fields; `readyByStage: false` with `state: local-present-live-unverified` means “perform the named live check now,” not “reinstall the local dependency.”

Run only the gate needed by the next stage:

```bash
python3 scripts/check_environment.py --project <project> --stage research
python3 scripts/check_environment.py --project <project> --stage visuals
python3 scripts/check_environment.py --project <project> --stage production
python3 scripts/check_environment.py --project <project> --stage editor
```

Use `--stage all` only for a full installation audit. Read `readyByStage`, `stageStates`, and the named checks; do not interpret a successful research gate as production or editor readiness. After a successful first image-generation call, continue the current visual run and preserve the generated asset plus its semantic review as evidence. After a successful editor authentication/write/readback call, continue to the editable-delivery validator; a local-installation check alone is never sufficient.

On machines that provide `moying-doubao-config`, the production gate calls `moying-doubao-config status --require-ready` and exposes only readiness metadata. It does not print or copy the API key. A project voice can override the machine speaker, but the machine route must still be ready.

## Network surfaces

- WeRead endpoints used by `weread-skills`.
- `api.pexels.com` and the selected Pexels video download host.
- Volcengine/Doubao TTS endpoints.
- Localhost OpenChatCut MCP when that route is selected.
- Cloudflare only after the user explicitly requests publication.

## Secret handling

Resolve credentials from the current process or supported macOS Keychain services. Never print the value, put it in command arguments, save it in project JSON/Markdown, or commit it. A successful credential check proves connectivity readiness only; it does not approve a voice, image, stock clip, or editor result.

Interpret preflight outcomes by state:

- `ready`: continue that stage.
- research `degraded` with route state `fallback-required`: attempt WeRead first, then record at least one authoritative HTTP(S) fallback `sourceUrl` plus `reason`; rerun the draft validator. The missing WeRead route is actionable degradation, not permission to invent evidence.
- `local-present-live-unverified`: perform the listed host-tool or editor live check and retain its stage evidence.
- `blocked-local-prerequisite-missing`: stop before that stage and report the exact failed dependency.

Do not silently substitute a different research source, visual provider, voice, or editor. After a blocking dependency is restored, rerun the same stage gate instead of rebuilding earlier approved work. The production gate is independent: a missing editor or unverified imagegen route must not be reported as a Doubao/FFmpeg production failure.
