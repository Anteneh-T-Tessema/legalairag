"""CLI for ingesting Indiana court documents into the RAG pipeline.

Usage:
    python -m ingestion.cli recent --county "Marion County" --days 7
    python -m ingestion.cli search --query "eviction" --county "Lake County"
    python -m ingestion.cli case --case-number "49D01-2401-CT-000123"
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from config.logging import get_logger
from ingestion.queue.sqs import IngestionMessage, SQSProducer
from ingestion.sources.indiana_courts import IndianaCourtClient

logger = get_logger(__name__)


async def ingest_recent(county: str, days: int, dry_run: bool) -> int:
    """Fetch recent filings and queue them for ingestion."""
    queued = 0
    async with IndianaCourtClient() as client:
        cases = await client.list_recent_filings(county=county, days_back=days)
        logger.info("found_recent_filings", county=county, days=days, count=len(cases))

        if dry_run:
            for c in cases:
                print(f"  [DRY RUN] {c.case_number} — {c.case_type} — {c.filing_date}")
            return len(cases)

        producer = SQSProducer()
        for case in cases:
            full = await client.get_case(case.case_number)
            for doc in full.documents:
                msg = IngestionMessage(
                    source_id=doc.doc_id,
                    source_type="indiana_courts",
                    document_url=doc.download_url,
                    metadata={
                        "case_number": case.case_number,
                        "court": case.court,
                        "jurisdiction": case.jurisdiction,
                        "case_type": case.case_type,
                        "doc_type": doc.doc_type,
                        "filed_date": doc.filed_date.isoformat(),
                    },
                )
                await producer.send(msg)
                queued += 1
                logger.info("queued_document", doc_id=doc.doc_id, case=case.case_number)

    logger.info("ingest_recent_complete", county=county, queued=queued)
    return queued


async def ingest_search(
    query: str, county: str | None, case_type: str | None, dry_run: bool
) -> int:
    """Search for cases and queue matching documents."""
    queued = 0
    async with IndianaCourtClient() as client:
        cases = await client.search_cases(query=query, county=county, case_type=case_type)
        logger.info("search_results", query=query, count=len(cases))

        if dry_run:
            for c in cases:
                print(f"  [DRY RUN] {c.case_number} — {c.summary[:80]}")
            return len(cases)

        producer = SQSProducer()
        for case in cases:
            full = await client.get_case(case.case_number)
            for doc in full.documents:
                msg = IngestionMessage(
                    source_id=doc.doc_id,
                    source_type="indiana_courts",
                    document_url=doc.download_url,
                    metadata={
                        "case_number": case.case_number,
                        "court": case.court,
                        "jurisdiction": case.jurisdiction,
                        "case_type": case.case_type,
                        "doc_type": doc.doc_type,
                        "filed_date": doc.filed_date.isoformat(),
                    },
                )
                await producer.send(msg)
                queued += 1

    logger.info("ingest_search_complete", query=query, queued=queued)
    return queued


async def ingest_case(case_number: str, dry_run: bool) -> int:
    """Fetch a specific case and queue all its documents."""
    queued = 0
    async with IndianaCourtClient() as client:
        case = await client.get_case(case_number)
        logger.info("case_detail", case_number=case_number, docs=len(case.documents))

        if dry_run:
            for d in case.documents:
                print(f"  [DRY RUN] {d.doc_id} — {d.doc_type} — {d.filed_date}")
            return len(case.documents)

        producer = SQSProducer()
        for doc in case.documents:
            msg = IngestionMessage(
                source_id=doc.doc_id,
                source_type="indiana_courts",
                document_url=doc.download_url,
                metadata={
                    "case_number": case.case_number,
                    "court": case.court,
                    "jurisdiction": case.jurisdiction,
                    "case_type": case.case_type,
                    "doc_type": doc.doc_type,
                    "filed_date": doc.filed_date.isoformat(),
                },
            )
            await producer.send(msg)
            queued += 1

    logger.info("ingest_case_complete", case_number=case_number, queued=queued)
    return queued


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="indyleg-ingest",
        description="Indiana Legal Document Ingestion CLI",
    )
    parser.add_argument("--dry-run", action="store_true", help="List documents without queuing")
    sub = parser.add_subparsers(dest="command", required=True)

    # recent
    p_recent = sub.add_parser("recent", help="Ingest recent filings for a county")
    p_recent.add_argument("--county", required=True, help="e.g. 'Marion County'")
    p_recent.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")

    # search
    p_search = sub.add_parser("search", help="Search cases and ingest documents")
    p_search.add_argument("--query", required=True, help="Search query string")
    p_search.add_argument("--county", default=None)
    p_search.add_argument("--case-type", default=None)

    # case
    p_case = sub.add_parser("case", help="Ingest all documents from a specific case")
    p_case.add_argument("--case-number", required=True, help="e.g. '49D01-2401-CT-000123'")

    args = parser.parse_args()

    if args.command == "recent":
        count = asyncio.run(ingest_recent(args.county, args.days, args.dry_run))
    elif args.command == "search":
        count = asyncio.run(ingest_search(args.query, args.county, args.case_type, args.dry_run))
    elif args.command == "case":
        count = asyncio.run(ingest_case(args.case_number, args.dry_run))
    else:
        parser.print_help()
        sys.exit(1)

    action = "Found" if args.dry_run else "Queued"
    print(f"\n{action} {count} document(s).")


if __name__ == "__main__":
    main()
