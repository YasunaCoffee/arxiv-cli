"""APIモジュールのテスト"""

from unittest.mock import MagicMock, patch

import pytest

from arx.api import fetch_paper, fetch_rss, _parse_api_response, PaperMeta


_SAMPLE_API_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2303.08774v2</id>
    <title>GPT-4 Technical Report</title>
    <summary>We report the development of GPT-4, a large-scale multimodal model.</summary>
    <published>2023-03-15T17:00:00Z</published>
    <author><name>OpenAI</name></author>
    <link rel="alternate" type="text/html" href="https://arxiv.org/abs/2303.08774"/>
  </entry>
</feed>
"""

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>cs.AI updates on arXiv.org</title>
    <item>
      <title>Attention Is All You Need</title>
      <link>https://arxiv.org/abs/1706.03762</link>
      <description>The dominant sequence transduction models...</description>
      <author>Vaswani et al.</author>
    </item>
  </channel>
</rss>
"""


class TestParseApiResponse:
    def test_parse_valid_response(self):
        meta = _parse_api_response(_SAMPLE_API_XML, "2303.08774")
        assert meta.arxiv_id == "2303.08774"
        assert meta.title == "GPT-4 Technical Report"
        assert "OpenAI" in meta.authors
        assert meta.published == "2023-03-15"
        assert "https://arxiv.org/abs/2303.08774" in meta.url

    def test_parse_empty_entries(self):
        empty_xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
        with pytest.raises(RuntimeError, match="論文が見つかりません"):
            _parse_api_response(empty_xml, "9999.99999")

    def test_parse_invalid_xml(self):
        with pytest.raises(RuntimeError, match="パース"):
            _parse_api_response("not xml", "1234.56789")


class TestFetchPaper:
    @patch("arx.api.httpx.Client")
    @patch("arx.api.time.sleep")
    def test_fetch_paper_success(self, mock_sleep, mock_client_class):
        mock_response = MagicMock()
        mock_response.text = _SAMPLE_API_XML
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        meta = fetch_paper("2303.08774")
        assert meta.arxiv_id == "2303.08774"
        assert meta.title == "GPT-4 Technical Report"

    @patch("arx.api.httpx.Client")
    @patch("arx.api.time.sleep")
    def test_fetch_paper_timeout(self, mock_sleep, mock_client_class):
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client_class.return_value = mock_client

        with pytest.raises(RuntimeError, match="タイムアウト"):
            fetch_paper("2303.08774")

    @patch("arx.api.httpx.Client")
    @patch("arx.api.time.sleep")
    def test_fetch_paper_network_error(self, mock_sleep, mock_client_class):
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(side_effect=httpx.NetworkError("connection failed"))
        mock_client_class.return_value = mock_client

        with pytest.raises(RuntimeError, match="ネットワークエラー"):
            fetch_paper("2303.08774")


class TestFetchRss:
    @patch("arx.api.httpx.Client")
    def test_fetch_rss_success(self, mock_client_class):
        mock_response = MagicMock()
        mock_response.text = _SAMPLE_RSS
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        papers = fetch_rss("https://arxiv.org/rss/cs.AI")
        assert len(papers) >= 1
        assert any(p.arxiv_id == "1706.03762" for p in papers)

    def test_fetch_rss_unsafe_url(self):
        with pytest.raises(ValueError, match="安全でない"):
            fetch_rss("http://example.com/rss")

    @patch("arx.api.httpx.Client")
    def test_fetch_rss_timeout(self, mock_client_class):
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client_class.return_value = mock_client

        with pytest.raises(RuntimeError, match="タイムアウト"):
            fetch_rss("https://arxiv.org/rss/cs.AI")
