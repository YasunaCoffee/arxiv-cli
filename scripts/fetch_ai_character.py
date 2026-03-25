#!/usr/bin/env python3
"""AlphaXiv MCPで2025年のAIキャラクター関連論文を取得してDBに保存する。

Usage:
    python scripts/fetch_ai_character.py   # JSON形式で保存した論文を出力
"""

import asyncio
import json
import re
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from arx.api import fetch_paper
from arx.db import add_paper, get_connection

# AlphaXivのembedding_similarity_searchに渡すクエリ
# 複数の観点を含む2〜3文で書くと精度が上がる（AlphaXivの推奨）
_QUERY = (
    "AI character generation and virtual character synthesis using deep learning. "
    "Methods for generating anime characters, game characters, or digital humans "
    "with controllable appearance, personality, and behavior using generative models."
)

_LIMIT = 5


async def search_alphaxiv(query: str) -> list[str]:
    """AlphaXiv MCPのembedding_similarity_searchを呼び出してarXiv IDリストを返す。"""
    params = StdioServerParameters(
        command="uvx",
        args=["alphaxiv-mcp"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "embedding_similarity_search",
                arguments={"query": query},
            )

    # 結果テキストからarXiv IDを抽出
    text = ""
    for content in result.content:
        if hasattr(content, "text"):
            text += content.text

    # arXiv IDパターン: 2501.12345 形式
    ids = re.findall(r"\b(2[0-9]{3}\.\d{4,5})\b", text)
    # 2025年論文のみ (25xx.xxxxx)
    ids_2025 = [i for i in ids if i.startswith("25")]
    # 重複除去・順序保持
    seen = set()
    unique = []
    for i in ids_2025:
        if i not in seen:
            seen.add(i)
            unique.append(i)
    return unique[:_LIMIT]


def save_papers(arxiv_ids: list[str]) -> list[dict]:
    """arXiv APIで論文メタデータを取得してDBに保存する。保存した論文の情報を返す。"""
    saved = []
    for arxiv_id in arxiv_ids:
        try:
            meta = fetch_paper(arxiv_id)
        except RuntimeError as e:
            print(f"[skip] {arxiv_id}: {e}", file=sys.stderr)
            continue

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

        status = "added" if added else "already_exists"
        saved.append({
            "id": meta.arxiv_id,
            "title": meta.title,
            "authors": meta.authors,
            "url": meta.url,
            "published": meta.published,
            "status": status,
        })
        print(f"[{status}] {meta.arxiv_id}: {meta.title[:60]}", file=sys.stderr)

    return saved


async def main() -> None:
    print("AlphaXiv MCPで検索中...", file=sys.stderr)
    arxiv_ids = await search_alphaxiv(_QUERY)

    if not arxiv_ids:
        print("論文が見つかりませんでした", file=sys.stderr)
        print(json.dumps([]))
        return

    print(f"{len(arxiv_ids)}件取得、DBに保存中...", file=sys.stderr)
    papers = save_papers(arxiv_ids)

    # 結果をJSONで標準出力（notify_discord.pyが受け取る）
    print(json.dumps(papers, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
