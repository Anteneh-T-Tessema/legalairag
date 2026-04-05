#!/usr/bin/env python3
"""Ingest Indiana Code into the pgvector database.

Two modes:
  --api-key KEY    Pull statutes via the api.iga.in.gov REST API.
  --zip-file PATH  Parse a locally-downloaded IGA HTML ZIP.

Register for an IGA API key at: https://api.iga.in.gov/
Download the HTML ZIP manually from: https://iga.in.gov/laws/ic/downloads

Examples
--------
# IGA REST API (requires free API key from IGA):
python infrastructure/scripts/ingest_indiana_code.py \
    --api-key YOUR_IGA_KEY --titles 35,31,9,6 --year 2025

# Local HTML ZIP:
python infrastructure/scripts/ingest_indiana_code.py \
    --zip-file ~/Downloads/2025-Indiana-Code-html.zip --titles 35,31,9,6

By default the script targets the local Docker Postgres:
  DATABASE_URL=postgresql://user:password@localhost:5432/indyleg
Override by setting DATABASE_URL in your environment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import zipfile
from typing import Any
from urllib.parse import urljoin

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/indyleg",
)

IGA_API_BASE = "https://api.iga.in.gov"

# Titles to ingest when --titles is not specified
DEFAULT_TITLES = [
    "6",   # Taxation
    "9",   # Motor Vehicles
    "11",  # Corrections & Criminal Justice
    "22",  # Labor & Safety
    "31",  # Family Law
    "32",  # Property
    "34",  # Civil Remedies
    "35",  # Criminal & Sentencing
]

# Maximum characters per chunk before splitting on paragraph boundary
MAX_CHUNK_CHARS = 2000


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    """Return a lowercase, hyphenated identifier from an IC citation."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _chunk_id(section_id: str, idx: int) -> str:
    return f"ic-{_slug(section_id)}-{idx:03d}"


def _source_id(title: str, article: str) -> str:
    return f"indiana-code-{title}-{article}"


def _extract_article(section_id: str) -> str:
    """Extract article number from 'IC 35-42-1-1' → '42'."""
    parts = re.split(r"[-.]", section_id.replace("IC ", ""))
    if len(parts) >= 2:
        return parts[1]
    return "0"


def _extract_title(section_id: str) -> str:
    """Extract title number from 'IC 35-42-1-1' → '35'."""
    parts = re.split(r"[-.]", section_id.replace("IC ", ""))
    return parts[0] if parts else "0"


def _split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split *text* into chunks of at most *max_chars* on paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    paragraphs = re.split(r"\n{2,}", text)
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current.strip())
            current = para
        else:
            current = (current + "\n\n" + para).lstrip("\n")
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text[:max_chars]]


# ---------------------------------------------------------------------------
# Deterministic vector (dev/seed only — matches seed_dev_data.py)
# ---------------------------------------------------------------------------

def _deterministic_vector(text: str, dim: int = 1536) -> list[float]:
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16)  # noqa: S324
    rng_state = seed
    vec: list[float] = []
    for _ in range(dim):
        rng_state = (rng_state * 1_664_525 + 1_013_904_223) & 0xFFFF_FFFF
        vec.append((rng_state / 0xFFFF_FFFF) * 2 - 1)
    magnitude = sum(v * v for v in vec) ** 0.5
    return [v / magnitude for v in vec]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _upsert_chunks(conn: Any, chunks: list[dict]) -> int:
    """Insert *chunks* into the paragraphs table; return count inserted/updated."""
    sql = """
        INSERT INTO paragraphs
            (chunk_id, source_id, section, section_idx,
             content, citations, metadata, embedding)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s::vector)
        ON CONFLICT (chunk_id) DO UPDATE SET
            content    = EXCLUDED.content,
            citations  = EXCLUDED.citations,
            metadata   = EXCLUDED.metadata,
            embedding  = EXCLUDED.embedding
    """
    count = 0
    with conn.cursor() as cur:
        for chunk in chunks:
            vec = _deterministic_vector(chunk["content"])
            vec_str = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
            cur.execute(
                sql,
                (
                    chunk["chunk_id"],
                    chunk["source_id"],
                    chunk["section"],
                    chunk["section_idx"],
                    chunk["content"],
                    json.dumps(chunk["citations"]),
                    json.dumps(chunk["metadata"]),
                    vec_str,
                ),
            )
            count += 1
    conn.commit()
    return count


