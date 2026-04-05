"""Retrieval – hybrid search, indexing, reranking, authority scoring."""

from retrieval.authority import AuthorityRanker, CitationGraph
from retrieval.evaluator import RAGEvaluator
from retrieval.hybrid_search import HybridSearcher, SearchResult
from retrieval.indexer import VectorIndexer
from retrieval.query_parser import ParsedQuery, parse_legal_query
from retrieval.reranker import CrossEncoderReranker

__all__ = [
    "AuthorityRanker",
    "CitationGraph",
    "CrossEncoderReranker",
    "HybridSearcher",
    "ParsedQuery",
    "RAGEvaluator",
    "SearchResult",
    "VectorIndexer",
    "parse_legal_query",
]
