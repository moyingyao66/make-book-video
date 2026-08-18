# Book-video production workflow

Use this reference as the default creative and technical sequence. Keep the order unless the user approves a `custom` profile. Technical validators enforce structure; editorial, listening, and visual decisions still require human judgment.

## Contents

- Default film grammar
- Publication poster and real-cover roles
- Narration provenance
- Book-aware style selection
- Voice and audio generation
- Visual sourcing and scene construction
- Reference render and editable assembly
- Review and repair loop

## Default film grammar

| Order | Beat | Default picture | Audio | Gate |
|---:|---|---|---|---|
| 1 | `fixed-opening` | A vertical clip with obvious real motion and preferably no recognizable face when `pexels-video` was selected; otherwise an approved generated still with subtle deterministic motion | Say exactly `今天分享的是。` | Motion/source compliance and first-frame review |
| 2 | `anticipation-carousel` | Five attributable real covers, about nine frames each at 30 fps | Silence; do not split speech across this hold | Phone-size title recognition and exact 45-frame allocation |
| 3 | `book-reveal` | Primary real cover, fully visible, over an optional designed background | Speak the primary author and `《书名》` as one complete unit | Edition, author, title, aspect ratio, and legibility review |
| 4 | `audience-problem` | One observable situation the viewer recognizes | Begin the approved body narration | Semantic match to that segment |
| 5 | `alternative-explanation` | A distinct scene that makes the book's thesis visible | Explain one main thesis | Claim mapping and semantic review |
| 6 | `concrete-example` | One or two visible examples, not a generic reading scene | Develop the same thesis | Evidence boundary and continuity review |
| 7 | `practical-boundary` | A usable pause, question, signal, or next action | Avoid guarantees | Claim and commerce-safety review |
| 8 | `audience-close` | Return visually to the viewer's original situation | State what this reader can take away | No slogan-only or hard-sell ending |

The opening must feel like video, not a static poster held on screen. The fast flash creates anticipation and stays silent. The primary book reveal resolves that anticipation before the body begins. Do not paste an article into one long scene; split the five conceptual body beats into 12–18 narration-first shots, normally 3–6 seconds each, so every image or clip remains independently replaceable.

## Publication poster and real-cover roles

Create three separate assets; never confuse them:

1. **Publication poster/thumbnail:** a 9:16 promotional image used by the hosted page or publishing surface. By default its only text is `《书名》` and `作者`. Do not add narrator names, `谁谁的`, explanatory subtitles, slogans, or CTA copy unless the user explicitly asks.
2. **Carousel covers:** attributable real cover images used in the silent flash.
3. **Primary reveal cover:** the exact attributable edition shown when author and title are spoken.

For the publication poster:

- Make the title the dominant visual anchor and the author clearly secondary. Start around 90–120 px for a one- or two-line title on a 1080x1920 canvas and 34–48 px for the author, then adjust for the actual title length.
- Prefer a strong designed or generated background with deterministic text rendering. Do not ask an image model to draw Chinese title or author typography.
- Keep the title inside a deliberate text block with balanced line breaks, generous side margins, and enough contrast. Large means forceful, not clipped, cramped, or touching an edge.
- Keep text out of platform UI risk zones. Inspect the full-resolution poster and a phone-size preview before approval; verify every character, line break, author name, and safe margin.
- Store the poster separately from the real cover and record its final path in the completion report.

For every real cover, preserve aspect ratio, title, author, publisher marks, and edition identity. Never enlarge a cropped fragment until the title or publisher disappears, and never use a generated imitation as book evidence.

## Narration provenance

Build narration through this explicit chain:

1. Capture exact identity, contents/themes, attributable highlights, and public review clusters through WeRead-first research or a recorded fallback.
2. Separate source claims, reader reactions, and creator interpretation in `case.json`.
3. Choose one target-viewer situation and one thesis that the book can genuinely support.
4. Draft the eight-beat profile from the copywriting contract linked directly by `SKILL.md`; do not concatenate book-source results or copy long passages.
5. Map every substantial sentence to claim IDs, a segment role, one `visualIntent`, and exact caption cards.
6. Read the Chinese aloud; revise written-sounding clauses, unrelated concepts, vague slogans, or unsupported promises.
7. Run draft validation, generate the complete approval package, and obtain approval before paid generation.

Default new copy targets 350–420 non-whitespace Chinese characters and one coherent 80–95 second planning range. Provider audio, not character count, determines final duration. Preserve a user-approved script unless the user asks for rewriting.

