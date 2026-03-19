"""バリデーション等のヘルパー関数"""

import re
from urllib.parse import urlparse


# arXiv IDのパターン（新旧両形式）
_ARXIV_ID_PATTERN = re.compile(
    r"(?:arxiv[:/])?(\d{4}\.\d{4,5}(?:v\d+)?|[a-zA-Z\-]+(?:\.[a-zA-Z]{2})?/\d{7}(?:v\d+)?)",
    re.IGNORECASE,
)


def extract_arxiv_id(value: str) -> str | None:
    """URLまたは文字列からarXiv IDを抽出・正規化する。"""
    value = value.strip()

    # URLの場合はpathを取り出す
    parsed = urlparse(value)
    if parsed.scheme in ("http", "https"):
        path = parsed.path.rstrip("/")
        # /abs/ID, /pdf/ID, /html/ID などに対応
        for prefix in ("/abs/", "/pdf/", "/html/", "/e-print/"):
            if prefix in path:
                candidate = path.split(prefix, 1)[1]
                # .pdf拡張子を除去
                candidate = re.sub(r"\.pdf$", "", candidate)
                m = _ARXIV_ID_PATTERN.match(candidate)
                if m:
                    return _normalize_id(m.group(1))
        return None

    # 生ID or "arxiv:ID" 形式
    m = _ARXIV_ID_PATTERN.match(value)
    if m:
        return _normalize_id(m.group(1))

    return None


def _normalize_id(arxiv_id: str) -> str:
    """arXiv IDを小文字・バージョン除去なし、標準形式に正規化する。"""
    # バージョン番号は保持しない（常に最新を指す）
    return re.sub(r"v\d+$", "", arxiv_id)


def is_safe_url(url: str) -> bool:
    """URLがhttpsスキームかどうか検証する。"""
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https"
    except Exception:
        return False
