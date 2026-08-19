# Stable user-facing outputs

Read this reference when showing the startup choices, the pre-generation approval package, or the final completion report. Use the exact section order so two runs remain comparable.

## Contents

- Startup selection
- Approval package
- Completion report
- Three routing examples

## Startup selection

Use one host-native structured choice control with both questions. `request_user_input`, `AskUserQuestion`, or another host widget may be the adapter, but the persisted method is always `host-structured-choice`; do not persist a tool name. Do not convert the questions to prose or accept typed substitutes. If the current host has no structured choice surface, stop before initialization and report that capability blocker.

```yaml
questions:
  - header: 开场素材
    id: opening_media
    question: 开头前几秒使用哪种素材？
    options:
      - label: Pexels 动态视频 (Recommended)
        description: 使用经检索和逐帧审核的真实竖屏动态视频。
      - label: GPT 静态图片
        description: 使用语义匹配的生成静态图并允许轻微推拉。
  - header: 正文素材
    id: body_media
    question: 书籍内容介绍部分使用哪种素材？
    options:
      - label: GPT 生图 (Recommended)
        description: 为每段旁白生成独立且语义匹配的正文图。
      - label: Pexels 动态视频
        description: 为每段旁白检索并审核独立的真实动态视频。
```

Persist the returned option IDs, not their display labels:

```json
{
  "selectionMethod": "host-structured-choice",
  "openingSource": "pexels-video",
  "bodySource": "gpt-image"
}
```

## Approval package

Before generating the three style previews, run `validate_case.py <project> --stage copy-preview`, show the complete narration and semantic storyboard, and obtain two explicit decisions: approve the copy/storyboard, and authorize exactly three preview generations. This limited preview authorization is not authorization for full TTS or batch visual generation.

Run `scripts/build_approval_package.py <project>`. Present the generated `approval-package.md` without changing its section order:

1. 请确认
2. 项目摘要
3. 视觉风格候选
4. 完整旁白
5. 证据边界
6. 语义分镜

Do not improvise a shorter summary in place of the full narration or hide empty evidence fields. Before approval, regenerate the package whenever its source hashes no longer match `case.json` and `render-manifest.json`. After `record_approval.py` creates the receipt, do not overwrite that package: its raw case hash intentionally refers to the reviewed draft, while the receipt's semantic projection detects any later content change.

The package must include the three visual-style candidates, their representative preview paths, the selected style, and the face policy. Style selection happens here after copy/storyboard work, not in the startup source questions. Use the same representative body scene for all three previews so the user compares style rather than content.

After the user approves the full package and authorizes paid generation, create and play the short Doubao preview using the current `case.voice` values. After listening approval, run:

```bash
python3 scripts/record_approval.py <project> \
  --approved-by "<user or review channel>" \
  --voice-preview audio/voice-preview.wav
```

The adjacent `audio/voice-preview.wav.json` must come from `doubao_tts.py`; the recorder verifies that its audio hash and voice fields match both the WAV and `case.json`.

## Completion report

Return these fields in this order:

```text
状态：完成 / 未完成（原因）
书名：
视频封面：绝对路径；默认文字仅书名和作者
开场素材：pexels-video / gpt-image
正文素材：gpt-image / pexels-video
视觉风格：selectedStyleId；默认 avoid-recognizable-faces
MP4：绝对路径
规格：分辨率、帧率、编码、时长
可编辑工程：编辑器、projectId、timelineId、URL
旁白：provider、speaker、speechRate、provider timestamp source
QA：delivery-ready 路径、video SHA-256、ChatCut 工程校验状态
ChatCut 积分：列出本次实际执行的 Agent、生成或云渲染动作；没有则写“无”
仍需人工判断：没有则写“无”
```

## Three routing examples

### New title-first production

Input: `帮我把《思考，快与慢》做成竖屏视频；交付后我还要自己替换第三段图片继续用。`

Expected behavior: trigger this Skill, show the two startup choices once, initialize a new project, research through WeRead, generate the fixed approval package, and stop before paid generation until approval.

### Existing project repair

Input: `百年孤独这条视频后半段字幕不同步，检查并修好，工程还要能继续剪。`

Expected behavior: trigger this Skill, read the existing confirmed `visualSourcePolicy` instead of asking again, diagnose provider timing and project hashes, repair from source components, and repeat editor plus MP4 QA.

### Boundary case

Input: `把《原则》做成60秒竖屏卖书视频，我只要最终 MP4，不要剪辑工程。`

Expected behavior: do not trigger this Skill; route to `book-sales-video` because the user explicitly excluded the editable-project half of this Skill's contract. Script-, storyboard-, or article-only requests are likewise outside this Skill.

Use the examples reference linked directly by `SKILL.md` for filled startup, approval-package, and fail-closed completion outputs. They illustrate output shape only and are not execution evidence or an evaluation baseline.
