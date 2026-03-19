# arx — arXiv論文管理CLIツール

## セットアップ
```bash
pip install -e .
```

## テスト実行
```bash
pytest
```

## 設計方針
- SQLは必ずプレースホルダー（?）を使う
- 外部URLはhttps://のみ許可
- DBファイルは~/.arx/papers.db、chmod 600
- httpxはverify=True、timeout=10
- マイグレーションはdb.migrate()で管理（PRAGMA user_version）
- arXiv IDの正規化はutils.extract_arxiv_id()を必ず通す
