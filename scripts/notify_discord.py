#!/usr/bin/env python3
"""論文リスト（JSON）をDiscordに通知する。

Usage:
    python scripts/fetch_ai_character.py | python scripts/notify_discord.py
"""

import json
import os
import sys

import httpx

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


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
        json={"content": f"**📄 AIキャラクター論文 2025 — {len(papers)}件**"},
        verify=True,
        timeout=10,
    ).raise_for_status()

    for p in papers:
        authors_short = p["authors"][:80] + ("..." if len(p["authors"]) > 80 else "")
        status_mark = "🆕" if p.get("status") == "added" else "📌"
        content = f"{status_mark} **{p['title']}**\n{authors_short}\n<{p['url']}>"
        httpx.post(
            WEBHOOK_URL,
            json={"content": content},
            verify=True,
            timeout=10,
        ).raise_for_status()

    print(f"Discord通知完了: {len(papers)}件")


if __name__ == "__main__":
    main()
