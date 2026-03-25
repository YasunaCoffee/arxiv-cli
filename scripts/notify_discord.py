#!/usr/bin/env python3
"""論文リスト（JSON）をGeminiで日本語訳してDiscordに通知する。

Usage:
    python scripts/fetch_ai_character.py > /tmp/papers.json
    python scripts/notify_discord.py < /tmp/papers.json
"""

import json
import os
import sys

import httpx

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent"


def translate_abstract(abstract: str) -> str:
    """Gemini APIでアブストラクトを日本語訳する。失敗時は空文字を返す。"""
    if not GEMINI_API_KEY or not abstract:
        return ""
    try:
        resp = httpx.post(
            _GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": (
                "次の英語のアブストラクトを日本語に翻訳してください。"
                "学術的な文体で200字以内で簡潔にまとめてください。\n\n"
                + abstract
            )}]}]},
            timeout=30,
            verify=True,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"[warn] Gemini翻訳失敗: {e}", file=sys.stderr)
        return ""


def main() -> None:
    if not WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL が未設定のためスキップ")
        return

    raw = sys.stdin.read().strip()
    if not raw:
        print("入力が空のため通知スキップ")
        return

    papers = json.loads(raw)
    if not papers:
        print("通知対象なし、スキップ")
        return

    httpx.post(
        WEBHOOK_URL,
        json={"content": f"**📄 {len(papers)}件の論文**"},
        verify=True,
        timeout=10,
    ).raise_for_status()

    for p in papers:
        authors_short = p["authors"][:80] + ("..." if len(p["authors"]) > 80 else "")
        status_mark = "🆕" if p.get("status") == "added" else "📌"

        ja_abstract = translate_abstract(p.get("abstract", ""))
        abstract_line = f"\n> {ja_abstract}" if ja_abstract else ""

        content = (
            f"{status_mark} **{p['title']}**\n"
            f"{authors_short}\n"
            f"{abstract_line}\n"
            f"<{p['url']}>"
        )
        httpx.post(
            WEBHOOK_URL,
            json={"content": content[:2000]},
            verify=True,
            timeout=10,
        ).raise_for_status()

    print(f"Discord通知完了: {len(papers)}件")


if __name__ == "__main__":
    main()
