#!/usr/bin/env python3
"""arXiv APIで2025年のAIキャラクター関連論文を取得してDBに保存する。

Usage:
    python scripts/fetch_ai_character.py   # JSON形式で保存した論文を出力
"""

import asyncio
import json
import sys
import time
import xml.etree.ElementTree as ET

import httpx

from arx.db import add_paper, get_connection
from arx.utils import extract_arxiv_id, is_safe_url

_ARXIV_SEARCH_URL = "https://export.arxiv.org/api/query"
_NS = {"atom": "http://www.w3.org/2005/Atom"}

# AIキャラクター関連の検索クエリ（arXiv API構文）
_QUERIES = [
    'all:"AI character" AND submittedDate:[20250101 TO 20251231]',
    'all:"character generation" AND all:"generative model" AND submittedDate:[20250101 TO 20251231]',
    'all:"anime character" OR all:"virtual character" AND submittedDate:[20250101 TO 20251231]',
]
_LIMIT = 5


def search_arxiv(query: str, max_results: int = 10) -> list[dict]:
    """arXiv APIで論文を検索してメタデータのリストを返す。"""
    params = {
        "search_query": query,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    resp = httpx.get(_ARXIV_SEARCH_URL, params=params, verify=True, timeout=15)
    resp.raise_for_status()
    time.sleep(3)  # arXiv レートリミット遵守

    root = ET.fromstring(resp.text)
    results = []
    for entry in root.findall("atom:entry", _NS):
        # arXiv IDを取得
        id_url = entry.findtext("atom:id", default="", namespaces=_NS)
        arxiv_id = extract_arxiv_id(id_url)
        if not arxiv_id:
            continue

        title = (entry.findtext("atom:title", default="", namespaces=_NS) or "").strip().replace("\n", " ")
        abstract = (entry.findtext("atom:summary", default="", namespaces=_NS) or "").strip()
        published = (entry.findtext("atom:published", default="", namespaces=_NS) or "")[:10]
        authors = ", ".join(
            (a.findtext("atom:name", default="", namespaces=_NS) or "")
            for a in entry.findall("atom:author", _NS)
        )
        url = f"https://arxiv.org/abs/{arxiv_id}"
        for link in entry.findall("atom:link", _NS):
            if link.get("rel") == "alternate":
                href = link.get("href", "")
                if is_safe_url(href):
                    url = href

        results.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "url": url,
            "published": published,
        })
    return results


def fetch_papers() -> list[dict]:
    """複数クエリで検索し、重複除去して上位 _LIMIT 件を返す。"""
    seen = set()
    all_results = []

    for query in _QUERIES:
        try:
            results = search_arxiv(query, max_results=10)
        except Exception as e:
            print(f"[warn] 検索失敗: {e}", file=sys.stderr)
            continue

        for r in results:
            if r["arxiv_id"] not in seen:
                seen.add(r["arxiv_id"])
                all_results.append(r)

        if len(all_results) >= _LIMIT:
            break

    return all_results[:_LIMIT]


def save_papers(papers: list[dict]) -> list[dict]:
    """DBに保存して結果リストを返す。"""
    saved = []
    for p in papers:
        with get_connection() as conn:
            added = add_paper(
                conn,
                p["arxiv_id"],
                p["title"],
                p["authors"],
                p["abstract"],
                p["url"],
                p["published"],
            )
        status = "added" if added else "already_exists"
        saved.append({
            "id": p["arxiv_id"],
            "title": p["title"],
            "authors": p["authors"],
            "url": p["url"],
            "published": p["published"],
            "status": status,
        })
        print(f"[{status}] {p['arxiv_id']}: {p['title'][:60]}", file=sys.stderr)
    return saved


def main() -> None:
    print("arXiv APIで検索中...", file=sys.stderr)
    papers = fetch_papers()

    if not papers:
        print("論文が見つかりませんでした", file=sys.stderr)
        print(json.dumps([]))
        return

    print(f"{len(papers)}件取得、DBに保存中...", file=sys.stderr)
    saved = save_papers(papers)
    print(json.dumps(saved, ensure_ascii=False))


if __name__ == "__main__":
    main()
