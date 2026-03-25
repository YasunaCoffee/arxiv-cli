#!/usr/bin/env python3
"""直近24時間に追加された論文をDiscordに通知する。"""

import os
import sys

import httpx

from arx.db import get_connection

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
LIMIT = int(os.environ.get("NOTIFY_LIMIT", "5"))


def main() -> None:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, authors, url, published
            FROM papers
            WHERE added_at >= datetime('now', '-1 day')
            ORDER BY added_at DESC
            LIMIT ?
            """,
            (LIMIT,),
        ).fetchall()

    if not rows:
        print("新着なし、通知スキップ")
        return

    lines = [f"**📄 arXiv 新着 {len(rows)}件**\n"]
    for r in rows:
        authors_short = r["authors"][:60] + ("..." if len(r["authors"]) > 60 else "")
        lines.append(f"**{r['title']}**")
        lines.append(f"{authors_short}")
        lines.append(f"<{r['url']}>\n")

    content = "\n".join(lines)[:2000]  # Discord上限

    resp = httpx.post(
        WEBHOOK_URL,
        json={"content": content},
        verify=True,
        timeout=10,
    )
    resp.raise_for_status()
    print(f"Discord通知完了: {len(rows)}件")


if __name__ == "__main__":
    main()
