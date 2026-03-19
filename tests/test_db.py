"""DBモジュールのテスト"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from arx.db import (
    get_connection,
    migrate,
    add_paper,
    get_paper,
    list_papers,
    update_memo,
    mark_read,
    add_tag,
    remove_tag,
    list_tags,
    search_papers,
    add_feed,
    list_feeds,
    update_feed_fetched,
)


@pytest.fixture
def conn():
    """テスト用DBへの接続を返す。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        c = get_connection(db_path)
        yield c
        c.close()


def _add_test_paper(conn, arxiv_id="2303.08774", title="Test Paper"):
    result = add_paper(
        conn,
        arxiv_id=arxiv_id,
        title=title,
        authors="Alice, Bob",
        abstract="This is a test abstract.",
        url=f"https://arxiv.org/abs/{arxiv_id}",
        published="2023-03-15",
    )
    conn.commit()
    return result


class TestAddPaper:
    def test_add_new_paper(self, conn):
        result = _add_test_paper(conn)
        assert result is True

    def test_add_duplicate_paper(self, conn):
        _add_test_paper(conn)
        result = _add_test_paper(conn)
        assert result is False

    def test_paper_is_stored(self, conn):
        _add_test_paper(conn)
        paper = get_paper(conn, "2303.08774")
        assert paper is not None
        assert paper["title"] == "Test Paper"
        assert paper["authors"] == "Alice, Bob"


class TestGetPaper:
    def test_get_existing_paper(self, conn):
        _add_test_paper(conn)
        paper = get_paper(conn, "2303.08774")
        assert paper["id"] == "2303.08774"

    def test_get_nonexistent_paper(self, conn):
        paper = get_paper(conn, "9999.99999")
        assert paper is None

    def test_get_paper_includes_tags(self, conn):
        _add_test_paper(conn)
        add_tag(conn, "2303.08774", "attention")
        add_tag(conn, "2303.08774", "transformer")
        conn.commit()
        paper = get_paper(conn, "2303.08774")
        assert "attention" in paper["tags"]
        assert "transformer" in paper["tags"]


class TestListPapers:
    def test_list_all_papers(self, conn):
        _add_test_paper(conn, "2301.00001", "Paper A")
        _add_test_paper(conn, "2301.00002", "Paper B")
        papers = list_papers(conn)
        assert len(papers) == 2

    def test_list_unread_only(self, conn):
        _add_test_paper(conn, "2301.00001")
        _add_test_paper(conn, "2301.00002")
        mark_read(conn, "2301.00001")
        conn.commit()
        papers = list_papers(conn, unread=True)
        assert len(papers) == 1
        assert papers[0]["id"] == "2301.00002"

    def test_list_by_tag(self, conn):
        _add_test_paper(conn, "2301.00001")
        _add_test_paper(conn, "2301.00002")
        add_tag(conn, "2301.00001", "rlhf")
        conn.commit()
        papers = list_papers(conn, tag="rlhf")
        assert len(papers) == 1
        assert papers[0]["id"] == "2301.00001"

    def test_list_limit(self, conn):
        for i in range(5):
            _add_test_paper(conn, f"2301.0000{i}", f"Paper {i}")
        papers = list_papers(conn, limit=3)
        assert len(papers) == 3

    def test_list_invalid_sort_falls_back(self, conn):
        _add_test_paper(conn)
        papers = list_papers(conn, sort="invalid_sort")
        assert len(papers) == 1


class TestMemo:
    def test_update_memo(self, conn):
        _add_test_paper(conn)
        update_memo(conn, "2303.08774", "This is a memo.")
        conn.commit()
        paper = get_paper(conn, "2303.08774")
        assert paper["memo"] == "This is a memo."

    def test_delete_memo(self, conn):
        _add_test_paper(conn)
        update_memo(conn, "2303.08774", "memo")
        conn.commit()
        update_memo(conn, "2303.08774", "")
        conn.commit()
        paper = get_paper(conn, "2303.08774")
        assert paper["memo"] == ""


class TestRead:
    def test_mark_read(self, conn):
        _add_test_paper(conn)
        paper_before = get_paper(conn, "2303.08774")
        assert paper_before["read_at"] is None

        mark_read(conn, "2303.08774")
        conn.commit()
        paper_after = get_paper(conn, "2303.08774")
        assert paper_after["read_at"] is not None


class TestTags:
    def test_add_tag(self, conn):
        _add_test_paper(conn)
        add_tag(conn, "2303.08774", "survey")
        conn.commit()
        paper = get_paper(conn, "2303.08774")
        assert "survey" in paper["tags"]

    def test_remove_tag(self, conn):
        _add_test_paper(conn)
        add_tag(conn, "2303.08774", "survey")
        conn.commit()
        result = remove_tag(conn, "2303.08774", "survey")
        conn.commit()
        assert result is True
        paper = get_paper(conn, "2303.08774")
        assert not paper["tags"] or "survey" not in paper["tags"]

    def test_remove_nonexistent_tag(self, conn):
        _add_test_paper(conn)
        result = remove_tag(conn, "2303.08774", "nonexistent")
        assert result is False

    def test_list_tags(self, conn):
        _add_test_paper(conn, "2301.00001")
        _add_test_paper(conn, "2301.00002")
        add_tag(conn, "2301.00001", "attention")
        add_tag(conn, "2301.00002", "attention")
        add_tag(conn, "2301.00001", "transformer")
        conn.commit()

        tags = list_tags(conn)
        tag_names = [t["tag"] for t in tags]
        assert "attention" in tag_names
        assert "transformer" in tag_names

        attention = next(t for t in tags if t["tag"] == "attention")
        assert attention["count"] == 2


