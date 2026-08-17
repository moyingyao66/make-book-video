# Visual sourcing contract

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

For a Pexels opening, use an actual moving portrait clip rather than a downloaded preview image. For a Pexels body, use a distinct scene-specific clip for every narrated body segment; do not stretch one generic reading clip across multiple meanings.

Search with concrete action, subject, setting, and emotional-state terms derived from the scene's `visualIntent`. Inspect the downloaded file at the beginning, middle, and end, plus any trim boundaries. Complete the scene's `assets/pexels/<scene-id>-source.json` ledger with the query, Pexels page, creator, selected file URL and dimensions, attribution, downloaded path and checksum, and passed frame review.

Pexels is not a research, cover, narration, or text-rendering source. If the user selected Pexels and credentials, network access, licensing evidence, or an acceptable semantic match is unavailable, stop that route and report the precise blocker. A GPT image is not an automatic fallback.

## GPT image route

Use built-in GPT image generation for every scene assigned to `gpt-image`. An opening generated this way is a static source image, although the renderer may apply a subtle deterministic push-in. Define each image's narrative job, layout, reserved caption area, and visual risks before generation. Review full-resolution images for readable objects, anatomy, spatial logic, accidental text, and continuity.

Do not treat an automated validator as semantic approval. Review each generated image beside its exact narration and `visualIntent`; record whether the main subject, action, props, and causal relationship actually express that segment. Reject visually consistent but semantically generic or repetitive images.
