# レビュー指摘事項（Issues）

このファイルはコードレビューで発見された問題をイシューとして記録したものです。

---

## Issue #1: [高] db.py の migrate() にバージョンアップグレードバグがある

**ラベル:** bug, high-priority

### 内容
`migrate()` で `PRAGMA user_version` を取得した後、各マイグレーションブロックで `version` 変数を更新していない。
`if version < 1` / `if version < 2` / `if version < 3` の条件分岐では、`version` は初回取得値のまま。

新規DB（version=0）では全マイグレーションが順番に走るため問題ないが、既存DB（例: version=1）を version=3 にアップグレードする際に意図しない挙動が起こり得る。

### 再現手順
version=1 のDBに対して `get_connection()` を呼ぶと、`_migrate_v1` が再実行される（`IF NOT EXISTS` で実害は回避されるが、設計として不正確）。

### 修正案
```python
def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]

    if version < 1:
        _migrate_v1(conn)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()

    if version < 2:  # ← version=0 でも version=1 でもここを通るのは正しい
        _migrate_v2(conn)
        conn.execute("PRAGMA user_version = 2")
        conn.commit()

    if version < 3:
        _migrate_v3(conn)
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
```

実はこの逐次 `if` 構造は正しく動く（version=0 なら v1→v2→v3 すべて実行、version=1 なら v2→v3 を実行）。ただし、マイグレーションのアップグレードパスのテストが存在しないことが真の問題。テストを追加すべき。

---

## Issue #2: [高] db.py の list_papers で ORDER BY 句を f-string で組み立てている

**ラベル:** security, high-priority

### 内容
`list_papers()` の ORDER BY 句を f-string で動的生成している。`sort` パラメータはコード内のリテラル値しか取らないため実際のSQLインジェクションリスクはないが、プロジェクトの設計指針「文字列結合でSQLを組み立てない」に違反する。

### 該当箇所
`arx/db.py` の `list_papers()` 関数

### 修正案
```python
_ORDER_MAP = {
    "added": "p.added_at DESC",
    "date": "p.published DESC",
    "title": "p.title ASC",
}

order = _ORDER_MAP.get(sort, "p.added_at DESC")
```
さらに、不正な `sort` 値が渡された場合に `ValueError` を送出するか、デフォルトにフォールバックするかを明示する。

---

## Issue #3: [中] cli.py の rss_fetch でループ内に毎回 DB 接続を開いている

**ラベル:** performance, enhancement

### 内容
`rss_fetch` コマンドでフィードごとに `_get_conn()` を呼んでおり、接続の開閉を繰り返している。外側で一度取得した接続を再利用すべき。

### 該当箇所
`arx/cli.py` の `rss_fetch()` 関数

### 修正案
```python
with _get_conn() as conn:
    feeds = list_feeds(conn)
    for feed in feeds:
        ...
        for meta in papers:
            add_paper(conn, ...)
        update_feed_fetched(conn, feed["id"])
```

---

## Issue #4: [中] api.py の fetch_rss にフィード間のレートリミット sleep がない

**ラベル:** bug, enhancement

### 内容
`fetch_paper()` には arXiv API レートリミット遵守のための `time.sleep(3)` があるが、`fetch_rss()` にはない。`rss_fetch` コマンドで複数フィードを連続取得する際、arXiv サーバーに短時間で連続アクセスしてしまう。

### 該当箇所
- `arx/api.py` の `fetch_rss()`
- `arx/cli.py` の `rss_fetch()`（フィードループ）

### 修正案
`rss_fetch` のループ内に `time.sleep(3)` を追加するか、`fetch_rss()` 内に sleep を組み込む。

---

## Issue #5: [低] cli.py で commit 責任が二重になっている

**ラベル:** code-quality

### 内容
`with _get_conn() as conn:` は `sqlite3.Connection` のコンテキストマネージャで、正常終了時に `conn.commit()` を呼ぶ。しかし `add_paper()` 等の DB 関数内でもそれぞれ `conn.commit()` を呼んでおり、二重コミットになっている。

実害はないが、commit 責任の所在が曖昧。

### 修正案
方針を統一する：
- **案A:** DB関数内では `conn.commit()` しない。呼び出し側の `with conn:` に任せる
- **案B:** DB関数内で `conn.commit()` する。呼び出し側は `with conn:` を使わない（ただし例外時のrollbackが漏れる）

案Aを推奨。

---

## Issue #6: [低] utils.py の正規表現で IGNORECASE フラグと大文字文字クラスが混在

**ラベル:** code-quality

### 内容
`_ARXIV_ID_PATTERN` で `re.IGNORECASE` を使いつつ、旧形式カテゴリの `[A-Z]{2}` を大文字限定で書いている。`IGNORECASE` によって `[A-Z]` は小文字もマッチするため実害はないが、意図が不明確。

### 修正案
明示的に `[A-Za-z]{2}` に書き換えるか、`re.IGNORECASE` を外してマッチ対象を厳密にする。

---

## Issue #7: [低] テスト不足 — マイグレーションとRSS fetch のカバレッジ

**ラベル:** testing

### 内容
以下のテストが不足している：

1. **マイグレーションのアップグレードパス**: v1→v2→v3 の段階的アップグレードが正しく動くことのテスト
2. **`arx rss fetch` のE2Eテスト**: フィードを登録→フェッチ→論文が追加される一連のフロー
3. **`extract_arxiv_id` の旧形式ID**: `hep-th/0001001` 形式のテスト
