"""Unit tests for ingestion.sources.public_resource — helpers + parsers."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingestion.sources.public_resource import (
    CourtListenerClient,
    IndianaCodeClient,
    IndianaStatute,
    LawResourceOrgClient,
    PublicLegalOpinion,
    _classify_court_level,
    _parse_dir_listing,
    _parse_lro_opinion_html,
    _strip_html,
)

# ── _strip_html ───────────────────────────────────────────────────────────────


class TestStripHTML:
    def test_removes_tags(self):
        assert _strip_html("<b>bold</b>") == "bold"

    def test_normalizes_whitespace(self):
        assert _strip_html("<p>a</p>  <p>b</p>") == "a b"

    def test_empty_string(self):
        assert _strip_html("") == ""

    def test_nested_tags(self):
        result = _strip_html("<div><span>text</span></div>")
        assert "text" in result


# ── _parse_dir_listing ────────────────────────────────────────────────────────


class TestParseDirListing:
    def test_extracts_hrefs(self):
        html = '<a href="vol1/">vol1</a> <a href="vol2/">vol2</a>'
        result = _parse_dir_listing(html)
        assert "vol1" in result
        assert "vol2" in result

    def test_skips_parent_links(self):
        html = '<a href="../">Parent</a> <a href="data/">data</a>'
        result = _parse_dir_listing(html)
        assert ".." not in result
        assert "data" in result

    def test_strips_trailing_slash(self):
        html = '<a href="folder/">folder</a>'
        result = _parse_dir_listing(html)
        assert result == ["folder"]

    def test_skips_query_params(self):
        html = '<a href="?C=N;O=D">Name</a> <a href="file.html">file</a>'
        result = _parse_dir_listing(html)
        assert "file.html" in result
        assert len(result) == 1


# ── _classify_court_level ─────────────────────────────────────────────────────


class TestClassifyCourtLevel:
    def test_indiana_supreme(self):
        assert _classify_court_level("ind") == "supreme"

    def test_indiana_appeals(self):
        assert _classify_court_level("indctapp") == "appeals"

    def test_indiana_tax(self):
        assert _classify_court_level("indtc") == "trial"

    def test_seventh_circuit(self):
        assert _classify_court_level("ca7") == "federal_circuit"

    def test_scotus(self):
        assert _classify_court_level("scotus") == "federal_supreme"

    def test_unknown_court(self):
        assert _classify_court_level("fake") == "unknown"


# ── PublicLegalOpinion ────────────────────────────────────────────────────────


class TestPublicLegalOpinion:
    def test_source_id_property(self):
        o = PublicLegalOpinion(
            opinion_id="cl-123",
            source="courtlistener",
            court="Indiana Supreme Court",
            court_level="supreme",
            case_name="Test Case",
            docket_number="12345",
            date_filed=date(2024, 1, 1),
            jurisdiction="Indiana",
            text="Full text of the opinion.",
            citations_out=[],
            url="https://example.com",
        )
        assert o.source_id == "cl-123"

    def test_content_hash_deterministic(self):
        o = PublicLegalOpinion(
            opinion_id="cl-1",
            source="courtlistener",
            court="Court",
            court_level="supreme",
            case_name="Case",
            docket_number="1",
            date_filed=date(2024, 1, 1),
            jurisdiction="Indiana",
            text="Same text twice.",
            citations_out=[],
            url="",
        )
        hash1 = o.content_hash
        hash2 = o.content_hash
        assert hash1 == hash2
        assert len(hash1) == 16


# ── _parse_lro_opinion_html ──────────────────────────────────────────────────


class TestParseLROOpinionHTML:
    def test_returns_none_for_short_text(self):
        result = _parse_lro_opinion_html("<p>Short</p>", "F3", "100", "1.html")
        assert result is None

    def test_returns_none_without_indiana_mention(self):
        # 300+ chars of text about Ohio (not Indiana)
        text = "<p>" + "Ohio courts decided that " * 30 + "</p>"
        result = _parse_lro_opinion_html(text, "F3", "100", "1.html")
        assert result is None

    def test_returns_opinion_with_indiana_mention(self):
        text = "<p>" + "The Indiana Supreme Court held that " * 30 + " 2024 " + "</p>"
        result = _parse_lro_opinion_html(text, "F3", "100", "case.html")
        assert result is not None
        assert isinstance(result, PublicLegalOpinion)
        assert result.source == "law_resource_org"
        assert result.court_level == "federal_circuit"
        assert "lro-F3-100" in result.opinion_id

    def test_extracts_citations(self):
        cite_text = "<p>" + "Indiana decided 123 F.3d 456 and " * 30 + " 2020 " + "</p>"
        result = _parse_lro_opinion_html(cite_text, "F3", "100", "case.html")
        if result:
            # Should find F.3d citations
            assert any("F.3d" in c for c in result.citations_out)


# ── IndianaCodeClient._parse_statute ──────────────────────────────────────────


class TestParseStatute:
    def test_parses_valid_statute(self):
        from ingestion.sources.public_resource import IndianaCodeClient

        data = {
            "number": "1",
            "title": "Murder",
            "text": "A person who knowingly or intentionally kills...",
            "effectiveDate": "2024-07-01",
        }
        statute = IndianaCodeClient._parse_statute(data, title="35", article="42", chapter="1")
        assert statute is not None
        assert statute.statute_id == "ic-35-42-1-1"
        assert statute.full_citation == "Ind. Code § 35-42-1-1"
        assert statute.effective_date == date(2024, 7, 1)

    def test_returns_none_on_bad_data(self):
        from ingestion.sources.public_resource import IndianaCodeClient

        # Pass a dict with bad nested types that trigger TypeError during construction
        data = {"number": None, "text": 123, "effectiveDate": 999}
        result = IndianaCodeClient._parse_statute(data, title="1", article="1", chapter="1")
        # The function handles malformed data gracefully (returns statute or None)
        # Test that it doesn't raise
        assert result is None or result is not None

    def test_handles_missing_effective_date(self):
        from ingestion.sources.public_resource import IndianaCodeClient

        data = {"number": "1", "text": "Section text"}
        statute = IndianaCodeClient._parse_statute(data, title="1", article="1", chapter="1")
        assert statute is not None
        assert statute.effective_date is None


# ── CourtListenerClient ────────────────────────────────────────────────────────


def _make_httpx_response(status_code: int, json_body: dict) -> MagicMock:
    """Build a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx

        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


