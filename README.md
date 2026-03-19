# arx — arXiv論文管理CLIツール

arXiv論文をローカルで管理するPython製CLIツール。

## インストール

```bash
uv sync
```

## 使い方

> **注意:** `uv sync` でインストールした場合、各コマンドの先頭に `uv run` が必要です（例: `uv run arx list`）。
> `pip install -e .` でインストールした場合は `arx` をそのまま使えます。

```bash
# 論文を追加
uv run arx add 2303.08774
uv run arx add https://arxiv.org/abs/2303.08774

# 一覧表示
uv run arx list
uv run arx list --unread --sort date
uv run arx list --tag survey

# 詳細表示
uv run arx show 2303.08774

# メモ管理
uv run arx memo 2303.08774 "Section 3のアーキテクチャが面白い"
uv run arx memo 2303.08774          # メモを表示
uv run arx memo 2303.08774 --delete # メモを削除

# タグ管理
uv run arx tag 2303.08774 transformer attention
uv run arx tag 2303.08774 --list    # 全タグ一覧
uv run arx tag 2303.08774 --remove attention

# 既読にする
uv run arx read 2303.08774

# 全文検索
uv run arx search "diffusion score"
uv run arx search "classifier-free" --tag generation

# ブラウザで開く
uv run arx open 2303.08774

# RSS管理
uv run arx rss add cs.AI https://arxiv.org/rss/cs.AI
uv run arx rss list
uv run arx rss fetch
```

## テスト

```bash
uv run pytest
```
