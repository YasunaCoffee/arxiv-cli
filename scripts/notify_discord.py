#!/usr/bin/env python3
"""論文リスト（JSON）をDiscordに通知する。

Usage:
    python scripts/fetch_ai_character.py | python scripts/notify_discord.py
"""

import json
import os
import sys

import httpx

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]


def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        print("入力が空のため通知スキップ")
        return

    papers = json.loads(raw)

    if not papers:
        print("通知対象なし、スキップ")
        return

    lines = [f"**📄 AIキャラクター論文 2025 — {len(papers)}件**\n"]
    for p in papers:
        authors_short = p["authors"][:60] + ("..." if len(p["authors"]) > 60 else "")
        status_mark = "🆕" if p.get("status") == "added" else "📌"
        lines.append(f"{status_mark} **{p['title']}**")
        lines.append(f"{authors_short}")
        lines.append(f"<{p['url']}>\n")

    content = "\n".join(lines)[:2000]  # Discord上限

    resp = httpx.post(
        WEBHOOK_URL,
        json={"content": content},
        verify=True,
        timeout=10,
    )
    resp.raise_for_status()
    print(f"Discord通知完了: {len(papers)}件")


if __name__ == "__main__":
    main()