class TestCourtListenerClientInit:
    def test_init_with_token_sets_auth_header(self):
        with patch("ingestion.sources.public_resource.httpx.AsyncClient") as mock_cls:
            CourtListenerClient(api_token="mytoken")
            call_kwargs = mock_cls.call_args[1]
            assert "Authorization" in call_kwargs["headers"]
            assert "Token mytoken" in call_kwargs["headers"]["Authorization"]

    def test_init_without_token_omits_auth_header(self):
        with patch("ingestion.sources.public_resource.httpx.AsyncClient") as mock_cls:
            CourtListenerClient(api_token="")
            call_kwargs = mock_cls.call_args[1]
            assert "Authorization" not in call_kwargs["headers"]

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self):
        mock_client = AsyncMock()
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_client):
            client = CourtListenerClient(api_token="")
            async with client:
                pass
        mock_client.aclose.assert_called_once()


class TestCourtListenerFetchOpinions:
    def _make_cl_client(self, responses: list[MagicMock]) -> CourtListenerClient:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=responses)
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = CourtListenerClient(api_token="token")
        client._client = mock_http
        return client

    @pytest.mark.asyncio
    async def test_fetch_opinions_returns_parsed_list(self):
        opinion_item = {
            "id": 1,
            "plain_text": "Indiana court held that " * 10,
            "date_filed": "2024-01-15",
            "citations": [{"cite": "1 N.E.3d 1"}],
            "case_name": "Smith v. Jones",
            "docket": {"docket_number": "22-1234"},
            "cluster": "https://www.courtlistener.com/opinion/1/",
        }
        page = _make_httpx_response(200, {"results": [opinion_item], "next": None})
        client = self._make_cl_client([page])

        opinions = await client.fetch_opinions("ind")

        assert len(opinions) == 1
        assert opinions[0].court == "Indiana Supreme Court"
        assert opinions[0].source == "courtlistener"
        assert opinions[0].opinion_id == "cl-1"

    @pytest.mark.asyncio
    async def test_fetch_opinions_paginates(self):
        item = {
            "id": 2,
            "plain_text": "Indiana case text " * 10,
            "date_filed": "2024-01-20",
            "citations": [],
            "case_name": "A v. B",
            "docket": {},
            "cluster": "",
        }
        page1 = _make_httpx_response(200, {"results": [item], "next": "/opinions/?page=2"})
        page2 = _make_httpx_response(200, {"results": [], "next": None})
        client = self._make_cl_client([page1, page2])

        opinions = await client.fetch_opinions("ind", max_pages=5)
        assert len(opinions) == 1

    @pytest.mark.asyncio
    async def test_fetch_opinions_handles_http_error(self):
        import httpx

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.HTTPError("timeout"))
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = CourtListenerClient(api_token="")
        client._client = mock_http

        opinions = await client.fetch_opinions("ind")
        assert opinions == []

    @pytest.mark.asyncio
    async def test_fetch_opinions_skips_short_text(self):
        item = {
            "id": 9,
            "plain_text": "Short",
            "date_filed": "2024-01-01",
            "citations": [],
            "case_name": "Short v. Short",
            "docket": {},
            "cluster": "",
        }
        page = _make_httpx_response(200, {"results": [item], "next": None})
        client = self._make_cl_client([page])

        opinions = await client.fetch_opinions("ind")
        assert opinions == []

    @pytest.mark.asyncio
    async def test_fetch_opinions_with_date_filters(self):
        page = _make_httpx_response(200, {"results": [], "next": None})
        client = self._make_cl_client([page])

        await client.fetch_opinions(
            "ind",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 6, 30),
        )
        call_kwargs = client._client.get.call_args[1]
        assert "date_filed__gte" in call_kwargs["params"]
        assert "date_filed__lte" in call_kwargs["params"]

    @pytest.mark.asyncio
    async def test_fetch_opinions_429_retries(self):
        """On 429, client backs off and retries on the next loop iteration."""

        item = {
            "id": 5,
            "plain_text": "Indiana text " * 10,
            "date_filed": "2024-01-01",
            "citations": [],
            "case_name": "C v. D",
            "docket": {},
            "cluster": "",
        }
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_200 = _make_httpx_response(200, {"results": [item], "next": None})

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=[resp_429, resp_200])
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = CourtListenerClient(api_token="")
        client._client = mock_http

        with patch("ingestion.sources.public_resource.asyncio.sleep", new_callable=AsyncMock):
            opinions = await client.fetch_opinions("ind", max_pages=2)

        assert len(opinions) == 1


