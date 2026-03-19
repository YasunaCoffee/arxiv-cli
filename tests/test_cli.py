"""CLIコマンドのテスト"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from arx.cli import app
from arx.db import get_connection, add_paper, add_tag, update_memo


runner = CliRunner()


@pytest.fixture
def db_conn():
    """テスト用DB接続とパス"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = get_connection(db_path)
        yield conn, db_path
        conn.close()


@pytest.fixture
def patched_conn(db_conn):
    """CLIのDB接続をテスト用DBにパッチする。"""
    conn, db_path = db_conn
    with patch("arx.cli._get_conn", return_value=conn):
        yield conn


def _add_paper(conn, arxiv_id="2303.08774", title="Test Paper"):
    add_paper(
        conn,
        arxiv_id=arxiv_id,
        title=title,
        authors="Alice, Bob",
        abstract="Test abstract about transformers.",
        url=f"https://arxiv.org/abs/{arxiv_id}",
        published="2023-03-15",
    )


class TestAddCommand:
    @patch("arx.cli._get_conn")
    @patch("arx.api.time.sleep")
    @patch("arx.api.httpx.Client")
    def test_add_valid_paper(self, mock_client_class, mock_sleep, mock_get_conn):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = get_connection(db_path)
            mock_get_conn.return_value = conn

            xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2303.08774v2</id>
    <title>GPT-4 Technical Report</title>
    <summary>GPT-4 abstract.</summary>
    <published>2023-03-15T17:00:00Z</published>
    <author><name>OpenAI</name></author>
    <link rel="alternate" type="text/html" href="https://arxiv.org/abs/2303.08774"/>
  </entry>
