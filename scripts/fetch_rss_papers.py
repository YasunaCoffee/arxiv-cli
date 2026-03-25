#!/usr/bin/env python3
"""RSSフィードを取得し、新着論文をJSON形式で出力する。

Usage:
    python scripts/fetch_rss_papers.py > /tmp/rss_papers.json
"""

import json
import sys
import time

from arx.api import fetch_rss
from arx.db import add_paper, get_connection, list_feeds, update_feed_fetched


def main() -> None:
    with get_connection() as conn:
        feeds = list_feeds(conn)

    if not feeds:
        print("登録済みフィードなし", file=sys.stderr)
        print(json.dumps([]))
        return

    saved = []
    for i, feed in enumerate(feeds):
        if i > 0:
            time.sleep(3)  # arXiv レートリミット遵守

        print(f"取得中: {feed['name']} ...", file=sys.stderr)
        try:
            papers = fetch_rss(feed["url"])
        except (RuntimeError, ValueError) as e:
            print(f"[skip] {feed['name']}: {e}", file=sys.stderr)
            continue

        for meta in papers:
            with get_connection() as conn:
                added = add_paper(
                    conn,
                    meta.arxiv_id,
                    meta.title,
                    meta.authors,
                    meta.abstract,
                    meta.url,
                    meta.published,
                )
            if added:
                saved.append({
                    "id": meta.arxiv_id,
                    "title": meta.title,
                    "authors": meta.authors,
                    "abstract": meta.abstract,
                    "url": meta.url,
                    "published": meta.published,
                    "status": "added",
                })
                print(f"[added] {meta.arxiv_id}: {meta.title[:60]}", file=sys.stderr)

        with get_connection() as conn:
            update_feed_fetched(conn, feed["id"])

    print(f"合計 {len(saved)}件追加", file=sys.stderr)
    print(json.dumps(saved, ensure_ascii=False))


if __name__ == "__main__":
    main()
