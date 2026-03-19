"""DB接続・マイグレーション管理"""

import os
import sqlite3
from pathlib import Path


def get_db_path() -> Path:
    """DBファイルのパスを返す。"""
    return Path.home() / ".arx" / "papers.db"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """SQLite接続を返す。WALモード・タイムアウト設定済み。"""
    if db_path is None:
        db_path = get_db_path()

    db_dir = db_path.parent
    db_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(db_dir, 0o700)

    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row

    if not db_path.exists() or db_path.stat().st_size == 0:
        pass  # chmod will be set after first write

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    migrate(conn)

    # DBファイルのパーミッション設定
    if db_path.exists():
        os.chmod(db_path, 0o600)

    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """スキーママイグレーションをPRAGMA user_versionで管理する。"""
    version = conn.execute("PRAGMA user_version").fetchone()[0]

    if version < 1:
        _migrate_v1(conn)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()

    if version < 2:
        _migrate_v2(conn)
        conn.execute("PRAGMA user_version = 2")
        conn.commit()

    if version < 3:
        _migrate_v3(conn)
        conn.execute("PRAGMA user_version = 3")
        conn.commit()


def _migrate_v1(conn: sqlite3.Connection) -> None:
    """Phase 1: papersテーブルとFTS5仮想テーブルを作成する。"""
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
            id UNINDEXED,
            title,
            authors,
            abstract,
            memo,
            content='papers',
            content_rowid='rowid'
        );

        CREATE TRIGGER IF NOT EXISTS papers_ai AFTER INSERT ON papers BEGIN
            INSERT INTO papers_fts(rowid, id, title, authors, abstract, memo)
            VALUES (new.rowid, new.id, new.title, new.authors, new.abstract, new.memo);
        END;

        CREATE TRIGGER IF NOT EXISTS papers_ad AFTER DELETE ON papers BEGIN
            INSERT INTO papers_fts(papers_fts, rowid, id, title, authors, abstract, memo)
            VALUES ('delete', old.rowid, old.id, old.title, old.authors, old.abstract, old.memo);
        END;

        CREATE TRIGGER IF NOT EXISTS papers_au AFTER UPDATE ON papers BEGIN
            INSERT INTO papers_fts(papers_fts, rowid, id, title, authors, abstract, memo)
            VALUES ('delete', old.rowid, old.id, old.title, old.authors, old.abstract, old.memo);
            INSERT INTO papers_fts(rowid, id, title, authors, abstract, memo)
            VALUES (new.rowid, new.id, new.title, new.authors, new.abstract, new.memo);
        END;
    """)


def _migrate_v2(conn: sqlite3.Connection) -> None:
    """Phase 2: tagsテーブルを作成する。"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tags (
            paper_id    TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
            tag         TEXT NOT NULL,
            PRIMARY KEY (paper_id, tag)
        );

        CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);
    """)


def _migrate_v3(conn: sqlite3.Connection) -> None:
    """Phase 4: rss_feedsテーブルを作成する。"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rss_feeds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            url         TEXT NOT NULL,
            last_fetched TEXT
        );
    """)


# --- papers CRUD ---

def add_paper(
    conn: sqlite3.Connection,
    arxiv_id: str,
    title: str,
    authors: str,
    abstract: str,
    url: str,
    published: str | None = None,
) -> bool:
    """論文を追加する。既存の場合はFalseを返す。"""
    existing = conn.execute("SELECT id FROM papers WHERE id = ?", (arxiv_id,)).fetchone()
    if existing:
        return False

    conn.execute(
        """
        INSERT INTO papers (id, title, authors, abstract, url, published)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (arxiv_id, title, authors, abstract, url, published),
    )
    return True


def get_paper(conn: sqlite3.Connection, arxiv_id: str) -> sqlite3.Row | None:
    """IDで論文を取得する。"""
    return conn.execute(
        """
        SELECT p.*, GROUP_CONCAT(t.tag, ', ') AS tags
        FROM papers p
        LEFT JOIN tags t ON t.paper_id = p.id
        WHERE p.id = ?
        GROUP BY p.id
        """,
        (arxiv_id,),
    ).fetchone()


