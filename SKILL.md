---
name: video-to-book
description: 把视频/链接转成可阅读的文档（markdown + EPUB），存到本机 Downloads，并自动复制到 ~/同步空间macmini/readify待上传/ 文件夹。用于用户发来 YouTube 等视频链接并说「转书」「转成文档」「存为 epub」「转书skill」「video to book」等。流程：判断有无字幕→有字幕直接抓取（优先中文，只有英文则翻译成简体）→无字幕则本地 Whisper 转写→人工校对整理成 markdown→转成 EPUB 存到 ~/Downloads 并复制到 readify待上传/。readify.ai 书架需用户手动登录上传（无法自动化），故用待上传文件夹汇总。
---

# 转书 skill

把视频/链接转成文档（`.md` + `.epub`），存到本机 Downloads。

## 前置环境（若缺失需重建）

- **代理**：YouTube 等需走本地代理 `127.0.0.1:7897`，每条命令前 export：
  `export https_proxy=http://127.0.0.1:7897 http_proxy=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897`
- **yt-dlp**：已装在 `~/.local/bin/yt-dlp`。
- **faster-whisper 虚拟环境**（若 `/tmp/whisper-venv` 被清空则重建，模型缓存在 `~/.cache/huggingface` 一般不用重下）：
  ```
  python3 -m venv /tmp/whisper-venv
  /tmp/whisper-venv/bin/pip install faster-whisper
  ```

## 工作流

1. **判断字幕**：用 baoyu-youtube-transcript 的 `--list`，或 `yt-dlp --list-subs`。同时 `yt-dlp --print "%(title)s ||| %(channel)s ||| %(duration)s秒 ||| %(upload_date)s"` 拿标题/频道/时长/日期。
2. **有字幕**：优先抓 `zh` / `zh-Hans`；只有英文（或 en-US 误判）时抓英文再翻译成简体中文。
3. **无字幕**：下载音频 → 用 `scripts/transcribe.py` 转写。
   - 中文视频：`language="zh"`（脚本默认 zh）。
   - 英文视频：改成 `language="en"` 转写，再翻译成简体中文。
   - 音频下载（yt-dlp）：
     `yt-dlp -f "bestaudio/best" -x --audio-format mp3 --extractor-args "youtube:player_client=web_embedded" --js-runtimes "node:$(command -v node)" -o "audio.%(ext)s" URL`
4. **分组**：`scripts/group.py <transcript.json> <grouped.txt>`，按句末标点 + 字数分段、加 `[MM:SS]` 时间戳。
5. **人工校对整理成 markdown**：修正 ASR 错误，按主题分章节，加 YAML frontmatter（title/channel/date/duration/url/language/transcription-note），正文用 `##` 分节，结尾加版权声明。
6. **转 EPUB**：`python3 scripts/md2epub.py <md路径> <输出.epub>`，输出到 `~/Downloads`。
7. **归档到 readify 待上传文件夹**：`mkdir -p ~/同步空间macmini/readify待上传 && cp "<输出.epub>" ~/同步空间macmini/readify待上传/`，把新生成的 EPUB 复制进去，便于用户一次性拖入 readify.ai 书架。
8. **readify.ai 书架**：提示用户手动登录 `https://app.readifyai.com/library` 上传（需登录，无法自动化）；上传时可整批从 `~/同步空间macmini/readify待上传/` 拖入。

## 脚本（本 skill 的 scripts/ 目录下）

- `transcribe.py <audio.mp3> <transcript.json>` —— faster-whisper small / int8 / beam5 / vad / zh。
- `group.py <transcript.json> <grouped.txt>` —— 分段 + 时间戳。
- `md2epub.py <md路径> <epub路径>` —— 标准 EPUB3（含目录 nav + toc.ncx），按 `##` 分章，`## 视频信息` 表格并入封面页。

## 输出位置

- markdown：vault 的 `youtube-transcript/` 目录。
- EPUB：`/Users/qqm4/Downloads/`（并自动复制一份到 `/Users/qqm4/同步空间macmini/readify待上传/`）。

## 注意

- 中文音频优先直接转写（比"英文字幕再翻译"更准）。
- YouTube 中文翻译/自动字幕接口常 429 限流，无字幕时直接走 Whisper 转写最稳。
- 生成的 EPUB 用「图书」（Apple Books）双击即可打开。
