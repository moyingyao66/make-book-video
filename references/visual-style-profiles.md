# Book-aware visual style profiles

Choose style only after the complete narration and semantic storyboard exist. The copy is the product argument; visuals clarify, pace, and reinforce it. Never choose a fashionable look first and force unrelated narration into it.

## Selection procedure

1. Classify the book by its dominant reading promise, not only its bookstore category.
2. Derive three candidate profiles from the matrix below.
3. Obtain copy/storyboard approval and explicit authorization for three preview generations.
4. Use the same representative body shot, preferably an `alternative-explanation` shot, to make three low-cost previews.
5. Compare semantic accuracy, simplicity, caption space, continuity, and artificial-looking details at phone size.
6. Ask the user to choose one profile before batch generation. Save all three candidates, preview paths, rationale, and the selected ID under `case.visualStyleProfile`.
7. Keep the chosen visual grammar consistent. Change color or texture only when the narration requires a clear state change.

There is no universal “most popular” profile. Current trend signals can inform the candidate list, but book type, narration, and editability decide the final route.

## Stable profile matrix

| Profile ID | Best fit | Visual grammar | Avoid |
|---|---|---|---|
| `minimal-editorial-collage` | social science, cognition, business, history | cut paper, objects, restrained geometric shapes, two or three colors, generous negative space | crowded magazine spreads, decorative fragments with no semantic job |
| `symbolic-minimal-illustration` | psychology, philosophy, self-development | one clear metaphor, simplified faceless figures, silhouettes, objects, quiet gradients | literal talking faces, surreal spectacle that replaces the idea |
| `warm-handmade-illustration` | parenting, healing, memoir, culture | hand-drawn lines, print or paper texture, warm restrained palette, tactile imperfections | glossy 3D characters, exaggerated sentimentality |
| `quiet-publisher-editorial` | classics, essays, literature, finance | still life, architectural space, serif-led poster rhythm, diagrams, strong negative space | stock-photo corporate scenes, decorative quote text inside images |
| `retro-ui-data-visual` | technology, science, management, methods | simple interface fragments, grids, charts, labeled shapes rendered deterministically | fake dashboards, tiny unreadable generated text |
| `atmospheric-faceless-cinematic` | fiction, biography, narrative nonfiction | backs, hands, shadows, objects, locations, shallow depth, controlled film grain | recognizable synthetic faces, unrelated cinematic spectacle |

Default candidate set when evidence does not strongly favor another route:

- `minimal-editorial-collage`;
- `symbolic-minimal-illustration`;
- one category-specific profile from the matrix.

## Face and simplicity policy

Default to `avoid-recognizable-faces` for generated images and stock footage. Prefer hands, over-shoulder framing, backs, silhouettes, objects, rooms, landscapes, diagrams, and paper collage. A visible recognizable face is an exception, not a shortcut; record why the meaning cannot be communicated more simply and who approved the exception.

Each body shot should normally contain:

- one narrative job;
- one dominant subject, action, object, or metaphor;
- no more than two primary subjects;
- a quiet caption-safe area;
- no generated title, quote, UI label, or other text;
- enough separation from adjacent shots to make replacement obvious in the editor.

Reject a candidate when it is attractive but generic, repeats the same pose or action, invents human anatomy, competes with captions, or needs explanation before it matches the narration.