class TestSearch:
    def test_search_by_title(self, conn):
        _add_test_paper(conn, "2301.00001", "Attention Is All You Need")
        _add_test_paper(conn, "2301.00002", "BERT: Pre-training of Deep Transformers")
        results = search_papers(conn, "Attention")
        assert any(r["id"] == "2301.00001" for r in results)

    def test_search_by_memo(self, conn):
        _add_test_paper(conn, "2301.00001")
        update_memo(conn, "2301.00001", "diffusion score matching")
        conn.commit()
        results = search_papers(conn, "diffusion")
        assert any(r["id"] == "2301.00001" for r in results)

    def test_search_no_results(self, conn):
        _add_test_paper(conn)
        results = search_papers(conn, "xyznonexistent123")
        assert len(results) == 0


class TestRssFeeds:
    def test_add_feed(self, conn):
        result = add_feed(conn, "cs.AI", "https://arxiv.org/rss/cs.AI")
        conn.commit()
        assert result is True

    def test_add_duplicate_feed(self, conn):
        add_feed(conn, "cs.AI", "https://arxiv.org/rss/cs.AI")
        conn.commit()
        result = add_feed(conn, "cs.AI", "https://arxiv.org/rss/cs.AI")
        assert result is False

    def test_list_feeds(self, conn):
        add_feed(conn, "cs.AI", "https://arxiv.org/rss/cs.AI")
        add_feed(conn, "cs.LG", "https://arxiv.org/rss/cs.LG")
        conn.commit()
        feeds = list_feeds(conn)
        assert len(feeds) == 2

    def test_update_feed_fetched(self, conn):
        add_feed(conn, "cs.AI", "https://arxiv.org/rss/cs.AI")
        conn.commit()
        feeds = list_feeds(conn)
        assert feeds[0]["last_fetched"] is None

        update_feed_fetched(conn, feeds[0]["id"])
        conn.commit()
        feeds = list_feeds(conn)
        assert feeds[0]["last_fetched"] is not None


class TestMigration:
    def test_upgrade_v1_to_v3(self):
        """v1からv3へのアップグレードパスが正しく動く。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path), timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")

            # v1だけ適用
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS papers (
                    id          TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    authors     TEXT NOT NULL,
                    abstract    TEXT NOT NULL,
                    url         TEXT NOT NULL,
                    published   TEXT,
                    added_at    TEXT NOT NULL DEFAULT (datetime('now')),
                    read_at     TEXT,
                    memo        TEXT NOT NULL DEFAULT ''
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
                    id UNINDEXED, title, authors, abstract, memo,
                    content='papers', content_rowid='rowid'
                );
            """)
            conn.execute("PRAGMA user_version = 1")
            conn.commit()

            # migrate()でv2→v3が適用されるはず
            migrate(conn)

            version = conn.execute("PRAGMA user_version").fetchone()[0]
            assert version == 3

            # tagsテーブルが存在する
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            assert "tags" in tables
            assert "rss_feeds" in tables

            conn.close()

    def test_upgrade_v2_to_v3(self):
        """v2からv3へのアップグレードパスが正しく動く。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path), timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")

            # v1+v2を手動適用
            conn.executescript("""
                CREATE TABLE papers (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    authors TEXT NOT NULL, abstract TEXT NOT NULL,
                    url TEXT NOT NULL, published TEXT,
                    added_at TEXT NOT NULL DEFAULT (datetime('now')),
                    read_at TEXT, memo TEXT NOT NULL DEFAULT ''
                );
                CREATE VIRTUAL TABLE papers_fts USING fts5(
                    id UNINDEXED, title, authors, abstract, memo,
                    content='papers', content_rowid='rowid'
                );
                CREATE TABLE tags (
                    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
                    tag TEXT NOT NULL, PRIMARY KEY (paper_id, tag)
                );
            """)
            conn.execute("PRAGMA user_version = 2")
            conn.commit()

            migrate(conn)

            version = conn.execute("PRAGMA user_version").fetchone()[0]
            assert version == 3

            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            assert "rss_feeds" in tables

            conn.close()

    def test_already_at_v3_no_error(self):
        """既にv3のDBに対してmigrate()を呼んでもエラーにならない。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = get_connection(db_path)
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            assert version == 3

            # 再度呼んでもエラーにならない
            migrate(conn)
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            assert version == 3
            conn.close()
