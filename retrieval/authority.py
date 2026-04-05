"""
Indiana Court Authority Hierarchy and Citation Graph.

Two components:

1. AuthorityRanker
   Scores search results by court authority under Indiana law.
   The hierarchy mirrors how Indiana courts are bound by precedent:

     US Supreme Court        → weight 1.00  (binding on federal questions)
     7th Circuit             → weight 0.90  (binding federal circuit)
     Indiana Supreme Court   → weight 0.85  (highest Indiana state authority)
     Indiana Court of Appeals→ weight 0.70  (binding unless overruled by IndSCt)
     Indiana Tax Court       → weight 0.60  (specialized — tax matters only)
     Federal District (Ind.) → weight 0.55  (persuasive on state questions)
     Indiana Trial Courts    → weight 0.40  (persuasive only)

   Authority scores are blended with retrieval scores (configurable weight).

2. CitationGraph
   Builds and queries an in-memory directed graph of legal citations:
     edge: citing_opinion → cited_opinion
   Supports:
     - PageRank-style authority propagation
     - "Good law" validation (detect overruled/distinguished opinions)
     - Precedent chain traversal
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from config.logging import get_logger
from retrieval.hybrid_search import SearchResult

logger = get_logger(__name__)


# ── Court Authority Hierarchy ──────────────────────────────────────────────────

_COURT_WEIGHTS: dict[str, float] = {
    # US Supreme Court
    "us supreme court": 1.00,
    "supreme court of the united states": 1.00,
    "scotus": 1.00,
    # Federal Circuit (7th covers Indiana)
    "7th circuit court of appeals": 0.90,
    "united states court of appeals for the seventh circuit": 0.90,
    "ca7": 0.90,
    # Indiana Supreme Court
    "indiana supreme court": 0.85,
    "supreme court of indiana": 0.85,
    "ind": 0.85,
    # Indiana Court of Appeals
    "indiana court of appeals": 0.70,
    "court of appeals of indiana": 0.70,
    "indctapp": 0.70,
    # Indiana Tax Court
    "indiana tax court": 0.60,
    "indtc": 0.60,
    # Federal District Courts in Indiana
    "united states district court for the southern district of indiana": 0.55,
    "united states district court for the northern district of indiana": 0.55,
    "s.d. ind": 0.55,
    "n.d. ind": 0.55,
    # Indiana Trial/Circuit Courts
    "marion county superior court": 0.40,
    "indiana circuit court": 0.40,
}

_DEFAULT_AUTHORITY_WEIGHT = 0.35


def get_authority_score(court: str) -> float:
    """Return the authority weight for a given court name."""
    court_lower = court.lower().strip()
    # Exact match
    if court_lower in _COURT_WEIGHTS:
        return _COURT_WEIGHTS[court_lower]
    # Substring match (most specific first)
    for court_key, weight in sorted(_COURT_WEIGHTS.items(), key=lambda x: -len(x[0])):
        if court_key in court_lower:
            return weight
    return _DEFAULT_AUTHORITY_WEIGHT


class AuthorityRanker:
    """
    Re-scores retrieval results by blending retrieval score with court authority.

    Rationale: A lower retrieval score from the Indiana Supreme Court should often
    outrank a higher score from a trial court for binding precedent questions.

    Blend formula:
        final_score = (1 - alpha) * retrieval_score + alpha * authority_score

    Default alpha=0.30 — authority contributes 30% of the final score.
    Configurable per query type (e.g., citation-lookup queries use lower alpha).
    """

    def __init__(self, authority_alpha: float = 0.30) -> None:
        self.authority_alpha = authority_alpha

    def rerank(
        self,
        results: list[SearchResult],
        alpha: float | None = None,
    ) -> list[SearchResult]:
        """Apply authority blending and re-sort results."""
        a = alpha if alpha is not None else self.authority_alpha
        adjusted: list[tuple[SearchResult, float]] = []

        for result in results:
            court = result.metadata.get("court", "")
            authority = get_authority_score(court)
            blended = (1.0 - a) * result.score + a * authority

            # Log large score adjustments for monitoring
            if abs(blended - result.score) > 0.20:
                logger.debug(
                    "authority_rerank",
                    chunk_id=result.chunk_id,
                    court=court,
                    original_score=round(result.score, 3),
                    authority_score=round(authority, 3),
                    blended=round(blended, 3),
                )

            adjusted.append((result, blended))

        adjusted.sort(key=lambda x: x[1], reverse=True)

        for result, blended_score in adjusted:
            result.score = blended_score

        return [r for r, _ in adjusted]


# ── Temporal Validity ─────────────────────────────────────────────────────────

def is_temporally_valid(metadata: dict[str, Any], reference_date: date | None = None) -> bool:
    """
    Check if a document is temporally valid relative to a reference date.

    For statutes: the effective_date must be <= reference_date and
    no expiry_date must have passed.
    For case law: generally valid unless explicitly overruled (see CitationGraph).
    """
    ref = reference_date or date.today()

    effective_str = metadata.get("effective_date") or metadata.get("effectiveDate")
    if effective_str:
        try:
            effective = date.fromisoformat(str(effective_str)[:10])
            if effective > ref:
                return False  # Not yet in effect
        except ValueError:
            pass

    expiry_str = metadata.get("expiry_date") or metadata.get("expiryDate")
    if expiry_str:
        try:
            expiry = date.fromisoformat(str(expiry_str)[:10])
            if expiry < ref:
                return False  # Expired
        except ValueError:
            pass

    return True


def filter_temporally_valid(
    results: list[SearchResult],
    reference_date: date | None = None,
    warn_on_filter: bool = True,
) -> list[SearchResult]:
    """Remove results whose underlying documents are no longer in effect."""
    valid = []
    for r in results:
        if is_temporally_valid(r.metadata, reference_date):
            valid.append(r)
        elif warn_on_filter:
            logger.warning(
                "stale_document_filtered",
                source_id=r.source_id,
                effective=r.metadata.get("effective_date"),
                expiry=r.metadata.get("expiry_date"),
            )
    return valid


# ── Citation Graph ─────────────────────────────────────────────────────────────

_NEGATIVE_TREATMENT = {
    "overruled",
    "overruled by",
    "reversed",
    "disapproved",
    "abrogated",
    "criticized",
    "distinguished",
}

_POSITIVE_TREATMENT = {
    "affirmed",
    "followed",
    "cited",
    "relied on",
    "approved",
    "cited with approval",
}


@dataclass
class CitationEdge:
    citing_id: str
    cited_id: str
    treatment: str          # "cited" | "followed" | "overruled" | "distinguished" | ...
    is_negative: bool
    date_cited: date | None = None
    context_snippet: str = ""


@dataclass
class NodeMetadata:
    source_id: str
    court: str
    court_level: str
    date_filed: date | None
    case_name: str
    citation_string: str    # e.g. "123 F.3d 456"
    is_good_law: bool = True
    overruled_by: str | None = None
    pagerank_score: float = 0.0


class CitationGraph:
    """
    Directed graph of legal citation relationships.

    Nodes: legal opinions / statutes (identified by source_id)
    Edges: citation relationships with treatment labels

    Provides:
    - good_law check: is an opinion still valid precedent?
    - authority score: PageRank-weighted citation authority
    - precedent chain: ancestors and descendants in citation tree
    - overruling detection: marks opinions overruled by later decisions

    In production this graph is persisted in PostgreSQL (see indexer.py).
    In memory it serves as a working index for the current session.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, NodeMetadata] = {}
        self._edges_out: dict[str, list[CitationEdge]] = defaultdict(list)   # citing → cited
        self._edges_in: dict[str, list[CitationEdge]] = defaultdict(list)    # cited → citing
        self._citation_str_to_id: dict[str, str] = {}  # "123 F.3d 456" → source_id

    def add_node(self, metadata: NodeMetadata) -> None:
        self._nodes[metadata.source_id] = metadata
        if metadata.citation_string:
            self._citation_str_to_id[metadata.citation_string] = metadata.source_id

    def add_edge(self, edge: CitationEdge) -> None:
        self._edges_out[edge.citing_id].append(edge)
        self._edges_in[edge.cited_id].append(edge)

        # Mark negative treatment immediately
        if edge.is_negative and edge.treatment in {"overruled", "overruled by"}:
            if edge.cited_id in self._nodes:
                self._nodes[edge.cited_id].is_good_law = False
                self._nodes[edge.cited_id].overruled_by = edge.citing_id
                logger.info(
                    "opinion_overruled",
                    cited=edge.cited_id,
                    by=edge.citing_id,
                )

    def is_good_law(self, source_id: str) -> bool:
        """Check whether an opinion is still valid (not overruled)."""
        node = self._nodes.get(source_id)
        if node is None:
            return True  # Unknown → assume valid (conservative)
        return node.is_good_law

    def get_citing_count(self, source_id: str) -> int:
        """How many opinions cite this one (in-degree)."""
        return len(self._edges_in.get(source_id, []))

    def get_precedents(self, source_id: str, depth: int = 2) -> list[str]:
        """
        BFS traversal of the citation graph to find precedents.
        Returns source_ids of opinions cited by this opinion (and their citations).
        """
        visited: set[str] = set()
        queue = [source_id]
        for _ in range(depth):
            next_queue: list[str] = []
            for nid in queue:
                for edge in self._edges_out.get(nid, []):
                    if edge.cited_id not in visited:
                        visited.add(edge.cited_id)
                        next_queue.append(edge.cited_id)
            queue = next_queue
        return list(visited)

    def compute_pagerank(self, damping: float = 0.85, iterations: int = 30) -> None:
        """
        Compute PageRank scores for all nodes.
        Higher score = more widely cited = greater authority.
        Updates NodeMetadata.pagerank_score in-place.
        """
        if not self._nodes:
            return

        n = len(self._nodes)
        ids = list(self._nodes.keys())
        scores = {nid: 1.0 / n for nid in ids}

        for _ in range(iterations):
            new_scores: dict[str, float] = {}
            for nid in ids:
                incoming = self._edges_in.get(nid, [])
                rank_sum = 0.0
                for edge in incoming:
                    if not edge.is_negative:  # negative citations don't pass authority
                        out_count = len(self._edges_out.get(edge.citing_id, [])) or 1
                        rank_sum += scores[edge.citing_id] / out_count
                new_scores[nid] = (1.0 - damping) / n + damping * rank_sum
            scores = new_scores

        # Normalize to [0, 1]
        max_score = max(scores.values()) if scores else 1.0
        for nid, score in scores.items():
            self._nodes[nid].pagerank_score = score / max_score

        logger.info("citation_pagerank_computed", node_count=n)

    def enrich_results(
        self,
        results: list[SearchResult],
        *,
        filter_bad_law: bool = True,
        boost_cited: bool = True,
        pagerank_alpha: float = 0.15,
    ) -> list[SearchResult]:
        """
        Enrich retrieval results using citation graph signals:
        1. Filter out-overruled opinions (if filter_bad_law=True)
        2. Boost scores of widely-cited opinions via PageRank

        Returns filtered and re-scored list.
        """
        enriched: list[SearchResult] = []
        for r in results:
            if filter_bad_law and not self.is_good_law(r.source_id):
                logger.info("bad_law_filtered", source_id=r.source_id)
                continue

            if boost_cited:
                node = self._nodes.get(r.source_id)
                if node and node.pagerank_score > 0:
                    boost = pagerank_alpha * node.pagerank_score
                    r.score = min(1.0, r.score + boost)
                    r.metadata["pagerank_score"] = round(node.pagerank_score, 4)

            # Annotate with citation signals
            citing_count = self.get_citing_count(r.source_id)
            r.metadata["times_cited"] = citing_count
            r.metadata["is_good_law"] = self.is_good_law(r.source_id)

            enriched.append(r)

        enriched.sort(key=lambda x: x.score, reverse=True)
        return enriched

    @staticmethod
    def parse_edge_from_context(
        citing_id: str,
        cited_id: str,
        context: str,
        date_cited: date | None = None,
    ) -> CitationEdge:
        """Infer treatment type from surrounding citation context text."""
        context_lower = context.lower()
        treatment = "cited"
        is_negative = False

        for neg in _NEGATIVE_TREATMENT:
            if neg in context_lower:
                treatment = neg
                is_negative = True
                break

        if not is_negative:
            for pos in _POSITIVE_TREATMENT:
                if pos in context_lower:
                    treatment = pos
                    break

        return CitationEdge(
            citing_id=citing_id,
            cited_id=cited_id,
            treatment=treatment,
            is_negative=is_negative,
            date_cited=date_cited,
            context_snippet=context[:200],
        )

    def __len__(self) -> int:
        return len(self._nodes)

    def __repr__(self) -> str:
        return (
            f"CitationGraph(nodes={len(self._nodes)}, "
            f"edges={sum(len(v) for v in self._edges_out.values())})"
        )
