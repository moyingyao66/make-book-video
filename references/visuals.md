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

## Startup source policy

Before research or project initialization, collect both choices in one structured selection form:

- opening: `pexels-video` (recommended) or `gpt-image`;
- narrated body: `gpt-image` (recommended) or `pexels-video`.

The choice applies to the fixed narrated opening and the body roles `audience-problem`, `alternative-explanation`, `concrete-example`, `practical-boundary`, and `audience-close`. It does not change the real-cover carousel or true-cover reveal. Save it under `case.visualSourcePolicy`, keep the matching paths in both control files, and never switch providers silently.

## Pexels video route

For a Pexels opening, use an actual moving vertical clip rather than a downloaded preview image. Prefer hands, walking, page turns, spaces, objects, over-shoulder views, and other obvious motion without a recognizable face. For a Pexels body, use a distinct scene-specific clip for every narrated body segment; do not stretch one generic reading clip across multiple meanings.

Search with concrete action, subject, setting, and emotional-state terms derived from the scene's `visualIntent`. Inspect the downloaded file at the beginning, middle, and end, plus any trim boundaries. Complete the scene's `assets/pexels/<scene-id>-source.json` ledger with the query, Pexels page, creator, selected file URL and dimensions, attribution, downloaded path and checksum, and passed frame review.

Pexels is not a research, cover, narration, or text-rendering source. If the user selected Pexels and credentials, network access, licensing evidence, or an acceptable semantic match is unavailable, stop that route and report the precise blocker. A GPT image is not an automatic fallback.

## GPT image route

Use built-in GPT image generation for every scene assigned to `gpt-image`. An opening generated this way is a static source image, although the renderer may apply a subtle deterministic push-in. Define each image's narrative job, layout, reserved caption area, and visual risks before generation. Review full-resolution images for readable objects, anatomy, spatial logic, accidental text, and continuity.

Do not treat an automated validator as semantic approval. Review each generated image beside its exact narration and `visualIntent`; record whether the main subject, action, props, and causal relationship actually express that segment. Reject visually consistent but semantically generic or repetitive images.

Split the default body into 12–18 independently timed segment entries, normally 3–6 seconds each after provider timing. Repeated conceptual roles are allowed when their segment IDs, narration, visual intent, captions, and source asset are distinct. If one shot exceeds six seconds, split at a semantic or caption boundary unless the approved pacing intentionally calls for a longer hold. This makes every body image or clip independently replaceable in ChatCut.
