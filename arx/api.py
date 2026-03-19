"""arXiv API・RSS取得"""

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import feedparser
import httpx

from arx.utils import extract_arxiv_id, is_safe_url

_ARXIV_API_BASE = "https://export.arxiv.org/api/query"
_RATE_LIMIT_SLEEP = 3.0  # arXiv APIレートリミット遵守

# XML名前空間
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


@dataclass
class PaperMeta:
    """arXiv論文メタデータ"""
    arxiv_id: str
    title: str
    authors: str
    abstract: str
    url: str
    published: str | None


def fetch_paper(arxiv_id: str) -> PaperMeta:
    """arXiv APIから論文メタデータを取得する。"""
    url = f"{_ARXIV_API_BASE}?id_list={arxiv_id}&max_results=1"

    try:
        with httpx.Client(verify=True, timeout=10, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise RuntimeError("arXiv APIへの接続がタイムアウトしました。")
    except httpx.NetworkError as e:
        raise RuntimeError(f"ネットワークエラーが発生しました: {e}")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"arXiv APIがエラーを返しました: {e.response.status_code}")

    time.sleep(_RATE_LIMIT_SLEEP)

    return _parse_api_response(response.text, arxiv_id)


def _parse_api_response(xml_text: str, arxiv_id: str) -> PaperMeta:
    """arXiv APIのXMLレスポンスをパースする。"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise RuntimeError(f"APIレスポンスのパースに失敗しました: {e}")

    entries = root.findall("atom:entry", _NS)
    if not entries:
        raise RuntimeError(f"論文が見つかりませんでした: {arxiv_id}")

    entry = entries[0]

    # エラーチェック（arXiv APIはエラー時もentryを返す場合がある）
    title_el = entry.find("atom:title", _NS)
    if title_el is not None and title_el.text and "Error" in title_el.text:
        raise RuntimeError(f"論文が見つかりませんでした: {arxiv_id}")

    title = _get_text(entry, "atom:title")
    abstract = _get_text(entry, "atom:summary")
    published = _get_text(entry, "atom:published")

    # 著者リスト
    author_els = entry.findall("atom:author", _NS)
    authors = ", ".join(
        _get_text(a, "atom:name") for a in author_els
    )

    # abs URLを取得
    url = f"https://arxiv.org/abs/{arxiv_id}"
    for link in entry.findall("atom:link", _NS):
        if link.get("rel") == "alternate" and link.get("type") == "text/html":
            href = link.get("href", "")
            if is_safe_url(href):
                url = href
                break

    # publishedはISO形式の先頭10文字（日付部分）
    pub_date = published[:10] if published else None

    return PaperMeta(
        arxiv_id=arxiv_id,
        title=title.strip(),
        authors=authors,
        abstract=abstract.strip(),
        url=url,
        published=pub_date,
    )


def _get_text(element: ET.Element, tag: str) -> str:
    """要素のテキストを取得する。"""
    el = element.find(tag, _NS)
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def fetch_rss(feed_url: str) -> list[PaperMeta]:
    """RSSフィードから新着論文を取得する。"""
    if not is_safe_url(feed_url):
        raise ValueError(f"安全でないURLです: {feed_url}")

    try:
        with httpx.Client(verify=True, timeout=10, follow_redirects=True) as client:
            response = client.get(feed_url)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise RuntimeError("RSSフィードへの接続がタイムアウトしました。")
    except httpx.NetworkError as e:
        raise RuntimeError(f"ネットワークエラーが発生しました: {e}")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"RSSフィードがエラーを返しました: {e.response.status_code}")

    feed = feedparser.parse(response.text)
    papers = []

    for entry in feed.entries:
        link = getattr(entry, "link", "") or ""
        arxiv_id = extract_arxiv_id(link)
        if not arxiv_id:
            # idフィールドからも試みる
            arxiv_id = extract_arxiv_id(getattr(entry, "id", "") or "")
        if not arxiv_id:
            continue

        title = getattr(entry, "title", "") or ""
        title = title.replace("\n", " ").strip()

        # 著者
        authors_list = getattr(entry, "authors", [])
        if authors_list:
            authors = ", ".join(a.get("name", "") for a in authors_list)
        else:
            authors = getattr(entry, "author", "") or ""

        # アブスト
        summary = ""
        if hasattr(entry, "summary"):
            summary = entry.summary or ""
        summary = summary.strip()

        published = None
        if hasattr(entry, "published"):
            pub = entry.published or ""
            published = pub[:10] if pub else None

        url = link if is_safe_url(link) else f"https://arxiv.org/abs/{arxiv_id}"

        papers.append(PaperMeta(
            arxiv_id=arxiv_id,
            title=title,
            authors=authors,
            abstract=summary,
            url=url,
            published=published,
        ))

    return papers