# ---------------------------------------------------------------------------
# IGA REST API walker
# ---------------------------------------------------------------------------

def _api_get(session: Any, path: str, api_key: str) -> dict | list | None:
    """GET *path* from the IGA API; return parsed JSON or None on error."""
    url = urljoin(IGA_API_BASE, path)
    headers = {"x-api-key": api_key, "Accept": "application/json"}
    try:
        resp = session.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            print(f"  Rate-limited on {url}; sleeping 5 s …", file=sys.stderr)
            time.sleep(5)
            resp = session.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()
        print(
            f"  HTTP {resp.status_code} for {url}",
            file=sys.stderr,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  Error fetching {url}: {exc}", file=sys.stderr)
    return None


def _build_chunk_from_api_section(
    section_data: dict,
    title: str,
    article: str,
    chapter: str,
) -> list[dict]:
    """Convert an IGA API section object to one or more chunk dicts."""
    section_id = section_data.get("id", "")
    citation = f"IC {section_id}"
    title_text = section_data.get("catchline", "")
    body = section_data.get("s", "") or section_data.get("text", "") or ""

    # Strip HTML tags if present
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()

    if not body:
        return []

    full_text = f"{citation} — {title_text}\n{body}" if title_text else f"{citation}\n{body}"
    texts = _split_into_chunks(full_text)

    return [
        {
            "chunk_id": _chunk_id(section_id, idx),
            "source_id": _source_id(title, article),
            "section": citation,
            "section_idx": idx,
            "content": text,
            "citations": [citation],
            "metadata": {
                "court": "indiana",
                "jurisdiction": "Indiana",
                "type": "statute",
                "title": title,
                "article": article,
            },
        }
        for idx, text in enumerate(texts)
    ]


def walk_api(api_key: str, year: int, titles: list[str]) -> list[dict]:
    """Walk the IGA API and return all chunks for the requested titles."""
    try:
        import httpx
    except ImportError:
        print(
            "httpx is required for --api-key mode.  Install with: pip install httpx",
            file=sys.stderr,
        )
        sys.exit(1)

    chunks: list[dict] = []
    with httpx.Client() as session:
        for title_num in titles:
            print(f"Title {title_num} …")
            title_path = f"/{year}/ic/title/{title_num}"
            title_data = _api_get(session, title_path, api_key)
            if not title_data:
                continue

            articles = title_data.get("articles", []) or []
            for art in articles:
                art_num = art.get("id", "").split(".")[-1]
                art_path = f"{title_path}/article/{art_num}"
                art_data = _api_get(session, art_path, api_key)
                if not art_data:
                    continue

                chapters = art_data.get("chapters", []) or []
                for chap in chapters:
                    chap_num = chap.get("id", "").split(".")[-1]
                    chap_path = f"{art_path}/chapter/{chap_num}"
                    chap_data = _api_get(session, chap_path, api_key)
                    if not chap_data:
                        continue

                    sections = chap_data.get("sections", []) or []
                    for sec in sections:
                        sec_id = sec.get("id", "")
                        sec_path = f"{chap_path}/section/{sec_id}"
                        sec_data = _api_get(session, sec_path, api_key)
                        if not sec_data:
                            continue

                        new_chunks = _build_chunk_from_api_section(
                            sec_data, title_num, art_num, chap_num
                        )
                        if new_chunks:
                            print(
                                f"  IC {sec_id}: {len(new_chunks)} chunk(s)"
                            )
                            chunks.extend(new_chunks)

    return chunks


# ---------------------------------------------------------------------------
# IGA HTML ZIP parser
# ---------------------------------------------------------------------------

def _parse_section_html(html: str, filename: str) -> dict | None:
    """Extract section text from an IGA HTML file.

    Returns a dict with keys: id, catchline, text.
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore[import]
    except ImportError:
        print(
            "beautifulsoup4 is required for --zip-file mode. "
            "Install with: pip install beautifulsoup4",
            file=sys.stderr,
        )
        sys.exit(1)

    soup = BeautifulSoup(html, "html.parser")

    # Remove navigation elements
    for tag in soup.find_all(["nav", "header", "footer", "script", "style"]):
        tag.decompose()

    # Try to find the section citation (e.g. "IC 35-42-1-1")
    citation = ""
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = tag.get_text(" ", strip=True)
        if re.search(r"IC\s+\d+", text, re.IGNORECASE):
            citation = text
            break

    # Derive citation from filename if not found in HTML
    if not citation:
        stem = os.path.splitext(os.path.basename(filename))[0]
        parts = stem.replace("_", "-").split("-")
        if len(parts) >= 2:
            citation = "IC " + "-".join(parts)

    catchline = ""
    for tag in soup.find_all(["h4", "p"]):
        t = tag.get_text(" ", strip=True)
        if t and not re.search(r"^\d", t):
            catchline = t
            break

    body = soup.get_text(" ", strip=True)
    body = re.sub(r"\s+", " ", body).strip()

    if not body or len(body) < 30:
        return None

    return {"id": citation, "catchline": catchline, "text": body}


def walk_zip(zip_path: str, titles: list[str]) -> list[dict]:
    """Parse a locally downloaded IGA HTML ZIP and return all chunks."""
    chunks: list[dict] = []
    title_set = set(titles)

    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".html")]
        print(f"ZIP contains {len(names)} HTML files.")

        for name in names:
            # IGA HTML ZIPs typically use paths like:
            #   title35/article42/chapter01/IC_35-42-1-1.html
            parts_path = name.replace("\\", "/").split("/")
            title_folder = parts_path[0] if parts_path else ""
            title_num = re.sub(r"[^0-9.]", "", title_folder)

            if title_set and title_num not in title_set:
                continue

            with zf.open(name) as fh:
                html = fh.read().decode("utf-8", errors="replace")

            sec_data = _parse_section_html(html, name)
            if not sec_data:
                continue

            # Extract article from path
            art_folder = parts_path[1] if len(parts_path) > 1 else ""
            article = re.sub(r"[^0-9.]", "", art_folder) or "0"

            new_chunks = _build_chunk_from_api_section(
                sec_data, title_num, article, "0"
            )
            if new_chunks:
                chunks.extend(new_chunks)

    print(f"Parsed {len(chunks)} chunks from ZIP.")
    return chunks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Indiana Code into the pgvector database.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--api-key",
        metavar="KEY",
        help="api.iga.in.gov API key (register free at https://api.iga.in.gov/)",
    )
    group.add_argument(
        "--zip-file",
        metavar="PATH",
        help="Path to locally downloaded IGA HTML ZIP",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2025,
        help="Indiana Code edition year (default: 2025)",
    )
    parser.add_argument(
        "--titles",
        default=",".join(DEFAULT_TITLES),
        help=(
            "Comma-separated list of IC title numbers to ingest "
            f"(default: {','.join(DEFAULT_TITLES)})"
        ),
    )
    parser.add_argument(
        "--database-url",
        default=DATABASE_URL,
        help="PostgreSQL connection URL (default: $DATABASE_URL env or docker dev URL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print chunks without writing to the database",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    titles = [t.strip() for t in args.titles.split(",") if t.strip()]

    print(f"Titles to ingest: {titles}")
    print(f"Year: {args.year}")
    print(f"Mode: {'API' if args.api_key else 'ZIP'}")

    if args.api_key:
        chunks = walk_api(args.api_key, args.year, titles)
    else:
        zip_path = os.path.expanduser(args.zip_file)
        if not os.path.exists(zip_path):
            print(f"Error: ZIP file not found: {zip_path}", file=sys.stderr)
            sys.exit(1)
        chunks = walk_zip(zip_path, titles)

    print(f"\nTotal chunks prepared: {len(chunks)}")

    if args.dry_run:
        print("\n-- DRY RUN: first 3 chunks --")
        for chunk in chunks[:3]:
            print(json.dumps(chunk, indent=2, default=str))
        return

    try:
        import psycopg  # type: ignore[import]
    except ImportError:
        print("psycopg is required. Install with: pip install psycopg[binary]", file=sys.stderr)
        sys.exit(1)

    print(f"\nConnecting to {args.database_url} …")
    with psycopg.connect(args.database_url) as conn:
        inserted = _upsert_chunks(conn, chunks)

    print(f"Done. {inserted} chunks inserted/updated.")


if __name__ == "__main__":
    main()
