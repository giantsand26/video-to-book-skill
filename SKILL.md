---
name: video-to-book
description: 把视频/链接转成可阅读的文档（markdown + EPUB），存到本机 Downloads，并自动复制到 ~/同步空间/readify待上传/ 文件夹。用于用户发来 YouTube 等视频链接并说「转书」「转成文档」「存为 epub」「转书skill」「video to book」等。流程：判断有无字幕→有字幕直接抓取（优先中文，只有英文则翻译成简体）→无字幕则本地 Whisper 转写→人工校对整理成 markdown→转成 EPUB 存到 ~/Downloads 并复制到 readify待上传/。readify.ai 书架需用户手动登录上传（无法自动化），故用待上传文件夹汇总。
---

# 转书 skill

把视频/链接转成文档（`.md` + `.epub`），存到本机 Downloads。

## 前置环境（若缺失需重建）

- **代理**：YouTube 等需走本地代理 `127.0.0.1:7897`，每条命令前 export：
  `export https_proxy=http://127.0.0.1:7897 http_proxy=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897`
- **yt-dlp**：装在 `/opt/homebrew/bin/yt-dlp`。⚠️ 该 homebrew 版本（2026.10.26）的 n-challenge 求解器与新 YouTube player 不兼容（报 `addOnDisposeCallback is not a function`，只能下到图片），需改用 pip 装的新版（如 `/tmp/ytvenv/bin/yt-dlp`，2026.11.x；若 `/tmp` 被清空则 `python3 -m venv /tmp/ytvenv && /tmp/ytvenv/bin/pip install -U "yt-dlp[default]" yt-dlp-ejs`）。
- **Cookie（避免钥匙串反复弹窗）**：已预导出到 `~/.config/yt-dlp/cookies.txt`，用 `--cookies ~/.config/yt-dlp/cookies.txt` 替代 `--cookies-from-browser chrome`（后者每次都会触发 macOS 钥匙串解锁）。若报「Sign in to confirm you're not a bot」且 cookie 已过期，重导一次：`yt-dlp --cookies-from-browser chrome --cookies ~/.config/yt-dlp/cookies.txt --skip-download --print "%(title)s" <任一URL>`（会弹一次钥匙串，选「始终允许」）。
- **ffmpeg**：用于按语言切分音频段（混合语言视频时），已装在 `/opt/homebrew/bin/ffmpeg`。
- **faster-whisper 虚拟环境**（若 `/tmp/whisper-venv` 被清空则重建，模型缓存在 `~/.cache/huggingface` 一般不用重下）：
  ```
  python3 -m venv /tmp/whisper-venv
  /tmp/whisper-venv/bin/pip install faster-whisper
  ```

## 工作流

1. **判断字幕与元数据**：用 baoyu-youtube-transcript 的 `--list`，或 `yt-dlp --list-subs`。同时 `yt-dlp --print "%(title)s ||| %(channel)s ||| %(duration)s秒 ||| %(upload_date)s"` 拿标题/频道/时长/日期。
2. **有字幕**：优先抓 `zh` / `zh-Hans`；只有英文（或 en-US 误判）时抓英文再翻译成简体中文。
3. **无字幕 → 先判断语言类型**（这一步是关键，很多"访谈/解读类"视频是混合语言）：
   - 观察标题、频道、简介，以及音频前几句，判断是：**纯中文** / **纯英文** / **混合语言**（常见形态：英文访谈/英文原声 + 中文主播点评，或反之）。
   - **纯中文**：`transcribe.py` 用默认 `zh` 直接转写。
   - **纯英文**：`transcribe.py <audio> <out> en` 转写，再逐句翻译成简体中文。
   - **混合语言**：先下载整段音频，用 ffmpeg 按语言切换点切成多段，各段用对应语言分别转写，最后按时间顺序拼接。例如「英文访谈 0:00–14:38 + 中文点评 14:38–结尾」：
     ```
     ffmpeg -y -v error -i audio.mp3 -t 878 -c:a libmp3lame -q:a 4 audio_en.mp3   # 英文段
     ffmpeg -y -v error -ss 878 -i audio.mp3 -c:a libmp3lame -q:a 4 audio_zh.mp3  # 中文段
     /tmp/whisper-venv/bin/python3 scripts/transcribe.py audio_en.mp3 en.json en
     /tmp/whisper-venv/bin/python3 scripts/transcribe.py audio_zh.mp3 zh.json zh
     ```
   - 音频下载（yt-dlp）：
     `yt-dlp -f "bestaudio/best" -x --audio-format mp3 --extractor-args "youtube:player_client=web_embedded" --js-runtimes "node:$(command -v node)" -o "audio.%(ext)s" URL`