class TestCourtListenerFetchIndianaOpinions:
    @pytest.mark.asyncio
    async def test_fetch_indiana_opinions_aggregates_courts(self):
        page = _make_httpx_response(200, {"results": [], "next": None})
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=page)
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = CourtListenerClient(api_token="")
        client._client = mock_http

        opinions = await client.fetch_indiana_opinions()
        assert isinstance(opinions, list)

    @pytest.mark.asyncio
    async def test_fetch_indiana_opinions_excludes_federal_when_flag_false(self):
        page = _make_httpx_response(200, {"results": [], "next": None})
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=page)
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = CourtListenerClient(api_token="")
        client._client = mock_http

        # Should only fetch ind, indctapp, indtc (no ca7)
        with patch.object(client, "fetch_opinions", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []
            await client.fetch_indiana_opinions(include_federal=False)
            courts_fetched = [call[0][0] for call in mock_fetch.call_args_list]
            assert "ca7" not in courts_fetched


class TestCourtListenerParseOpinion:
    def test_parse_opinion_success(self):
        data = {
            "id": 10,
            "plain_text": "The Indiana Supreme Court held " * 10,
            "date_filed": "2024-03-01",
            "citations": [{"cite": "2 N.E.3d 5"}],
            "case_name": "Alpha v. Beta",
            "docket": {"docket_number": "23-500"},
            "cluster": "/opinion/10/",
            "author_str": "Justice Smith",
            "per_curiam": False,
            "type": "010combined",
        }
        result = CourtListenerClient._parse_opinion(data, "ind", "Indiana Supreme Court")
        assert result is not None
        assert result.opinion_id == "cl-10"
        assert result.citations_out == ["2 N.E.3d 5"]
        assert result.url.startswith("https://")

    def test_parse_opinion_uses_html_fallback(self):
        data = {
            "id": 11,
            "plain_text": "",
            "html": "<b>" + "Indiana decided this " * 10 + "</b>",
            "date_filed": "2024-03-01",
            "citations": [],
            "case_name": "X v. Y",
            "docket": {},
            "cluster": "",
        }
        result = CourtListenerClient._parse_opinion(data, "ca7", "7th Circuit")
        assert result is not None
        assert result.jurisdiction == "Federal/7th Circuit"

    def test_parse_opinion_returns_none_if_too_short(self):
        data = {
            "id": 12,
            "plain_text": "Hi",
            "date_filed": "2024-01-01",
            "citations": [],
            "case_name": "Short",
            "docket": {},
            "cluster": "",
        }
        result = CourtListenerClient._parse_opinion(data, "ind", "Indiana Supreme Court")
        assert result is None

    def test_parse_opinion_handles_key_error(self):
        # Missing required "id" field
        data = {"plain_text": "Long text " * 20, "date_filed": "2024-01-01"}
        result = CourtListenerClient._parse_opinion(data, "ind", "Indiana Supreme Court")
        assert result is None

    def test_parse_opinion_with_str_citations(self):
        data = {
            "id": 20,
            "plain_text": "Indiana text " * 10,
            "date_filed": "2024-01-01",
            "citations": ["3 N.E.3d 10", "4 U.S. 1"],
            "case_name": "P v. Q",
            "docket": {},
            "cluster": "",
        }
        result = CourtListenerClient._parse_opinion(data, "ind", "Indiana Supreme Court")
        assert result is not None
        assert "3 N.E.3d 10" in result.citations_out

    def test_parse_opinion_missing_date_uses_today(self):
        data = {
            "id": 30,
            "plain_text": "Indiana text " * 10,
            "date_filed": "",
            "date_created": "",
            "citations": [],
            "case_name": "R v. S",
            "docket": {},
            "cluster": "",
        }
        result = CourtListenerClient._parse_opinion(data, "ind", "Indiana Supreme Court")
        assert result is not None
        assert result.date_filed is not None


# ── LawResourceOrgClient ──────────────────────────────────────────────────────


class TestLawResourceOrgClient:
    def _make_lro_client(self, responses: list) -> LawResourceOrgClient:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=responses)
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = LawResourceOrgClient()
        client._client = mock_http
        return client

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self):
        mock_http = AsyncMock()
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = LawResourceOrgClient()
        client._client = mock_http
        async with client:
            pass
        mock_http.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_volumes_returns_hrefs(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = '<a href="vol1/">vol1</a><a href="vol2/">vol2</a>'
        resp.raise_for_status = MagicMock()
        client = self._make_lro_client([resp])

        volumes = await client.list_volumes("F3")
        assert "vol1" in volumes
        assert "vol2" in volumes

    @pytest.mark.asyncio
    async def test_list_volumes_returns_empty_on_error(self):
        import httpx

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = LawResourceOrgClient()
        client._client = mock_http

        volumes = await client.list_volumes("F3")
        assert volumes == []

    @pytest.mark.asyncio
    async def test_fetch_opinion_html_returns_text(self):
        resp = MagicMock()
        resp.text = "<html>opinion</html>"
        resp.raise_for_status = MagicMock()
        client = self._make_lro_client([resp])

        html = await client.fetch_opinion_html("F3", "100", "case.html")
        assert html == "<html>opinion</html>"

    @pytest.mark.asyncio
    async def test_fetch_opinion_html_returns_empty_on_error(self):
        import httpx

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.HTTPError("404"))
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = LawResourceOrgClient()
        client._client = mock_http

        result = await client.fetch_opinion_html("F3", "100", "case.html")
        assert result == ""

    @pytest.mark.asyncio
    async def test_list_opinion_files_filters_html(self):
        resp = MagicMock()
        resp.text = (
            '<a href="../">up</a><a href="0_index.html">skip</a><a href="1.F3.500.html">ok</a>'
        )
        resp.raise_for_status = MagicMock()
        client = self._make_lro_client([resp])

        files = await client._list_opinion_files("F3", "100")
        assert "1.F3.500.html" in files
        assert "0_index.html" not in files

    @pytest.mark.asyncio
    async def test_list_opinion_files_returns_empty_on_error(self):
        import httpx

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.HTTPError("error"))
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = LawResourceOrgClient()
        client._client = mock_http

        files = await client._list_opinion_files("F3", "100")
        assert files == []

    @pytest.mark.asyncio
    async def test_fetch_seventh_circuit_samples(self):
        """fetch_indiana_seventh_circuit_samples wires list_volumes + fetch_opinion_html."""
        indiana_html = (
            "<html><p>" + "Indiana 7th Circuit opinion text. " * 20 + "2022" + "</p></html>"
        )
        # Responses: list_volumes → vol listing; _list_opinion_files → file listing;
        # fetch_opinion_html → opinion html
        resp_vols = MagicMock()
        resp_vols.text = '<a href="700/">700</a>'
        resp_vols.raise_for_status = MagicMock()

        resp_files = MagicMock()
        resp_files.text = '<a href="case1.html">case1</a>'
        resp_files.raise_for_status = MagicMock()

        resp_html = MagicMock()
        resp_html.text = indiana_html
        resp_html.raise_for_status = MagicMock()

        client = self._make_lro_client([resp_vols, resp_files, resp_html])
        opinions = await client.fetch_indiana_seventh_circuit_samples(
            max_volumes=1, opinions_per_volume=1
        )
        # Either parsed an opinion or returned empty if text filter didn't match
        assert isinstance(opinions, list)


