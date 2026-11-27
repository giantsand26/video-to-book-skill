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

### 快速、可恢复处理（默认）

- 优先使用与原声一致的人工字幕，其次自动字幕；英文原声字幕再翻译。字幕接口失败后切换一次来源，持续限流就转本地 ASR，避免反复请求。已有音频、原始转写、通过校验的译文必须复用。
- 转写仍可用现有 faster-whisper small/int8。先对短样本测量耗时和质量，再决定模型、beam 或并行度；Apple Silicon 的 faster-whisper CPU 路径不能当作 Metal 加速。不要在同一 CPU 上盲目启动多个重模型。降低模型大小须以样本质量为依据。
- 分组后优先使用 `batch_text.py` 代替旧 `translate.py`。旧脚本会剥离时间戳，其块数断点不验证输入，不能用于要求逐段对应的成品。
- `python3 scripts/batch_text.py prepare grouped.txt work/batches --mode translate [--glossary glossary.txt]`：生成最多12段、目标3000字符的 JSON 请求；单个超长段保留完整，必要时先人工细分源段再创建新的工作目录。
- 只读取 `work/batches/pending.json` 中列出的请求；旧请求文件是历史记录。每个工作单元仅接收该请求的短指令、术语表和记录，不重复加载全篇、skill 或历史。**批请求用 `python3 scripts/run_batches.py work/batches --sleep 4` 串行执行，绝不并发**——并发会触发限流→反复重试→token 膨胀数倍，这是最大的浪费源；缺少 API 时可由当前会话直接处理 JSON。
- 返回 JSON 数组后：`python3 scripts/batch_text.py accept work/batches result.json`。程序按 ID、时间戳和非空正文接受结果并缓存，重新生成仅含未完成记录的请求。串行接受结果，避免同时修改状态文件。连续两次失败的段落交当前会话校订或报告具体阻碍，不无限重试全文。
- `python3 scripts/batch_text.py finish work/batches translated.txt`：缺一段就拒绝生成，全部通过才按原顺序原子写入。输入或术语表变化会拒绝复用旧状态；重新执行相同 prepare 可安全续跑。译文仍须抽查语义，ID 一致不代表没有内容错位。
- 中文先用 `--mode polish` 标出长段缺标点和重复异常，只把这些段交模型；规则不能证明其余段落合格。抽查开头、中间、结尾以及专名密集段。若普遍不通顺，或用户要求全篇校订，使用新工作目录加 `--all`，不能凭标点数量宣布校订完成。禁止按固定字数盲目插入句号、按通用字典替换人名。
- 专名表每个视频维护一次，只记录有上下文证据的名称；保持原始转写，疑似幻觉先核对再删。没有说话人证据不虚构人物标签。
- 完稿后程序检查时间戳、空段、重复与超长无标点段，检查 EPUB ZIP/目录/正文，并比较 Downloads 与同步副本哈希；只修复失败环节。结构检查与语义抽查各做一轮，修复后只复查受影响部分。
- 处理阶段及产物状态落盘；最终回复结束后不能宣称任务仍自动在后台推进。只有实际运行的进程或已配置的自动任务才能报告为后台工作。

### Token 优化（务必遵守，目标省 50%+）

翻译/校订是「输入输出等长」的任务，正文 token 是硬成本省不掉，但流程浪费可省 70%。务必遵守：

- **读全文只一次**：把 `grouped.txt`/转写结果一次性读完进上下文，然后**分多次输出** `layout.json`（先出章节边界，再出说话人映射和 glossary），不重读全文。不要把「章节划分」和「说话人追踪」挤进同一次输出——三种注意力模式混在一次 pass 里易顾此失彼，说话人映射最易降质。之后分节、说话人标注、组装一律用 `layout.json`。
- **校订/翻译用 `run_batches.py` 串行执行，绝不并发**：`python3 scripts/run_batches.py work/batches --sleep 4`。串行 + 每批间冷却从根上避开限流（并发曾把 18 次理想调用膨胀成约 100 次）；脚本内建指数退避与「只补缺失段」循环，不要手动并发或绕过它。
- **失败只补缺失段，不整批重发**：`accept` 后程序自动重新生成「仅含未完成记录」的请求，只处理 `pending.json` 里列出的；连续两次失败的段交当前会话补。指数退避 5s→10s→20s。
- **finish 直接组装成稿**：`finish` 输出后用 `layout.json` 直接拼最终 markdown，不再重读全文、不再单独跑一遍组装。
- **精简输出格式**：模型输出用纯文本 `#id|text` 替代 JSON 对象，省掉 JSON 括号和 timestamp 字段的结构开销。**必须保留 `#id` 锚点**——`accept` 靠 id+timestamp 双校验拒绝错位段，退化成「仅 text 靠顺序对应」会毁掉这道安全网；配套一个轻量解析器。
- **精简 prompt + 按需 glossary**：system prompt 只留硬约束（忠实逐句、保留口吻、不改原意），去掉客套话；glossary 只传本批实际出现的专名，不整张传。
- **中文默认全篇校订（`--all`），不默认只修脏段**：Whisper 中文的逗号切句、缺标点、近音错字普遍存在且规则检测不到，默认直接全篇捋顺。只有抽样（分层：开头/中间/结尾 + 专名密集段 + 低音质段）显示近乎干净时，才跳过全篇。错字聚集分布，10% 小样本极易漏掉重灾区，不能凭标点数量或小样本抽样宣布「干净」。

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
5. **整理成 markdown（忠实翻译，不转述）**：默认使用上面的 `batch_text.py` 处理英文翻译及中文校订，再按下方原则补 frontmatter、可确定的说话人标注、分节和版权声明。下面旧 API 脚本仅供不要求时间戳的兼容流程使用：
   ```
   python3 scripts/translate.py <transcript.json|grouped.txt> <输出.md>
   ```
   旧脚本依赖 `ANTHROPIC_DEFAULT_HAIKU_MODEL` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`；缺少配置时使用默认 JSON 分批流程，不为每批启动带完整上下文的代理。中文仍须完成语义校订及抽查。
6. **转 EPUB**：`python3 scripts/md2epub.py <md路径> <输出.epub>`，输出到 `~/Downloads`。**EPUB 文件必须使用清理后的完整视频标题命名，不能使用 YouTube 视频 ID、序号或 `audio/transcript` 等临时名**；去掉文件系统不支持的字符，将空格和标题中的分隔符统一为短横线，保留足够信息便于在书架中识别。例如：`陈吉宁为何落马.epub`、`用AI学任何想学的东西-4个方法教你一步步做到.epub`。
7. **归档到 readify 待上传文件夹**：`mkdir -p ~/同步空间/readify待上传 && cp "<输出.epub>" ~/同步空间/readify待上传/`，把新生成的 EPUB 复制进去，便于用户一次性拖入 readify.ai 书架。
8. **readify.ai 书架**：提示用户手动登录 `https://app.readifyai.com/library` 上传（需登录，无法自动化）；上传时可整批从 `~/同步空间/readify待上传/` 拖入。