4. **分组**（可选，需时间戳时）：`scripts/group.py <transcript.json> <grouped.txt>`，按句末标点 + 字数分段、加 `[MM:SS]` 时间戳。
5. **整理成 markdown（忠实翻译，不转述）**：英文/混合语言部分用 `scripts/translate.py` 分块翻译（把翻译从 agent 上下文剥离、省 token），中文部分保留原文；翻译后再按下方「翻译与整理原则」补 frontmatter、说话人标注、`##` 分节、结尾版权声明：
   ```
   python3 scripts/translate.py <transcript.json|grouped.txt> <输出.md>
   ```
   模型与通道自动跟随 Claude Code 环境变量（`ANTHROPIC_DEFAULT_HAIKU_MODEL` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`），无需手动指定；块与块独立翻译、流式写文件、断点续传；纯中文视频无需翻译，直接对转写结果做轻量清洗即可。
6. **转 EPUB**：`python3 scripts/md2epub.py <md路径> <输出.epub>`，输出到 `~/Downloads`。
7. **归档到 readify 待上传文件夹**：`mkdir -p ~/同步空间/readify待上传 && cp "<输出.epub>" ~/同步空间/readify待上传/`，把新生成的 EPUB 复制进去，便于用户一次性拖入 readify.ai 书架。
8. **readify.ai 书架**：提示用户手动登录 `https://app.readifyai.com/library` 上传（需登录，无法自动化）；上传时可整批从 `~/同步空间/readify待上传/` 拖入。

## 翻译与整理原则（务必遵守）

- **忠实原文，逐句翻译，不做第三人称转述或总结**。这是最重要的原则。视频里谁说了什么，就原样保留谁的口吻：
  - 访谈/对话类：保留**一问一答**的对话形式，说话人用 `**Ackman**：` / `> **主持人**：` 等标注，用第一人称（"我"）逐句翻译，**不省略内容、不改写成"他表示/他认为/他谈到"**。
  - 独白/讲解类：保留第一人称叙述原貌，按原文顺序逐段翻译。
- **中文原声部分保留原文**，只做：补标点、改正明显错别字（如"学用福利投资"→"学用复利投资"、"归股"→"硅谷"）、修正 ASR 幻觉（如重复出现的无意义句子直接删除）。不要改动原话的意思和语气。
- **英文原声部分逐句翻译成简体中文**，翻译时修正明显的 ASR 专名错误（如 "the video"→NVIDIA、"clock release"→Claude 发布、"anthropologists"→Anthropics），但不得增删原意。
- **章节划分**：按主题用 `##` 分节即可，分节不影响原文的忠实呈现；每节内仍是完整的原文对白。
- **frontmatter**：加 title/channel/date/duration/url/language/transcription-note（注明「英文部分逐句翻译、中文部分按原话整理」等），正文用 `##` 分节，结尾加版权声明。

## 脚本（本 skill 的 scripts/ 目录下）

- `transcribe.py <audio.mp3> <transcript.json> [language]` —— faster-whisper small / int8 / beam5 / vad；第三个参数指定语言，缺省 `zh`（中文带简体断句提示词），传 `en` 等其他语言码则按该语言转写。
- `translate.py <transcript.json|grouped.txt> <输出.md> [model] [base_url]` —— 分块忠实翻译为简体中文（模型/通道自动跟随环境变量，块间不共享上下文、流式写文件、断点续传、失败切半重试、剥离国旗 emoji 规避内容风控），把翻译从 agent 上下文剥离以省 token。读 `ANTHROPIC_AUTH_TOKEN`（或 `ANTHROPIC_API_KEY`）、`ANTHROPIC_DEFAULT_HAIKU_MODEL`、`ANTHROPIC_BASE_URL`；`CHUNK_CHARS` 控制单块字符数。
- `group.py <transcript.json> <grouped.txt>` —— 分段 + 时间戳。
- `md2epub.py <md路径> <epub路径>` —— 标准 EPUB3（含目录 nav + toc.ncx），按 `##` 分章，`## 视频信息` 表格并入封面页。

## 输出位置

- markdown：vault 的 `youtube-transcript/` 目录。
- EPUB：`/Users/nongnong/Downloads/`（并自动复制一份到 `/Users/nongnong/同步空间/readify待上传/`）。

## 注意

- **混合语言视频不能用单一 language 转写**——英文音轨用 `zh` 转写会产生大量无意义重复的幻觉文本。务必先按语言切段，再分别转写。
- 中文音频优先直接转写（比"英文字幕再翻译"更准）。
- YouTube 中文翻译/自动字幕接口常 429 限流，无字幕时直接走 Whisper 转写最稳。
- 生成的 EPUB 用「图书」（Apple Books）双击即可打开。
