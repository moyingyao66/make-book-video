# Make Book Video

把一本书从标题、封面、书页、产品页或已确认文案，制作成一条中文竖屏图书推荐视频。

这个 Skill 的交付目标不是只有脚本或预览，而是同时得到：

- 一条经过媒体与人工复核的 MP4 成片；
- 一个可重新打开、可逐项修改的 ChatCut 工程；
- 与当前素材、旁白和时间轴绑定的验证记录。

[![License: MIT](https://img.shields.io/badge/License-MIT-orange.svg)](LICENSE)

## 主要能力

- 从书名、封面、产品页、笔记或已批准文案启动；
- 用可追溯来源核对书籍、版本、作者和真实封面；
- 在 Pexels 动态视频与 GPT 生图等素材路线之间做显式选择；
- 通过旁白、分镜、声音、素材、成片和可剪辑工程六个确认关口；
- 使用同一次完整 TTS 请求返回的词级时间戳安排字幕与镜头；
- 输出 1080×1920、30 fps、H.264/AAC 的默认竖屏成片；
- 保留封面、镜头、字幕、旁白、BGM 与音效为独立可编辑项目；
- 对成片解码、时间轴、素材哈希、编辑器回读和人工确认做闭环检查。

## 安装

将仓库克隆到 Codex Skills 目录：

```bash
git clone https://github.com/moyingyao66/make-book-video.git ~/.codex/skills/make-book-video
```

然后直接在支持 Skills 的会话中调用：

```text
使用 $make-book-video，生成《书名》的图书推荐视频
```

首次使用时，Skill 会自动检查 Python 运行环境、创建独立虚拟环境并安装缺失的固定版本依赖，不需要用户预先执行 Python 或 pip 命令。

完整执行规则、确认关口和命令以 [SKILL.md](SKILL.md) 为准。

## 默认流程

1. 选择开场与正文素材来源；
2. 核对书籍信息，确认旁白和语义分镜；
3. 生成三张风格预览并确定整片视觉风格；
4. 试听配音，生成正式旁白并准备全部素材；
5. 按提供方词级时间戳生成字幕与镜头时间轴；
6. 渲染 MP4，并在 ChatCut 中组装可编辑工程；
7. 完成媒体、画面、编辑器回读与人工复核后交付。

## 使用的工具和库

- **本地运行：**Python 3.8+、独立 `.venv`、`requests 2.32.4`、`urllib3 1.26.20`、FFmpeg、ffprobe；
- **书籍研究：**微信读书 Skill，或有出处的公开网页；
- **素材：**Pexels 动态视频、GPT 图像生成，按启动时的选择使用；
- **配音：**豆包 Seed TTS 2.0 V3；
- **可剪辑工程：**ChatCut。

Skill 会自动准备可自动安装的 Python 环境和库。外部服务可能需要单独的账号、API 权限或付费额度；仓库不会保存这些凭据。

## 第三方素材与内容

MIT 协议适用于本仓库原创代码和文档。书籍封面、文字摘录、库存视频、字体、配音、生成图片以及其他第三方素材仍受各自来源、平台协议和适用法律约束，不因本仓库采用 MIT 协议而自动获得再授权。

## 作者与公众号

作者：**莫影**<br />
微信公众号：**莫影AI**

点击二维码可查看原图，也可以使用微信扫码关注：

<a href="docs/images/moying-ai-wechat.jpg">
  <img src="docs/images/moying-ai-wechat.jpg" alt="微信公众号：莫影AI" width="300" />
</a>

GitHub：[@moyingyao66](https://github.com/moyingyao66)

## 开源协议

[MIT License](LICENSE) © 2026 moyingyao66（莫影AI）
