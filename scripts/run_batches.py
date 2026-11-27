#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_batches.py — 串行执行 batch_text.py 生成的批请求（防限流）。

逐批读取 pending.json 列出的 request，串行调用模型 API（绝不并发），
每批之间 sleep 冷却，失败指数退避；写 result.json 并 accept，循环直到全部接受。

用法:
    python3 run_batches.py <workdir> [--sleep 4] [--max-retry 5] [--glossary FILE]

依赖环境变量（与 translate.py 一致）:
    ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN(或 API_KEY) / ANTHROPIC_DEFAULT_HAIKU_MODEL

为什么必须串行：并发会触发限流 → 整批重发 → token 膨胀数倍。
串行 + 冷却从根上避开限流，是省 token 的关键。
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

socket.setdefaulttimeout(120)

BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/")
MODEL = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL") or os.environ.get("ANTHROPIC_MODEL")
AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN")
API_KEY = os.environ.get("ANTHROPIC_API_KEY")
BATCH_TEXT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "batch_text.py")


def auth_headers():
    if AUTH_TOKEN:
        return {"Authorization": f"Bearer {AUTH_TOKEN}"}
    if API_KEY:
        return {"x-api-key": API_KEY}
    raise RuntimeError("缺少 ANTHROPIC_AUTH_TOKEN 或 ANTHROPIC_API_KEY")


def call_api(system, user):
    endpoint = BASE_URL + "/v1/messages"
    payload = {"model": MODEL, "max_tokens": 8192, "system": system,
               "messages": [{"role": "user", "content": user}]}
    headers = {"anthropic-version": "2023-06-01", "content-type": "application/json"}
    headers.update(auth_headers())
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")


def extract_json(text):
    m = re.search(r"\[.*\]", text, flags=re.S)
    return json.loads(m.group(0) if m else text)


def process_request(reqfile, glossary):
    """处理单个 request 文件，返回 [{id, timestamp, text}]。"""
    req = json.load(open(reqfile, encoding="utf-8"))
    records = req["records"]
    system = ("你是专业的视频语音转写校对/翻译，负责忠实处理文本。\n"
              + req["instruction"] + "\n"
              + "术语表（专名 ASR 误识对照，按此修正）：\n" + glossary + "\n"
              + "注意：保留口语语气和第一人称，不书面化改写；数字、百分比、时间保持原值；"
                "只输出 JSON 数组，不要任何解释。")
    lines = [f"id={r['id']} timestamp={r['timestamp']}\n原文：{r['text']}" for r in records]
    user = "\n\n".join(lines)
    return extract_json(call_api(system, user))


def run_pending(work, glossary, sleep_sec, max_retry):
    """循环：读 pending → 串行处理 → accept → 直到 pending 空。"""
    work = os.path.abspath(work)  # 统一绝对路径，避免 subprocess 相对 cwd 失配
    total_done = 0
    while True:
        pending_path = os.path.join(work, "pending.json")
        if not os.path.exists(pending_path):
            # 首次 prepare 尚未生成，或全部完成
            state = json.load(open(os.path.join(work, "state.json"), encoding="utf-8"))
            done = len(state.get("done", {}))
            total = len(state.get("source", []))
            if done >= total:
                print(f"全部完成：{done}/{total} 段", flush=True)
                return
            raise RuntimeError("pending.json 缺失但仍有未完成段，请先执行 prepare")
        pending = json.load(open(pending_path, encoding="utf-8"))
        if not pending:
            print(f"全部完成，共 {total_done} 段新接受", flush=True)
            return

        results = []
        failed = []
        for i, name in enumerate(pending, 1):
            reqfile = os.path.join(work, name)
            print(f"[{i}/{len(pending)}] {name}", flush=True)
            ok = False
            backoff = sleep_sec
            for attempt in range(1, max_retry + 1):
                try:
                    arr = process_request(reqfile, glossary)
                    if isinstance(arr, list) and arr:
                        results.extend(arr)
                        ok = True
                        break
                    raise ValueError("返回不是非空数组")
                except Exception as e:
                    print(f"  重试 {attempt}/{max_retry}: {str(e)[:90]}", flush=True)
                    if attempt < max_retry:
                        time.sleep(backoff)
                        backoff = min(backoff * 2, 60)  # 指数退避，封顶 60s
            if not ok:
                failed.append(name)
            else:
                time.sleep(sleep_sec)  # 每批之间冷却，防限流

        # 写 result.json 并 accept（result 用绝对路径，accept 按传入路径读取）
        result_path = os.path.join(work, "result.json")
        json.dump(results, open(result_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        subprocess.run([sys.executable, BATCH_TEXT, "accept", work, result_path], check=False)
        total_done += len(results)
        if failed:
            print(f"本轮流失败 {len(failed)} 批（下轮只补这些缺失段）: {failed}", flush=True)
        # accept 会重新生成仅含未完成记录的 pending.json，循环继续


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", help="batch_text.py prepare 生成的工作目录")
    p.add_argument("--sleep", type=int, default=4, help="每批之间冷却秒数（默认 4）")
    p.add_argument("--max-retry", type=int, default=5, help="单批最大重试次数（默认 5）")
    p.add_argument("--glossary", type=str, default="", help="术语表文件路径（可选）")
    args = p.parse_args()
    glossary = open(args.glossary, encoding="utf-8").read() if args.glossary else ""
    run_pending(args.work, glossary, args.sleep, args.max_retry)


if __name__ == "__main__":
    main()