## Book-aware style selection

Choose visual style after the narration and semantic storyboard, before batch image generation:

1. Classify the book by its dominant promise and emotional temperature.
2. Read the style-profile matrix linked directly by `SKILL.md` and select three plausible candidates.
3. Obtain copy/storyboard approval and explicit authorization for the three preview generations, then make the same representative body shot in all three profiles. Keep it simple, caption-safe, free of generated text, and without a recognizable face by default.
4. Compare the previews at phone size and ask the user to choose one.
5. Persist the candidate IDs, rationales, preview paths, chosen style, face policy, and composition principles under `case.visualStyleProfile`.
6. Build the final package and obtain authorization for full TTS and batch visuals. Bind the selection into the approval receipt. Any later style or face-policy change reopens approval and downstream visual review.

The default candidate set is minimal editorial collage, symbolic minimal illustration, and one profile selected for the book category. Do not claim that one style is universally popular or force a trend onto the book.

## Voice and audio generation

1. Run `moying-doubao-config status --require-ready` before any credential or login action.
2. Generate a short preview with the same resource ID, speaker, speech rate, and subtitle setting planned for the full narration.
3. Play the preview and obtain listening approval; connectivity alone does not approve the voice.
4. Bind the approved preview, package, voice configuration, case, and manifest with `record_approval.py`.
5. Generate the complete approved narration in exactly one Doubao Seed TTS 2.0 V3 request with subtitles enabled.
6. Treat provider words and the decoded WAV duration as timing truth. Insert the silent carousel hold only at verified PCM silence; shift later timestamps without stretching speech.
7. Put narration, optional BGM, and each SFX on separate tracks. Keep BGM below speech, use fades, and audition opening, body, and ending for intelligibility and abrupt boundaries.

Never regenerate full TTS merely to repair visuals. Use `--render-only` for local visual or mix changes, and use `--force-tts` only after an intentional paid-regeneration decision.

## Visual sourcing and scene construction

- Source or generate one distinct asset for every narrated body shot according to the confirmed `visualSourcePolicy` and approved `visualStyleProfile`.
- Derive the search/generation prompt from the segment's subject, action, setting, emotion, and `visualIntent`; do not reuse a generic reading clip for different meanings.
- Prefer objects, environments, hands, backs, silhouettes, diagrams, and paper or editorial collage. Avoid recognizable faces by default and keep every composition to one main semantic anchor.
- Inspect video at its start, middle, end, and trim boundaries. Inspect generated stills at full resolution for anatomy, spatial logic, accidental text, and the exact narrated action.
- Compose overlays, subtitles, diagrams, and poster typography deterministically. Preserve real covers as ordinary image assets.
- Build a whole-film contact sheet before final approval so repetition, pacing, color continuity, and the opening-to-body transition are visible together.

## Reference render and editable assembly

Use this order:

1. Freeze the approved case, render manifest, full narration, provider timing, aligned scene timeline, caption timeline, and source hashes.
2. Render the deterministic reference MP4 and audio mix from those artifacts.
3. Build `editor-plan.json`; never improvise new timings in the editor adapter.
4. Import original covers, scene media, overlays, captions, narration, BGM, and SFX as independent editable items. Never use the flattened MP4 as primary timeline content.
5. Preserve semantic track roles and provider-derived frame ranges.
6. Reopen the returned project, read back all mappings, and capture composed opening, middle, and ending frames.
7. Compare editor frames with the reference MP4 before release.

## Review and repair loop

For every gate, repeat `create -> validate -> inspect -> repair -> revalidate`:

- **Editorial:** one thesis, natural read-aloud Chinese, evidence mapping, safe claims.
- **Poster:** only approved title/author text, visual impact, no clipping, phone-size readability.
- **Visual:** genuine covers, visible opening motion, silent-flash pace, body-scene semantics, continuity.
- **Audio:** approved voice, complete words, intelligible mix, clean holds and boundaries.
- **Media:** correct streams, full decode, exact duration, current hashes.
- **Editor:** independent items, reopened readback, complete mappings, composed-frame parity.

For revisions, route by changed truth: use `--render-only` and rebuild the editor plan for image, style, poster, BGM, SFX, or mix changes that preserve narration timing; rebuild TTS, provider alignment, scene/caption timing, render, editor plan, and readback when narration or voice timing changes. Never regenerate paid narration just to swap an image.

After any repair, invalidate and rebuild every downstream artifact whose source hash or timing changed. Publish only when the current MP4 and editable project both satisfy their release gates.
