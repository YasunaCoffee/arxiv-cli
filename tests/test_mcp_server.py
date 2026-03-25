"""MCPサーバーツールのテスト"""

import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# feedparser が環境によってビルド不可のため、import前にモックする
_feedparser_mock = MagicMock()
sys.modules.setdefault("feedparser", _feedparser_mock)
sys.modules.setdefault("sgmllib", MagicMock())

from arx.db import add_paper, get_connection  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """各テストで一時DBを使う。"""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ARX_DB_PATH", str(db_path))
    return db_path


def _add_test_paper(arxiv_id="2303.08774", title="Test Paper"):
    db_path = Path(__file__).parent.parent / "test_tmp.db"  # unused, via env
    with get_connection() as conn:
        add_paper(
            conn,
            arxiv_id,
            title,
            "Alice, Bob",
            "This is a test abstract about AI characters.",
            f"https://arxiv.org/abs/{arxiv_id}",
            "2023-03-15",
        )


class _MockMeta:
    arxiv_id = "2501.99999"
    title = "Mock Paper"
    authors = "Charlie"
    abstract = "Mock abstract."
    url = "https://arxiv.org/abs/2501.99999"
    published = "2025-01-01"


_MOCK_META = _MockMeta()


class TestArxAddPaper:
    def test_add_new_paper(self):
        from arx.mcp_server import arx_add_paper

        with patch("arx.api.fetch_paper", return_value=_MOCK_META):
            result = json.loads(arx_add_paper("2501.99999"))

        assert result["status"] == "added"
        assert result["id"] == "2501.99999"

    def test_add_duplicate(self):
        from arx.mcp_server import arx_add_paper

        with patch("arx.api.fetch_paper", return_value=_MOCK_META):
            arx_add_paper("2501.99999")
            result = json.loads(arx_add_paper("2501.99999"))

        assert result["status"] == "already_exists"

    def test_invalid_id(self):
        from arx.mcp_server import arx_add_paper

        result = json.loads(arx_add_paper("not-an-id"))
        assert "error" in result

    def test_api_error(self):
        from arx.mcp_server import arx_add_paper

        with patch("arx.api.fetch_paper", side_effect=RuntimeError("接続失敗")):
            result = json.loads(arx_add_paper("2501.99999"))

        assert "error" in result
        assert "接続失敗" in result["error"]


class TestArxSearch:
    def test_search_returns_results(self):
        from arx.mcp_server import arx_search

        _add_test_paper()
        result = json.loads(arx_search("AI characters"))

        assert result["count"] >= 1
        assert any(p["id"] == "2303.08774" for p in result["papers"])

    def test_search_no_results(self):
        from arx.mcp_server import arx_search

        result = json.loads(arx_search("zzznomatch"))
        assert result["count"] == 0
        assert result["papers"] == []


class TestArxList:
    def test_list_all(self):
        from arx.mcp_server import arx_list

        _add_test_paper("2303.08774", "Paper A")
        _add_test_paper("2303.08775", "Paper B")
        result = json.loads(arx_list())

        assert result["count"] == 2

    def test_list_empty(self):
        from arx.mcp_server import arx_list

        result = json.loads(arx_list())
        assert result["count"] == 0

    def test_list_with_tag_filter(self):
        from arx.mcp_server import arx_add_tag, arx_list

        _add_test_paper()
        arx_add_tag("2303.08774", "ai-char")
        result = json.loads(arx_list(tag="ai-char"))

        assert result["count"] == 1
        assert result["papers"][0]["id"] == "2303.08774"


class TestArxGet:
    def test_get_existing(self):
        from arx.mcp_server import arx_get

        _add_test_paper()
        result = json.loads(arx_get("2303.08774"))

        assert result["id"] == "2303.08774"
        assert result["title"] == "Test Paper"

    def test_get_not_found(self):
        from arx.mcp_server import arx_get

        result = json.loads(arx_get("9999.99999"))
        assert "error" in result

    def test_get_invalid_id(self):
        from arx.mcp_server import arx_get

        result = json.loads(arx_get("not-valid"))
        assert "error" in result


class TestArxAddTag:
    def test_add_tag(self):
        from arx.mcp_server import arx_add_tag

        _add_test_paper()
        result = json.loads(arx_add_tag("2303.08774", "deep-learning"))

        assert result["status"] == "ok"
        assert result["tag"] == "deep-learning"

    def test_add_tag_not_found(self):
        from arx.mcp_server import arx_add_tag

        result = json.loads(arx_add_tag("9999.99999", "tag"))
        assert "error" in result


class TestArxMarkRead:
    def test_mark_read(self):
        from arx.mcp_server import arx_get, arx_mark_read

        _add_test_paper()
        result = json.loads(arx_mark_read("2303.08774"))
        assert result["status"] == "ok"

        paper = json.loads(arx_get("2303.08774"))
        assert paper["read_at"] is not None

    def test_mark_read_not_found(self):
        from arx.mcp_server import arx_mark_read

        result = json.loads(arx_mark_read("9999.99999"))
        assert "error" in result


class TestArxMemo:
    def test_update_memo(self):
        from arx.mcp_server import arx_get, arx_memo

        _add_test_paper()
        result = json.loads(arx_memo("2303.08774", "重要な論文"))
        assert result["status"] == "ok"

        paper = json.loads(arx_get("2303.08774"))
        assert paper["memo"] == "重要な論文"

    def test_memo_not_found(self):
        from arx.mcp_server import arx_memo

        result = json.loads(arx_memo("9999.99999", "memo"))
        assert "error" in result


class TestArxRemoveTag:
    def test_remove_tag(self):
        from arx.mcp_server import arx_add_tag, arx_remove_tag

        _add_test_paper()
        arx_add_tag("2303.08774", "to-remove")
        result = json.loads(arx_remove_tag("2303.08774", "to-remove"))

        assert result["status"] == "ok"

    def test_remove_nonexistent_tag(self):
        from arx.mcp_server import arx_remove_tag

        _add_test_paper()
        result = json.loads(arx_remove_tag("2303.08774", "nonexistent"))
        assert result["status"] == "not_found"
