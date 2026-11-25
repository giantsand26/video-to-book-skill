#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
translate.py — 分块翻译视频转写为简体中文 markdown（忠实翻译，不转述）

把「翻译」从 agent 上下文里剥离，直接调 Anthropic API 分块翻译：
块与块互不共享上下文，译文流式追加写文件，从根本上省 token。

用法:
    python3 translate.py <transcript.json|grouped.txt> <输出.md> [model] [base_url]

    transcript.json : faster-whisper 输出（[{"start","end","text"}...]）
    grouped.txt     : group.py 输出（带 [MM:SS] 前缀，时间戳会被剥离）

环境变量:
    ANTHROPIC_API_KEY    必需
    ANTHROPIC_BASE_URL   可选，默认官方 https://api.anthropic.com
    CHUNK_CHARS          可选，单块字符数，默认 2500

示例:
    ANTHROPIC_API_KEY=sk-xxx python3 translate.py transcript.json book.md
    python3 translate.py transcript.json book.md claude-haiku-4-5 https://my-relay.com

特性:
    - 断点续传：中途报错/中断，重跑会从上次完成处继续
    - 自动重试：单块失败先切半再试，仍失败则打印 request_id 并中止
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_BASE_URL = "https://api.anthropic.com"
CHUNK_CHARS = int(os.environ.get("CHUNK_CHARS", "2500"))
MAX_TOKENS = 4096
API_VERSION = "2023-06-01"

SYSTEM_PROMPT = (
    "你是专业的字幕翻译。请将下面的视频语音转写文本逐句忠实翻译成简体中文。\n"
    "要求：\n"
    "- 忠实原文，逐句翻译，不省略、不总结、不改写成第三人称转述\n"
    "- 原文是语音转写，可能缺标点或有错别字，请结合语境补全标点、修正明显错误，但不得增删原意\n"
    "- 修正明显的专名误译（如品牌名、人名），但不得增删原意\n"
    "- 直接输出翻译结果，不要解释、不要加任何说明、不要输出原文"
)


# ---------------------------------------------------------------------------
# 输入读取：把两种格式统一成纯文本
# ---------------------------------------------------------------------------
def load_text(path):
    if path.endswith(".json"):
        segs = json.load(open(path, encoding="utf-8"))
        return "".join(s.get("text", "").strip() for s in segs)
    # grouped.txt：剥离行首的 [MM:SS] 时间戳
    raw = open(path, encoding="utf-8").read()
    return re.sub(r"(?m)^\s*\[\d{1,2}:\d{2}\]\s*", "", raw)


# ---------------------------------------------------------------------------
# 切块：按句子边界切，尽量接近 CHUNK_CHARS 而不切断句子
# ---------------------------------------------------------------------------
def split_chunks(text):
    # 先按句末标点切开成句子
    sentences = re.findall(r".*?[。！？!?]|.+$", text, flags=re.S)
    chunks, cur = [], ""
    for s in sentences:
        if len(cur) + len(s) > CHUNK_CHARS and cur:
            chunks.append(cur)
            cur = s
        else:
            cur += s
    if cur.strip():
        chunks.append(cur)
    return chunks


# ---------------------------------------------------------------------------
# API 调用（urllib 直连，零依赖，支持中转 base_url）
# ---------------------------------------------------------------------------
def call_api(text, model, base_url, api_key):
    endpoint = base_url.rstrip("/") + "/v1/messages"
    payload = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": text}],
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")


# ---------------------------------------------------------------------------
# 带重试的翻译：失败先把块切半，仍失败抛出带 request_id 的错误
# ---------------------------------------------------------------------------
def translate_chunk(text, model, base_url, api_key, depth=0):
    try:
        return call_api(text, model, base_url, api_key)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        rid = ""
        try:
            rid = json.loads(body)["error"].get("request_id", "")
        except Exception:
            pass
        # 块还够切半，且没切太多次 → 切半重试（应对单块过大）
        if len(text) > 400 and depth < 3:
            half = len(text) // 2
            a = translate_chunk(text[:half], model, base_url, api_key, depth + 1)
            b = translate_chunk(text[half:], model, base_url, api_key, depth + 1)
            return a + b
        raise RuntimeError(
            f"翻译失败 HTTP {e.code}: {body} (request_id: {rid})"
        ) from e


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    src, out = sys.argv[1], sys.argv[2]
    model = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_MODEL
    base_url = sys.argv[4] if len(sys.argv) > 4 else os.environ.get(
        "ANTHROPIC_BASE_URL", DEFAULT_BASE_URL
    )
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("缺少 ANTHROPIC_API_KEY 环境变量", file=sys.stderr)
        sys.exit(1)

    text = load_text(src)
    chunks = split_chunks(text)
    total = len(chunks)
    print(f"共 {total} 块，每块约 {CHUNK_CHARS} 字，模型 {model}")

    # 断点续传：从 progress 文件读取已完成块数
    progress_path = out + ".progress"
    done = 0
    if os.path.exists(progress_path):
        done = int(open(progress_path).read().strip() or 0)
        print(f"检测到断点，从第 {done + 1}/{total} 块继续")

    # 流式追加写
    f = open(out, "a", encoding="utf-8")
    try:
        for i in range(done, total):
            chunk = chunks[i]
            print(f"[{i + 1}/{total}] 翻译中…（{len(chunk)} 字）", flush=True)
            translated = translate_chunk(chunk, model, base_url, api_key).strip()
            f.write(translated + "\n\n")
            f.flush()
            # 每完成一块就记录进度，中断可续
            open(progress_path, "w").write(str(i + 1))
    finally:
        f.close()

    os.remove(progress_path)
    print(f"完成，已写入 {out}")


if __name__ == "__main__":
    main()
