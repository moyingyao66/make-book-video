# Visual sourcing contract

Do not confuse a video cover with book evidence. The video cover may use a designed background and deterministic title/author typography; the carousel and reveal must use attributable real cover images. Follow the full role and phone-review rules in the production workflow linked from `SKILL.md`.

## Narration-first visual direction

Treat the approved narration and semantic storyboard as the visual brief. The picture supports the sales argument; it must not introduce a second thesis or compensate for weak copy with spectacle.

After the copy is complete, read the style-profile reference linked directly by `SKILL.md`. Classify the book, prepare exactly three style candidates with the same representative shot, and obtain a style choice before batch generation. Persist the candidates and selection under `case.visualStyleProfile`; the approval hash must change when the style or face policy changes.

Use simple compositions by default: one narrative job, one dominant subject/action/object/metaphor, no more than two primary subjects, and a quiet caption-safe area. Generated text is prohibited. Prefer editorial collage, symbolic illustration, still life, diagrams, environments, hands, backs, over-shoulder framing, and silhouettes.

Default to avoiding recognizable human faces across generated and stock media. A visible face needs a recorded semantic reason and explicit approval. Do not use a close-up synthetic face merely to represent emotion; it is usually both less editable and more visibly artificial.

## Real book identity

Use the real main cover as an ordinary image asset. Preserve its aspect ratio, title, author, and publisher marks. Place it over a separate generated or designed background when a reveal needs more visual depth.

For an opening cover carousel:

- use five real covers by default, or fewer only after phone-size readability review;
- choose recognizably different titles;
- keep every cover small enough for the whole title area to fit on screen;
- allow enough frames for recognition at phone size;
- record each source page and checksum;
- do not let an image model redraw cover typography.

## How many visuals

`case.visualSourcePolicy.visualPlan` fixes the count before any sourcing starts: `bodyVisualCount` shared visuals across the five narrated body roles (default 3, split in narrative order), and `carouselCovers` real covers in the carousel (default 5, nine frames each inside the 45-frame hold). Each group records its `assetId`, the shared `path`, its `segments`, and one `visualIntent` covering all of them.

One image per segment is more sourcing, reviewing, regeneration, and cost than a one-minute video needs, and every extra generated asset is another thing that can drift from the house style. The carousel is the exception and stays at five: those covers are real, `weread-skills` already returns them, and collecting one more costs almost nothing. Judge a shared asset against every segment in its own group; the group boundary is where a change of situation belongs. Raise the count only when the user asks or a group genuinely spans two situations one still cannot carry, and record that decision.

## Startup source policy

Before research or project initialization, collect both choices in one structured selection form:

- opening: `pexels-video` (recommended) or `gpt-image`;
- narrated body: `gpt-image` (recommended) or `pexels-video`.

The choice applies to the fixed narrated opening and the body roles `audience-problem`, `alternative-explanation`, `concrete-example`, `practical-boundary`, and `audience-close`. It does not change the real-cover carousel or true-cover reveal. Save it under `case.visualSourcePolicy`, keep the matching paths in both control files, and never switch providers silently.

## Pexels video route

For a Pexels opening, use an actual moving vertical clip rather than a downloaded preview image. Prefer hands, walking, page turns, spaces, objects, over-shoulder views, and other obvious motion without a recognizable face. For a Pexels body, use a distinct scene-specific clip for every narrated body segment; do not stretch one generic reading clip across multiple meanings.

Search with concrete action, subject, setting, and emotional-state terms derived from the scene's `visualIntent`. Inspect the downloaded file at the beginning, middle, and end, plus any trim boundaries. Complete the scene's `assets/pexels/<scene-id>-source.json` ledger with the query, Pexels page, creator, selected file URL and dimensions, attribution, downloaded path and checksum, and passed frame review.

Pexels is not a research, cover, narration, or text-rendering source. If the user selected Pexels and credentials, network access, licensing evidence, or an acceptable semantic match is unavailable, stop that route and report the precise blocker. A GPT image is not an automatic fallback.

## Frozen house style for generated images

One project uses one style. `case.visualSourcePolicy.visualStyle` freezes it before the first scene is generated:

- `profileId`: the style name recorded in the project (default `paper-minimal-zh-v1`);
- `promptContract`: the full style paragraph, embedded verbatim in every image prompt above that scene's own subject and action;
- `forbidden`: the traits that make an image an automatic reject;
- `captionSafeBottomPx`: the bottom band the composition must leave empty for captions.

The default profile is a portrait 9:16 minimal hand-drawn illustration on warm off-white paper (`#F6F1E8`) with dark grey linework, generous negative space, one low-saturation accent colour, a single clear subject, a clean background, and an empty bottom third. It forbids rendered text of any kind, photographic or 3D realism, dense textures and high-saturation clashes, linework or palette that drifts from the other scenes in the same project, and any subject that intrudes into the caption safe area.

Rendered text is the one non-negotiable reject: an image model cannot spell Chinese reliably, and burned-in characters cannot be repaired downstream. Regenerate instead of retouching.

Changing the style after scenes exist is a user decision, not a fix: either keep the frozen profile or restate it and regenerate every scene already made under the old one, so the series never mixes two looks. The draft validator refuses a `gpt-image` route whose `visualStyle` is missing, unfrozen, or too thin to reproduce.

## GPT image route

Use built-in GPT image generation for every scene assigned to `gpt-image`. An opening generated this way is a static source image, although the renderer may apply a subtle deterministic push-in. Define each image's narrative job, layout, reserved caption area, and visual risks before generation. Review full-resolution images for readable objects, anatomy, spatial logic, accidental text, and continuity.

Do not treat an automated validator as semantic approval, and do not substitute your own inspection for the user's. Present each asset with the narration of the segments it covers, let the user judge whether the image says what the narration says, and record that answer as the semantic review. Reject visually consistent but semantically generic or repetitive images before showing them.
