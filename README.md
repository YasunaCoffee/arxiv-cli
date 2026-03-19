# arx — arXiv論文管理CLIツール

arXiv論文をローカルで管理するPython製CLIツール。

## インストール

```bash
pip install -e .
```

## 使い方

```bash
# 論文を追加
arx add 2303.08774
arx add https://arxiv.org/abs/2303.08774

# 一覧表示
arx list
arx list --unread --sort date
arx list --tag survey

# 詳細表示
arx show 2303.08774

# メモ管理
arx memo 2303.08774 "Section 3のアーキテクチャが面白い"
arx memo 2303.08774          # メモを表示
arx memo 2303.08774 --delete # メモを削除

# タグ管理
arx tag 2303.08774 transformer attention
arx tag 2303.08774 --list    # 全タグ一覧
arx tag 2303.08774 --remove attention

# 既読にする
arx read 2303.08774

# 全文検索
arx search "diffusion score"
arx search "classifier-free" --tag generation

# ブラウザで開く
arx open 2303.08774

# RSS管理
arx rss add cs.AI https://arxiv.org/rss/cs.AI
arx rss list
arx rss fetch
```

## テスト

```bash
pytest
```