## 翻译与整理原则（务必遵守）

- **忠实原文，逐句翻译，不做第三人称转述或总结**。这是最重要的原则。视频里谁说了什么，就原样保留谁的口吻：
  - 访谈/对话类：保留**一问一答**的对话形式，说话人用 `**Ackman**：` / `> **主持人**：` 等标注，用第一人称（"我"）逐句翻译，**不省略内容、不改写成"他表示/他认为/他谈到"**。
  - 独白/讲解类：保留第一人称叙述原貌，按原文顺序逐段翻译。
- **中文原声部分保留原文**，只做：补标点、改正明显错别字（如"学用福利投资"→"学用复利投资"、"归股"→"硅谷"）、修正 ASR 幻觉（如重复出现的无意义句子直接删除）。不要改动原话的意思和语气。
- **中文 ASR 后处理必须捋顺语句**：不能把 Whisper 的逗号分段直接当成成稿。先按语义重组句子，补全逗号、句号、问号和引号；修正明显的同音/近音识别错误、专名、人名、机构名和数字；删除重复、断裂、无意义的 ASR 片段。对无法确定的专名，结合视频标题、频道、上下文和公开资料核对；不要为了“忠实”保留明显不通顺的机器转写。整理后仍须保持原意、语气和信息顺序，不得擅自总结或改写成第三人称。
- **英文原声部分逐句翻译成简体中文**，翻译时修正明显的 ASR 专名错误（如 "the video"→NVIDIA、"clock release"→Claude 发布、"anthropologists"→Anthropics），但不得增删原意。
- **章节划分**：按主题用 `##` 分节即可，分节不影响原文的忠实呈现；每节内仍是完整的原文对白。
- **frontmatter**：加 title/channel/date/duration/url/language/transcription-note（注明「英文部分逐句翻译、中文部分按原话整理」等），正文用 `##` 分节，结尾加版权声明。

## 脚本（本 skill 的 scripts/ 目录下）

- `batch_text.py prepare|accept|finish` —— 默认处理入口：结构化小批次、逐 ID 缓存、输入变更检测、只补失败段落、完整性检查。无额外依赖和模型调用；`--help` 查看参数。
- `run_batches.py <workdir> [--sleep 4] [--max-retry 5] [--glossary FILE]` —— 串行执行批请求：逐批调 API（绝不并发）、批间冷却、失败指数退避、自动 accept 循环只补缺失段。依赖与 `translate.py` 相同的环境变量。

- `transcribe.py <audio.mp3> <transcript.json> [language]` —— faster-whisper small / int8 / beam5 / vad；第三个参数指定语言，缺省 `zh`（中文带简体断句提示词），传 `en` 等其他语言码则按该语言转写。
- `translate.py <transcript.json|grouped.txt> <输出.md> [model] [base_url]` —— 分块忠实翻译为简体中文（模型/通道自动跟随环境变量，块间不共享上下文、流式写文件、断点续传、失败切半重试、剥离国旗 emoji 规避内容风控），把翻译从 agent 上下文剥离以省 token。读 `ANTHROPIC_AUTH_TOKEN`（或 `ANTHROPIC_API_KEY`）、`ANTHROPIC_DEFAULT_HAIKU_MODEL`、`ANTHROPIC_BASE_URL`；`CHUNK_CHARS` 控制单块字符数。
- `group.py <transcript.json> <grouped.txt>` —— 分段 + 时间戳。
- `md2epub.py <md路径> <epub路径>` —— 标准 EPUB3（含目录 nav + toc.ncx），按 `##` 分章，`## 视频信息` 表格并入封面页。

## 输出位置

- markdown：vault 的 `youtube-transcript/` 目录。
- EPUB：`/Users/nongnong/Downloads/`（并自动复制一份到 `/Users/nongnong/同步空间/readify待上传/`）；两个位置均使用清理后的完整视频标题作为文件名。

## 注意

- **混合语言视频不能用单一 language 转写**——英文音轨用 `zh` 转写会产生大量无意义重复的幻觉文本。务必先按语言切段，再分别转写。
- 中文音频优先直接转写（比"英文字幕再翻译"更准）。
- YouTube 中文翻译/自动字幕接口常 429 限流，无字幕时直接走 Whisper 转写最稳。
- 生成的 EPUB 用「图书」（Apple Books）双击即可打开。
