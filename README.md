# video-subtitler

这是一个为视频生成精准字幕的 AI Agent Skill。默认产出独立的 SRT 字幕文件和配套文字稿；只有在你明确要求时，才会把字幕烧录进视频。

## 它能做什么

- 细粒度字幕：基于词级时间戳的语音识别重建短字幕条，而不是机械切分粗字幕，时间轴贴合语音。
- 语义断句：在短语边界切分字幕，不在说话人的呼吸停顿处硬切，每条字幕都是完整的语义单元。
- 画面文字校准：自动 OCR 视频中的幻灯片/屏幕文字，用它校准专有名词、英文术语和画面上的数字。屏幕上往往写着语音识别听错的那个词。
- 保守校对：修正识别错误、术语、幻觉内容、简繁混杂，按需清理口水词；不改写、不润色说话人的表达。
- 专有名词复核：交付前强制进行术语审查，并维护一个跨视频复用的术语表。校对过一次的词，下个视频自动用对。
- 质量门禁：交付前运行全量 SRT 校验脚本，零失败才放行。
- 可选进度条：可以为视频加水平动态模块进度条，会先交付 YouTube/Bilibili 章节文件供确认。

## 安装方法

把 `video-subtitler.zip` 下载到本机，然后把这段话直接发给你自己的 AI agent：

```text
请安装附件 video-subtitler.zip。先判断我当前使用的是 OpenClaw、Claude Code、Codex 还是 Hermes；优先按 OpenClaw、Claude Code、Codex、Hermes 的顺序匹配当前环境。根据本机已有 Skill 目录、同步链或 agent 配置完成安装，并在安装后验证 video-subtitler 能被当前环境发现和调用。不要改写 Skill 内容；只有在适配本机外部服务路径或账号能力时，才做必要的本机配置说明。
```

如果想手动安装（以 Claude Code 为例）：

```bash
unzip video-subtitler.zip -d ~/.claude/skills/
ls ~/.claude/skills/video-subtitler/
```

新开一个会话即可生效。

## 使用前准备

- FFmpeg：用于音频抽取、字幕烧录和视频校验（`brew install ffmpeg` 或对应平台的包管理器）。
- 词级时间戳的语音识别能力：本 Skill 要求 ASR 输出词级或短片段时间戳（例如 whisper / faster-whisper 等本地或云端方案均可），由你的 agent 根据本机条件选择。
- 可读取视频帧的 agent 环境：用于幻灯片 OCR 校准（Claude Code 等多模态 agent 自带此能力）。

## 使用方法

安装后直接对 agent 说：

- “给这个视频加字幕”
- “生成字幕版视频”（会先交付 SRT 和文字稿，确认后再烧录）
- “重做字幕同步”
- “给视频加进度条”

## 文件结构

```text
video-subtitler/
├── SKILL.md              # 主配置与核心规则
├── references/
│   └── workflow.md       # 端到端工作流程
├── agents/
│   └── openai.yaml
└── scripts/
    ├── validate_srt.py   # SRT 全量校验门禁
    ├── glossary.py       # 跨视频术语表
    ├── chapters.py       # 章节文件生成
    └── diff_srt.py       # 字幕版本对比
```