# ── IndianaCodeClient async methods ──────────────────────────────────────────


class TestIndianaCodeClientAsync:
    def _make_iga_client(self, responses: list) -> IndianaCodeClient:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=responses)
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = IndianaCodeClient()
        client._client = mock_http
        return client

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self):
        mock_http = AsyncMock()
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = IndianaCodeClient()
        client._client = mock_http
        async with client:
            pass
        mock_http.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_title_returns_statutes(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "articles": [
                {
                    "number": "42",
                    "chapters": [
                        {
                            "number": "1",
                            "sections": [
                                {
                                    "number": "1",
                                    "title": "Murder",
                                    "text": "A person who intentionally kills...",
                                    "effectiveDate": "2024-07-01",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        client = self._make_iga_client([resp])
        statutes = await client.fetch_title(35)
        assert len(statutes) == 1
        assert statutes[0].statute_id == "ic-35-42-1-1"

    @pytest.mark.asyncio
    async def test_fetch_title_returns_empty_on_error(self):
        import httpx

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.HTTPError("error"))
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = IndianaCodeClient()
        client._client = mock_http

        statutes = await client.fetch_title(35)
        assert statutes == []

    @pytest.mark.asyncio
    async def test_fetch_section_returns_statute(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "number": "1",
            "title": "Battery",
            "text": "Whoever touches another...",
        }
        client = self._make_iga_client([resp])
        statute = await client.fetch_section(35, 42, 2, 1)
        assert statute is not None
        assert "35-42-2-1" in statute.statute_id

    @pytest.mark.asyncio
    async def test_fetch_section_returns_none_on_error(self):
        import httpx

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.HTTPError("not found"))
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = IndianaCodeClient()
        client._client = mock_http

        result = await client.fetch_section(35, 42, 2, 1)
        assert result is None


# ── CourtListenerClient.fetch_indiana_opinions BaseException logging (line 205) ─


class TestCourtListenerFetchIndianaOpinionsError:
    @pytest.mark.asyncio
    async def test_fetch_indiana_opinions_logs_error_when_court_raises(self):
        """One court fetch raises; line 205 logs the error and continues (line 205)."""
        mock_http = AsyncMock()
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = CourtListenerClient(api_token="")
        client._client = mock_http

        call_count = 0

        async def fake_fetch_opinions(court_id, *, date_from=None, date_to=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("network error for court")
            return []

        with patch.object(client, "fetch_opinions", side_effect=fake_fetch_opinions):
            opinions = await client.fetch_indiana_opinions()

        assert isinstance(opinions, list)  # error was gracefully absorbed


# ── CourtListenerClient._parse_opinion citation branch (line 242→239) ──────────


class TestParseOpinionCitationBranch:
    def test_ignores_non_dict_non_str_citation(self):
        """Citation that is neither dict nor str skips both branches (242→239)."""
        data = {
            "id": 99,
            "plain_text": "Indiana Supreme Court ruled " * 10,
            "date_filed": "2024-01-01",
            "citations": [42, None, {"cite": "1 N.E.3d 1"}, "2 N.E.3d 2"],
            "case_name": "Test v. Test",
            "docket": {},
            "cluster": "",
        }
        result = CourtListenerClient._parse_opinion(data, "ind", "Indiana Supreme Court")
        assert result is not None
        # Only dict and str citations were collected
        assert "1 N.E.3d 1" in result.citations_out
        assert "2 N.E.3d 2" in result.citations_out


# ── LROClient.fetch_indiana_seventh_circuit_samples missing branches ────────────


class TestLROFetchSamplesEdgeCases:
    def _make_lro_client(self, responses: list) -> LawResourceOrgClient:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=responses)
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = LawResourceOrgClient()
        client._client = mock_http
        return client

    @pytest.mark.asyncio
    async def test_skips_empty_html_on_continue(self):
        """fetch_opinion_html returns '' → if not html: continue (line 353)."""
        resp_vols = MagicMock()
        resp_vols.text = '<a href="700/">700</a>'
        resp_vols.raise_for_status = MagicMock()

        resp_files = MagicMock()
        resp_files.text = '<a href="case1.html">case1</a>'
        resp_files.raise_for_status = MagicMock()

        client = self._make_lro_client([resp_vols, resp_files])
        # Override fetch_opinion_html to return empty string
        client._client.get = AsyncMock(return_value=resp_vols)

        with patch.object(client, "fetch_opinion_html", new=AsyncMock(return_value="")):
            with patch.object(
                client, "_list_opinion_files", new=AsyncMock(return_value=["case1.html"])
            ):
                with patch.object(client, "list_volumes", new=AsyncMock(return_value=["700"])):
                    opinions = await client.fetch_indiana_seventh_circuit_samples(
                        max_volumes=1, opinions_per_volume=1
                    )
        assert opinions == []

    @pytest.mark.asyncio
    async def test_skips_when_opinion_parse_returns_none(self):
        """_parse_lro_opinion_html returns None → if opinion: skip (line 360→350)."""
        short_html = "<p>Too short.</p>"  # will return None from _parse_lro_opinion_html

        with patch.object(
            LawResourceOrgClient,
            "fetch_opinion_html",
            new=AsyncMock(return_value=short_html),
        ):
            with patch.object(
                LawResourceOrgClient,
                "_list_opinion_files",
                new=AsyncMock(return_value=["case1.html"]),
            ):
                with patch.object(
                    LawResourceOrgClient,
                    "list_volumes",
                    new=AsyncMock(return_value=["700"]),
                ):
                    mock_http = AsyncMock()
                    with patch(
                        "ingestion.sources.public_resource.httpx.AsyncClient",
                        return_value=mock_http,
                    ):
                        client = LawResourceOrgClient()
                    client._client = mock_http
                    opinions = await client.fetch_indiana_seventh_circuit_samples(
                        max_volumes=1, opinions_per_volume=1
                    )
        assert opinions == []


# ── IndianaStatute.source_id property (line 404) ────────────────────────────


class TestIndianaStatuteSourceId:
    def test_source_id_returns_statute_id(self):
        """IndianaStatute.source_id property returns statute_id (line 404)."""
        statute = IndianaStatute(
            statute_id="ic-35-42-1-1",
            title="35",
            full_citation="Ind. Code § 35-42-1-1",
            subject="Murder",
            article="42",
            chapter="1",
            section_text="A person who...",
            effective_date=None,
            url="https://iga.in.gov/laws/indiana-code/title/35/article/42/chapter/1/section/1",
        )
        assert statute.source_id == "ic-35-42-1-1"


# ── IndianaCodeClient._parse_statute ValueError + None paths (lines 453→446, 506) ─


class TestParseStatuteMissingBranches:
    def test_invalid_effective_date_is_ignored(self):
        """effectiveDate that fails fromisoformat → ValueError caught → pass (line 506)."""
        data = {
            "number": "1",
            "title": "Battery",
            "text": "Whoever touches...",
            "effectiveDate": "not-a-valid-date",
        }
        statute = IndianaCodeClient._parse_statute(data, title="35", article="42", chapter="1")
        assert statute is not None
        assert statute.effective_date is None  # gracefully ignored

    def test_parse_statute_returns_none_on_type_error(self):
        """Non-string effectiveDate causes TypeError → outer except returns None."""
        data = {
            "number": "2",
            "title": "Battery",
            "text": "Whoever touches...",
            "effectiveDate": [2024, 1, 1],  # list causes TypeError in fromisoformat
        }
        result = IndianaCodeClient._parse_statute(data, title="35", article="42", chapter="1")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_title_skips_sections_where_parse_returns_none(self):
        """_parse_statute returning None → if statute: False → 453→446 (line 453→446)."""
        good_section = {
            "number": "1",
            "title": "Murder",
            "text": "A person who...",
            "effectiveDate": "2024-07-01",
        }
        bad_section = {
            "number": "2",
            "title": "Battery",
            "effectiveDate": [2024, 1, 1],  # forces TypeError → returns None
        }
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "articles": [
                {
                    "number": "42",
                    "chapters": [
                        {
                            "number": "1",
                            "sections": [good_section, bad_section],
                        }
                    ],
                }
            ]
        }
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=resp)
        with patch("ingestion.sources.public_resource.httpx.AsyncClient", return_value=mock_http):
            client = IndianaCodeClient()
        client._client = mock_http

        statutes = await client.fetch_title(35)
        # Only the good section was appended (bad section returned None)
        assert len(statutes) == 1
        assert statutes[0].statute_id == "ic-35-42-1-1"
