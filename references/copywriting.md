# Chinese book-video copy contract

Use this reference whenever the input is a book title, book page, or notes that need rewriting. Do not use it to rewrite a user-approved script unless the user asks for a rewrite.

## Separate evidence from expression

- A book-source Skill such as `weread-skills` supplies identity, synopsis, chapter themes, popular highlights, and public reader reactions.
- Those results are research evidence, not a finished narration. Never concatenate chapter concepts or review clusters into a script.
- The narration must select one audience situation and one main thesis. Supporting concepts and examples must serve that thesis.
- Keep book claims, reader reactions, and creator interpretation distinguishable in `case.json`.

## Default profile: `cognition-awakening-v1`

Use this profile for a new Chinese recommendation or sales video unless the user approves a different structure. It borrows the proven *functions* of the Cognition Awakening case without copying that book's claims or wording.

1. `intro`: say exactly `今天分享的是。`
2. `anticipation-carousel`: show five different real covers without narration; default to 45 frames, nine per cover.
3. `book-reveal`: after the carousel, say the primary author and `《书名》` as one complete unit.
4. `audience-problem`: let the target viewer recognize one concrete situation, action, thought, or repeated consequence.
5. `alternative-explanation`: use the book to reinterpret that situation. Do not begin with a directory summary or a list of terms.
6. `concrete-example`: develop one or two visible examples that support the same thesis.
7. `practical-boundary`: give one usable pause, question, signal, or next action without promising results.
8. `audience-close`: return to the opening situation and explain what this reader can take away. Avoid abstract slogans and hard selling.

Functional skeleton:

```text
今天分享的是。
[five-cover silent carousel]
作者的《书名》。
你是不是也经历过……（one concrete situation）
这本书提供了另一个解释……（one main thesis）
比如……（one or two visible examples）
所以当……时，先……（one usable action or boundary）
如果你正处在……，这本书最值得带走的是……（return to the viewer）
```

## Default length and rhythm

- Target 260–320 non-whitespace Chinese narration characters, including punctuation. At the current approved Doubao voice and `speechRate: 20`, treat 60–75 seconds as a planning range only; actual provider audio is timing truth. A sales video earns attention in the first ten seconds and loses it after about a minute, so the shorter default is a content decision, not only a cost one; it also buys one less segment of TTS and one less situation to illustrate.
- If the user requests a different duration or approves a script outside the range, update the profile range in `case.json`; do not secretly trim after approval.
- Use short spoken clauses. One sentence should normally carry one idea.
- Prefer second person and observable actions over abstract nouns.
- Keep one main thesis. Use at most two supporting mechanisms or example groups unless the user asks for a longer review.
- Reader objections are optional. Include them only when they materially help the viewer decide whether or how to read the book.

## Anti-patterns

Reject and rewrite a draft when it does any of the following:

- puts a conceptual hook before `今天分享的是。`;
- speaks during the anticipation carousel;
- splits the fixed opening, author, or title across the silent hold;
- summarizes the table of contents or stacks unrelated concepts;
- starts with `这是一本关于……的书` instead of a viewer situation;
- turns public reviews into author claims or quoted lines;
- uses a disclaimer paragraph only to sound rigorous;
- ends with a slogan that does not return to the opening situation;
- relies on the user's chat history or an external local case that this Skill does not reference.

## Pre-approval review

Before showing the draft to the user, record these checks in `case.copyReview.checks`:

- `singleMainThesis`: every body segment supports one thesis;
- `audienceSituationConcrete`: the viewer can picture the opening situation;
- `bookEvidenceMapped`: substantial book claims map to `claims[].id`;
- `examplesServeThesis`: examples explain the thesis rather than add new topics;
- `endingReturnsToAudience`: the close returns to the original viewer situation;
- `readAloudNatural`: the Chinese reads naturally aloud without long written clauses.

These are editorial judgments. Record them honestly; automated validation only proves that the review was completed, not that the copy is subjectively excellent.
