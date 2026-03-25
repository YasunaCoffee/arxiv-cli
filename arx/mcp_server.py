"""arx MCPサーバー — Claude等のAIエージェントからarxを操作できるようにする。"""

import json

from fastmcp import FastMCP

from arx.db import (
    add_paper,
    add_tag,
    get_connection,
    get_paper,
    list_papers,
    mark_read,
    remove_tag,
    search_papers,
    update_memo,
)
from arx.utils import extract_arxiv_id

mcp = FastMCP("arx")


def _paper_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "authors": row["authors"],
        "abstract": row["abstract"],
        "url": row["url"],
        "published": row["published"],
        "added_at": row["added_at"],
        "read_at": row["read_at"],
        "memo": row["memo"],
        "tags": row["tags"],
    }


@mcp.tool()
def arx_add_paper(arxiv_id: str) -> str:
    """arXiv IDで論文を取得してローカルDBに保存する。

    Args:
        arxiv_id: arXiv ID（例: 2501.12345 または https://arxiv.org/abs/2501.12345）
    """
    normalized = extract_arxiv_id(arxiv_id)
    if not normalized:
        return json.dumps({"error": f"無効なarXiv IDです: {arxiv_id}"})

    from arx.api import fetch_paper

    try:
        meta = fetch_paper(normalized)
    except RuntimeError as e:
        return json.dumps({"error": str(e)})

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
        return json.dumps({"status": "added", "id": meta.arxiv_id, "title": meta.title})
    return json.dumps({"status": "already_exists", "id": meta.arxiv_id, "title": meta.title})


@mcp.tool()
def arx_search(query: str) -> str:
    """ローカルDBをFTS5全文検索する（タイトル・著者・アブスト・メモ対象）。

    Args:
        query: 検索クエリ（FTS5構文に対応）
    """
    with get_connection() as conn:
        results = search_papers(conn, query)
    papers = [_paper_to_dict(r) for r in results]
    return json.dumps({"count": len(papers), "papers": papers}, ensure_ascii=False)


@mcp.tool()
def arx_list(tag: str = "", unread_only: bool = False, limit: int = 50) -> str:
    """保存済み論文一覧を返す。

    Args:
        tag: タグでフィルタ（空文字で全件）
        unread_only: Trueで未読のみ
        limit: 最大件数（デフォルト50）
    """
    with get_connection() as conn:
        results = list_papers(
            conn,
            unread=unread_only,
            tag=tag if tag else None,
            limit=limit,
        )
    papers = [_paper_to_dict(r) for r in results]
    return json.dumps({"count": len(papers), "papers": papers}, ensure_ascii=False)


@mcp.tool()
def arx_get(arxiv_id: str) -> str:
    """論文の詳細（アブスト・メモ・タグ含む）を返す。

    Args:
        arxiv_id: arXiv ID（例: 2501.12345）
    """
    normalized = extract_arxiv_id(arxiv_id)
    if not normalized:
        return json.dumps({"error": f"無効なarXiv IDです: {arxiv_id}"})

    with get_connection() as conn:
        row = get_paper(conn, normalized)

    if row is None:
        return json.dumps({"error": f"論文が見つかりません: {normalized}"})
    return json.dumps(_paper_to_dict(row), ensure_ascii=False)


@mcp.tool()
def arx_add_tag(arxiv_id: str, tag: str) -> str:
    """論文にタグを付ける。

    Args:
        arxiv_id: arXiv ID
        tag: 付けるタグ名
    """
    normalized = extract_arxiv_id(arxiv_id)
    if not normalized:
        return json.dumps({"error": f"無効なarXiv IDです: {arxiv_id}"})

    with get_connection() as conn:
        if get_paper(conn, normalized) is None:
            return json.dumps({"error": f"論文が見つかりません: {normalized}"})
        add_tag(conn, normalized, tag)

    return json.dumps({"status": "ok", "id": normalized, "tag": tag})


@mcp.tool()
def arx_mark_read(arxiv_id: str) -> str:
    """論文を既読にする。

    Args:
        arxiv_id: arXiv ID
    """
    normalized = extract_arxiv_id(arxiv_id)
    if not normalized:
        return json.dumps({"error": f"無効なarXiv IDです: {arxiv_id}"})

    with get_connection() as conn:
        if get_paper(conn, normalized) is None:
            return json.dumps({"error": f"論文が見つかりません: {normalized}"})
        mark_read(conn, normalized)

    return json.dumps({"status": "ok", "id": normalized})


@mcp.tool()
def arx_memo(arxiv_id: str, memo: str) -> str:
    """論文にメモを追加・更新する。

    Args:
        arxiv_id: arXiv ID
        memo: メモ内容（上書き）
    """
    normalized = extract_arxiv_id(arxiv_id)
    if not normalized:
        return json.dumps({"error": f"無効なarXiv IDです: {arxiv_id}"})

    with get_connection() as conn:
        if get_paper(conn, normalized) is None:
            return json.dumps({"error": f"論文が見つかりません: {normalized}"})
        update_memo(conn, normalized, memo)

    return json.dumps({"status": "ok", "id": normalized})


@mcp.tool()
def arx_remove_tag(arxiv_id: str, tag: str) -> str:
    """論文からタグを削除する。

    Args:
        arxiv_id: arXiv ID
        tag: 削除するタグ名
    """
    normalized = extract_arxiv_id(arxiv_id)
    if not normalized:
        return json.dumps({"error": f"無効なarXiv IDです: {arxiv_id}"})

    with get_connection() as conn:
        removed = remove_tag(conn, normalized, tag)

    if removed:
        return json.dumps({"status": "ok", "id": normalized, "tag": tag})
    return json.dumps({"status": "not_found", "id": normalized, "tag": tag})


def serve() -> None:
    """MCPサーバーをstdioで起動する。"""
    mcp.run()