</feed>"""
            mock_response = MagicMock()
            mock_response.text = xml
            mock_response.raise_for_status = MagicMock()

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get = MagicMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = runner.invoke(app, ["add", "2303.08774"])
            assert result.exit_code == 0
            assert "追加しました" in result.output

    def test_add_invalid_id(self):
        result = runner.invoke(app, ["add", "not-an-arxiv-id"])
        assert result.exit_code == 1


class TestListCommand:
    def test_list_empty(self, patched_conn):
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "論文がありません" in result.output

    def test_list_papers(self, patched_conn):
        _add_paper(patched_conn)
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "2303.08774" in result.output

    def test_list_unread(self, patched_conn):
        _add_paper(patched_conn, "2301.00001")
        _add_paper(patched_conn, "2301.00002")
        from arx.db import mark_read
        mark_read(patched_conn, "2301.00001")

        result = runner.invoke(app, ["list", "--unread"])
        assert result.exit_code == 0
        assert "2301.00002" in result.output
        assert "2301.00001" not in result.output

    def test_list_by_tag(self, patched_conn):
        _add_paper(patched_conn, "2301.00001")
        _add_paper(patched_conn, "2301.00002")
        add_tag(patched_conn, "2301.00001", "rlhf")

        result = runner.invoke(app, ["list", "--tag", "rlhf"])
        assert result.exit_code == 0
        assert "2301.00001" in result.output
        assert "2301.00002" not in result.output


class TestShowCommand:
    def test_show_existing_paper(self, patched_conn):
        _add_paper(patched_conn)
        result = runner.invoke(app, ["show", "2303.08774"])
        assert result.exit_code == 0
        assert "Test Paper" in result.output
        assert "Alice" in result.output

    def test_show_nonexistent_paper(self, patched_conn):
        result = runner.invoke(app, ["show", "9999.99999"])
        assert result.exit_code == 1
        assert "登録されていません" in result.output


class TestMemoCommand:
    def test_show_empty_memo(self, patched_conn):
        _add_paper(patched_conn)
        result = runner.invoke(app, ["memo", "2303.08774"])
        assert result.exit_code == 0
        assert "メモはありません" in result.output

    def test_add_memo(self, patched_conn):
        _add_paper(patched_conn)
        result = runner.invoke(app, ["memo", "2303.08774", "Great paper!"])
        assert result.exit_code == 0
        assert "更新しました" in result.output

    def test_delete_memo_with_yes(self, patched_conn):
        _add_paper(patched_conn)
        update_memo(patched_conn, "2303.08774", "some memo")
        result = runner.invoke(app, ["memo", "2303.08774", "--delete", "--yes"])
        assert result.exit_code == 0
        assert "削除しました" in result.output

    def test_memo_nonexistent_paper(self, patched_conn):
        result = runner.invoke(app, ["memo", "9999.99999", "text"])
        assert result.exit_code == 1


class TestReadCommand:
    def test_mark_read(self, patched_conn):
        _add_paper(patched_conn)
        result = runner.invoke(app, ["read", "2303.08774"])
        assert result.exit_code == 0
        assert "既読にしました" in result.output

    def test_already_read(self, patched_conn):
        _add_paper(patched_conn)
        from arx.db import mark_read
        mark_read(patched_conn, "2303.08774")
        result = runner.invoke(app, ["read", "2303.08774"])
        assert result.exit_code == 0
        assert "既に既読" in result.output


class TestTagCommand:
    def test_add_tags(self, patched_conn):
        _add_paper(patched_conn)
        result = runner.invoke(app, ["tag", "2303.08774", "attention", "transformer"])
        assert result.exit_code == 0
        assert "追加しました" in result.output

    def test_remove_tag_with_yes(self, patched_conn):
        _add_paper(patched_conn)
        add_tag(patched_conn, "2303.08774", "survey")
        result = runner.invoke(app, ["tag", "2303.08774", "--remove", "survey", "--yes"])
        assert result.exit_code == 0
        assert "削除しました" in result.output

    def test_list_all_tags(self, patched_conn):
        _add_paper(patched_conn)
        add_tag(patched_conn, "2303.08774", "survey")
        result = runner.invoke(app, ["tag", "--list"])
        assert result.exit_code == 0
        assert "survey" in result.output

    def test_show_tags_for_paper(self, patched_conn):
        _add_paper(patched_conn)
        add_tag(patched_conn, "2303.08774", "rlhf")
        result = runner.invoke(app, ["tag", "2303.08774"])
        assert result.exit_code == 0
        assert "rlhf" in result.output


class TestSearchCommand:
    def test_search_finds_paper(self, patched_conn):
        _add_paper(patched_conn, "2303.08774", "Attention Is All You Need")
        result = runner.invoke(app, ["search", "Attention"])
        assert result.exit_code == 0
        assert "2303.08774" in result.output

    def test_search_no_results(self, patched_conn):
        _add_paper(patched_conn)
        result = runner.invoke(app, ["search", "xyznonexistent123"])
        assert result.exit_code == 0
        assert "該当する論文がありません" in result.output

    def test_search_in_memo(self, patched_conn):
        _add_paper(patched_conn, "2303.08774")
        update_memo(patched_conn, "2303.08774", "diffusion score matching")
        result = runner.invoke(app, ["search", "diffusion"])
        assert result.exit_code == 0
        assert "2303.08774" in result.output


class TestOpenCommand:
    def test_open_registered_paper(self, patched_conn):
        _add_paper(patched_conn)
        with patch("arx.cli.webbrowser.open") as mock_open:
            result = runner.invoke(app, ["open", "2303.08774"])
            assert result.exit_code == 0
            mock_open.assert_called_once()

    def test_open_unregistered_paper(self, patched_conn):
        with patch("arx.cli.webbrowser.open") as mock_open:
            result = runner.invoke(app, ["open", "2303.08774"])
            assert result.exit_code == 0
            mock_open.assert_called_once_with("https://arxiv.org/abs/2303.08774")


class TestRssCommands:
    def test_rss_add(self, patched_conn):
        result = runner.invoke(app, ["rss", "add", "cs.AI", "https://arxiv.org/rss/cs.AI"])
        assert result.exit_code == 0
        assert "登録しました" in result.output

    def test_rss_add_unsafe_url(self, patched_conn):
        result = runner.invoke(app, ["rss", "add", "cs.AI", "http://arxiv.org/rss/cs.AI"])
        assert result.exit_code == 1

    def test_rss_add_duplicate(self, patched_conn):
        runner.invoke(app, ["rss", "add", "cs.AI", "https://arxiv.org/rss/cs.AI"])
        result = runner.invoke(app, ["rss", "add", "cs.AI", "https://arxiv.org/rss/cs.AI"])
        assert result.exit_code == 0
        assert "既に登録済み" in result.output

    def test_rss_list_empty(self, patched_conn):
        result = runner.invoke(app, ["rss", "list"])
        assert result.exit_code == 0
        assert "登録済みフィードはありません" in result.output

    def test_rss_list(self, patched_conn):
        from arx.db import add_feed
        add_feed(patched_conn, "cs.AI", "https://arxiv.org/rss/cs.AI")
        patched_conn.commit()
        result = runner.invoke(app, ["rss", "list"])
        assert result.exit_code == 0
        assert "cs.AI" in result.output

    @patch("time.sleep")
    @patch("arx.api.httpx.Client")
    def test_rss_fetch_e2e(self, mock_client_class, mock_sleep, patched_conn):
        """フィード登録→fetch→論文追加のE2Eテスト。"""
        from arx.db import add_feed, get_paper
        add_feed(patched_conn, "cs.AI", "https://arxiv.org/rss/cs.AI")
        patched_conn.commit()

        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>cs.AI</title>
<item>
  <title>Test Paper From RSS</title>
  <link>https://arxiv.org/abs/2401.00001</link>
  <description>An RSS paper abstract.</description>
</item>
</channel></rss>"""

        mock_response = MagicMock()
        mock_response.text = rss_xml
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["rss", "fetch"])
        assert result.exit_code == 0
        assert "1件追加" in result.output

        paper = get_paper(patched_conn, "2401.00001")
        assert paper is not None
        assert paper["title"] == "Test Paper From RSS"


class TestVersionCommand:
    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "arx" in result.output


class TestUrlParsing:
    def test_add_with_url(self, patched_conn):
        """URLから論文IDが正しく抽出される（APIモック）"""
        from arx.utils import extract_arxiv_id
        arxiv_id = extract_arxiv_id("https://arxiv.org/abs/2303.08774")
        assert arxiv_id == "2303.08774"

    def test_add_with_pdf_url(self):
        from arx.utils import extract_arxiv_id
        arxiv_id = extract_arxiv_id("https://arxiv.org/pdf/2303.08774.pdf")
        assert arxiv_id == "2303.08774"

    def test_old_format_id(self):
        from arx.utils import extract_arxiv_id
        assert extract_arxiv_id("hep-th/0001001") == "hep-th/0001001"

    def test_old_format_id_with_subcategory(self):
        from arx.utils import extract_arxiv_id
        assert extract_arxiv_id("math.AG/0601001") == "math.AG/0601001"

    def test_old_format_url(self):
        from arx.utils import extract_arxiv_id
        result = extract_arxiv_id("https://arxiv.org/abs/hep-th/0001001")
        assert result == "hep-th/0001001"

    def test_old_format_with_version(self):
        from arx.utils import extract_arxiv_id
        assert extract_arxiv_id("hep-th/0001001v2") == "hep-th/0001001"

    def test_arxiv_prefix(self):
        from arx.utils import extract_arxiv_id
        assert extract_arxiv_id("arxiv:2303.08774") == "2303.08774"
