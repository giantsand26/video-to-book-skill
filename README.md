# 转书 skill

把视频/链接转成可阅读的文档（markdown + EPUB），存到本机 Downloads，并自动复制到 readify 待上传文件夹。

## 功能

- 判断有无字幕 → 有字幕直接抓取（优先中文，只有英文则翻译成简体）→ 无字幕则本地 Whisper 转写
- 人工校对整理成 markdown（分章节 + YAML frontmatter）
- 转成标准 EPUB3（含目录 nav + toc.ncx）
- 归档到 `~/同步空间macmini/readify待上传/`，便于拖入 readify.ai 书架

## 目录结构

```
.
├── SKILL.md            # skill 定义与完整工作流
└── scripts/
    ├── transcribe.py   # faster-whisper 转写（small/int8/beam5/vad/zh）
    ├── group.py        # 分段 + [MM:SS] 时间戳
    └── md2epub.py      # markdown → EPUB3
```

## 使用

详见 [SKILL.md](./SKILL.md)。

## 前置依赖

- 本地代理 `127.0.0.1:7897`
- yt-dlp（`~/.local/bin/yt-dlp`）
- faster-whisper 虚拟环境（`/tmp/whisper-venv`）