def list_papers(
    conn: sqlite3.Connection,
    unread: bool = False,
    tag: str | None = None,
    sort: str = "added",
    limit: int = 50,
) -> list[sqlite3.Row]:
    """論文一覧を返す。"""
    conditions = []
    params: list = []

    if unread:
        conditions.append("p.read_at IS NULL")

    if tag:
        conditions.append("EXISTS (SELECT 1 FROM tags t WHERE t.paper_id = p.id AND t.tag = ?)")
        params.append(tag)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    _ORDER_MAP = {
        "added": "p.added_at DESC",
        "date": "p.published DESC",
        "title": "p.title ASC",
    }
    order = _ORDER_MAP.get(sort, "p.added_at DESC")

    params.append(limit)
    return conn.execute(
        f"""
        SELECT p.*, GROUP_CONCAT(t.tag, ', ') AS tags
        FROM papers p
        LEFT JOIN tags t ON t.paper_id = p.id
        {where}
        GROUP BY p.id
        ORDER BY {order}
        LIMIT ?
        """,
        params,
    ).fetchall()


def update_memo(conn: sqlite3.Connection, arxiv_id: str, memo: str) -> None:
    """メモを更新する。"""
    conn.execute("UPDATE papers SET memo = ? WHERE id = ?", (memo, arxiv_id))


def mark_read(conn: sqlite3.Connection, arxiv_id: str) -> None:
    """既読にする。"""
    conn.execute(
        "UPDATE papers SET read_at = datetime('now') WHERE id = ?",
        (arxiv_id,),
    )


def add_tag(conn: sqlite3.Connection, arxiv_id: str, tag: str) -> None:
    """タグを追加する。"""
    conn.execute(
        "INSERT OR IGNORE INTO tags (paper_id, tag) VALUES (?, ?)",
        (arxiv_id, tag),
    )


def remove_tag(conn: sqlite3.Connection, arxiv_id: str, tag: str) -> bool:
    """タグを削除する。削除できた場合はTrueを返す。"""
    cursor = conn.execute(
        "DELETE FROM tags WHERE paper_id = ? AND tag = ?",
        (arxiv_id, tag),
    )
    return cursor.rowcount > 0


def list_tags(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """全タグと論文数を返す。"""
    return conn.execute(
        """
        SELECT tag, COUNT(*) AS count
        FROM tags
        GROUP BY tag
        ORDER BY count DESC, tag ASC
        """
    ).fetchall()


def search_papers(conn: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    """FTS5で全文検索する。"""
    return conn.execute(
        """
        SELECT p.*, GROUP_CONCAT(t.tag, ', ') AS tags
        FROM papers_fts fts
        JOIN papers p ON p.id = fts.id
        LEFT JOIN tags t ON t.paper_id = p.id
        WHERE papers_fts MATCH ?
        GROUP BY p.id
        ORDER BY rank
        LIMIT 50
        """,
        (query,),
    ).fetchall()


# --- RSS feeds CRUD ---

def add_feed(conn: sqlite3.Connection, name: str, url: str) -> bool:
    """RSSフィードを登録する。既存の場合はFalseを返す。"""
    existing = conn.execute("SELECT id FROM rss_feeds WHERE name = ?", (name,)).fetchone()
    if existing:
        return False
    conn.execute("INSERT INTO rss_feeds (name, url) VALUES (?, ?)", (name, url))
    return True


def list_feeds(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """登録済みRSSフィード一覧を返す。"""
    return conn.execute("SELECT * FROM rss_feeds ORDER BY name").fetchall()


def update_feed_fetched(conn: sqlite3.Connection, feed_id: int) -> None:
    """RSSフィードの最終取得日時を更新する。"""
    conn.execute(
        "UPDATE rss_feeds SET last_fetched = datetime('now') WHERE id = ?",
        (feed_id,),
    )
