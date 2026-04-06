"""Unit tests for ingestion.cli — CLI argument parsing + async dispatch."""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingestion.cli import ingest_case, ingest_recent, ingest_search, main


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _fake_case(case_number="C-1", docs=None):
    case = MagicMock()
    case.case_number = case_number
    case.court = "Test Court"
    case.jurisdiction = "Test County"
    case.case_type = "Civil"
    case.filing_date = date(2024, 1, 1)
    case.summary = "Test case summary"
    if docs is None:
        doc = MagicMock()
        doc.doc_id = "d1"
        doc.download_url = "https://example.com/d1"
        doc.doc_type = "Order"
        doc.filed_date = date(2024, 1, 2)
        docs = [doc]
    case.documents = docs
    return case


# ── ingest_recent ─────────────────────────────────────────────────────────────


class TestIngestRecent:
    def test_dry_run_returns_count(self):
        case = _fake_case()
        with patch("ingestion.cli.IndianaCourtClient") as MockClient:
            ctx = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            ctx.list_recent_filings = AsyncMock(return_value=[case])

            count = _run(ingest_recent("Marion County", 7, dry_run=True))
            assert count == 1

    def test_queues_documents(self):
        case = _fake_case()
        full_case = _fake_case(
            docs=[
                MagicMock(
                    doc_id="d1",
                    download_url="https://example.com/d1",
                    doc_type="Order",
                    filed_date=date(2024, 1, 2),
                )
            ]
        )
        with (
            patch("ingestion.cli.IndianaCourtClient") as MockClient,
            patch("ingestion.cli.SQSProducer") as MockProducer,
        ):
            ctx = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            ctx.list_recent_filings = AsyncMock(return_value=[case])
            ctx.get_case = AsyncMock(return_value=full_case)

            producer = MockProducer.return_value
            producer.publish = AsyncMock()

            count = _run(ingest_recent("Marion County", 7, dry_run=False))
            assert count == 1
            producer.publish.assert_called_once()


# ── ingest_search ─────────────────────────────────────────────────────────────


class TestIngestSearch:
    def test_dry_run(self):
        case = _fake_case()
        with patch("ingestion.cli.IndianaCourtClient") as MockClient:
            ctx = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            ctx.search_cases = AsyncMock(return_value=[case])

            count = _run(ingest_search("eviction", None, None, dry_run=True))
            assert count == 1

    def test_queues_search_results(self):
        case = _fake_case()
        full = _fake_case(
            docs=[
                MagicMock(
                    doc_id="d2",
                    download_url="https://x.com/d2",
                    doc_type="Complaint",
                    filed_date=date(2024, 3, 1),
                )
            ]
        )
        with (
            patch("ingestion.cli.IndianaCourtClient") as MockClient,
            patch("ingestion.cli.SQSProducer") as MockProducer,
        ):
            ctx = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            ctx.search_cases = AsyncMock(return_value=[case])
            ctx.get_case = AsyncMock(return_value=full)

            producer = MockProducer.return_value
            producer.publish = AsyncMock()

            count = _run(ingest_search("eviction", "Marion County", "Civil", dry_run=False))
            assert count == 1


# ── ingest_case ───────────────────────────────────────────────────────────────


class TestIngestCase:
    def test_dry_run(self):
        case = _fake_case(
            docs=[
                MagicMock(doc_id="d1", doc_type="Order", filed_date=date(2024, 1, 1)),
                MagicMock(doc_id="d2", doc_type="Complaint", filed_date=date(2024, 1, 2)),
            ]
        )
        with patch("ingestion.cli.IndianaCourtClient") as MockClient:
            ctx = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            ctx.get_case = AsyncMock(return_value=case)

            count = _run(ingest_case("49D01-2401-CT-000123", dry_run=True))
            assert count == 2

    def test_queues_all_case_documents(self):
        doc1 = MagicMock(
            doc_id="d1",
            download_url="https://x.com/d1",
            doc_type="Order",
            filed_date=date(2024, 1, 1),
        )
        doc2 = MagicMock(
            doc_id="d2",
            download_url="https://x.com/d2",
            doc_type="Judgment",
            filed_date=date(2024, 1, 2),
        )
        case = _fake_case(docs=[doc1, doc2])
        with (
            patch("ingestion.cli.IndianaCourtClient") as MockClient,
            patch("ingestion.cli.SQSProducer") as MockProducer,
        ):
            ctx = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            ctx.get_case = AsyncMock(return_value=case)

            producer = MockProducer.return_value
            producer.publish = AsyncMock()

            count = _run(ingest_case("49D01-2401-CT-000123", dry_run=False))
            assert count == 2
            assert producer.publish.call_count == 2


# ── main() argument parsing ──────────────────────────────────────────────────


class TestMain:
    def test_recent_command(self):
        with (
            patch("sys.argv", ["indyleg-ingest", "recent", "--county", "Marion County"]),
            patch("ingestion.cli.ingest_recent", return_value=5),
            patch("asyncio.run", side_effect=lambda coro: _run(coro)),
        ):
            # asyncio.run calls the coroutine; we mock ingest_recent
            with patch("ingestion.cli.asyncio.run", return_value=5):
                main()

    def test_search_command(self):
        with (
            patch("sys.argv", ["indyleg-ingest", "search", "--query", "eviction"]),
            patch("ingestion.cli.asyncio.run", return_value=3),
        ):
            main()

    def test_case_command(self):
        with (
            patch("sys.argv", ["indyleg-ingest", "case", "--case-number", "C-1"]),
            patch("ingestion.cli.asyncio.run", return_value=1),
        ):
            main()

    def test_no_command_prints_help_and_exits(self):
        """Running with no subcommand triggers parser.print_help() + sys.exit(1) (lines 163-164)."""
        from argparse import Namespace

        with (
            patch(
                "argparse.ArgumentParser.parse_args",
                return_value=Namespace(command=None, dry_run=False),
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1
