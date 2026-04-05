"""
Offline evaluation framework for the IndyLeg legal RAG system.

Implements standard IR + RAG evaluation metrics:

Retrieval Quality:
  - Recall@K    — fraction of relevant docs retrieved in top-K
  - Precision@K — fraction of retrieved docs that are relevant
  - MRR         — Mean Reciprocal Rank (position of first relevant doc)
  - NDCG@K      — Normalized Discounted Cumulative Gain (graded relevance)

Generation Quality:
  - Citation Accuracy — what percentage of output citations map to real sources
  - Faithfulness      — do claims in the answer appear in the retrieved context?
  - Answer Coverage   — does the answer address the key aspects of the question?

Usage:
    from retrieval.evaluator import RAGEvaluator, EvalDataset, EvalExample

    dataset = EvalDataset.from_json("tests/data/eval_queries.json")
    evaluator = RAGEvaluator(searcher, reranker, generator)
    report = await evaluator.evaluate(dataset)
    report.print_summary()
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)


# ── Evaluation Dataset ─────────────────────────────────────────────────────────


@dataclass
class EvalExample:
    """
    A single evaluation query with known-good answers.

    Fields
    ------
    query_id:           Unique ID for this evaluation example
    query:              The raw legal question
    relevant_source_ids: Ground-truth set of source IDs that should be retrieved
    graded_relevance:   Optional source_id → relevance_grade (0/1/2/3) for NDCG
    expected_citations: Citations that must appear in a correct answer
    jurisdiction:       Optional filter to apply during retrieval
    notes:              Human annotation notes
    """

    query_id: str
    query: str
    relevant_source_ids: list[str]
    graded_relevance: dict[str, int] = field(default_factory=dict)
    expected_citations: list[str] = field(default_factory=list)
    jurisdiction: str | None = None
    notes: str = ""


@dataclass
class EvalDataset:
    examples: list[EvalExample]
    name: str = "unnamed"
    created_by: str = ""
    description: str = ""

    @classmethod
    def from_json(cls, path: str | Path) -> EvalDataset:
        """Load evaluation dataset from a JSON file."""
        with open(path) as f:
            data = json.load(f)

        examples = [
            EvalExample(
                query_id=item["query_id"],
                query=item["query"],
                relevant_source_ids=item["relevant_source_ids"],
                graded_relevance=item.get("graded_relevance", {}),
                expected_citations=item.get("expected_citations", []),
                jurisdiction=item.get("jurisdiction"),
                notes=item.get("notes", ""),
            )
            for item in data["examples"]
        ]

        return cls(
            examples=examples,
            name=data.get("name", ""),
            created_by=data.get("created_by", ""),
            description=data.get("description", ""),
        )

    def to_json(self, path: str | Path) -> None:
        """Persist evaluation dataset to JSON."""
        data: dict[str, Any] = {
            "name": self.name,
            "created_by": self.created_by,
            "description": self.description,
            "examples": [
                {
                    "query_id": ex.query_id,
                    "query": ex.query,
                    "relevant_source_ids": ex.relevant_source_ids,
                    "graded_relevance": ex.graded_relevance,
                    "expected_citations": ex.expected_citations,
                    "jurisdiction": ex.jurisdiction,
                    "notes": ex.notes,
                }
                for ex in self.examples
            ],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


# ── Per-example result ─────────────────────────────────────────────────────────


@dataclass
class ExampleResult:
    query_id: str
    query: str
    retrieved_ids: list[str]
    generated_answer: str
    cited_ids: list[str]
    recall_at_k: dict[int, float]
    precision_at_k: dict[int, float]
    reciprocal_rank: float
    ndcg_at_k: dict[int, float]
    citation_accuracy: float
    faithfulness_score: float
    # Raw signals for debugging
    relevant_ids: list[str]
    missing_relevant: list[str]  # relevant docs NOT retrieved in top-K
    hallucinated_citations: list[str]


# ── Aggregate report ───────────────────────────────────────────────────────────


@dataclass
class EvaluationReport:
    dataset_name: str
    num_examples: int
    k_values: list[int]
    mean_recall_at_k: dict[int, float]
    mean_precision_at_k: dict[int, float]
    mrr: float
    mean_ndcg_at_k: dict[int, float]
    mean_citation_accuracy: float
    mean_faithfulness: float
    per_example: list[ExampleResult]
    metadata: dict[str, Any] = field(default_factory=dict)

    def print_summary(self) -> None:
        """Print a concise evaluation summary to stdout."""
        print(f"\n{'=' * 60}")
        print(f"EVALUATION REPORT — {self.dataset_name}")
        print(f"{'=' * 60}")
        print(f"Examples evaluated : {self.num_examples}")
        print(f"MRR                : {self.mrr:.4f}")
        for k in self.k_values:
            print(
                f"Recall@{k:<3}          : {self.mean_recall_at_k.get(k, 0):.4f}  "
                f"Precision@{k:<3}: {self.mean_precision_at_k.get(k, 0):.4f}  "
                f"NDCG@{k:<3}: {self.mean_ndcg_at_k.get(k, 0):.4f}"
            )
        print(f"Citation Accuracy  : {self.mean_citation_accuracy:.4f}")
        print(f"Faithfulness       : {self.mean_faithfulness:.4f}")
        print(f"{'=' * 60}\n")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset_name,
            "num_examples": self.num_examples,
            "mrr": round(self.mrr, 4),
            "recall_at_k": {str(k): round(v, 4) for k, v in self.mean_recall_at_k.items()},
            "precision_at_k": {str(k): round(v, 4) for k, v in self.mean_precision_at_k.items()},
            "ndcg_at_k": {str(k): round(v, 4) for k, v in self.mean_ndcg_at_k.items()},
            "citation_accuracy": round(self.mean_citation_accuracy, 4),
            "faithfulness": round(self.mean_faithfulness, 4),
        }


# ── Core metric functions ──────────────────────────────────────────────────────


def recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """Fraction of relevant documents retrieved in the top-K results."""
    if not relevant:
        return 1.0  # vacuously true
    top_k = set(retrieved[:k])
    return len(top_k & set(relevant)) / len(relevant)


def precision_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """Fraction of top-K retrieved documents that are relevant."""
    if k == 0:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for doc in top_k if doc in set(relevant))
    return hits / k


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    """1 / rank_of_first_relevant_document. 0 if no relevant doc is retrieved."""
    for i, doc_id in enumerate(retrieved, start=1):
        if doc_id in relevant:
            return 1.0 / i
    return 0.0


def dcg_at_k(retrieved: list[str], graded: dict[str, int], k: int) -> float:
    """Discounted Cumulative Gain at K."""
    dcg = 0.0
    for i, doc_id in enumerate(retrieved[:k], start=1):
        rel = graded.get(doc_id, 0)
        dcg += (2**rel - 1) / math.log2(i + 1)
    return dcg


def ndcg_at_k(retrieved: list[str], graded: dict[str, int], k: int) -> float:
    """Normalized DCG at K."""
    ideal_order = sorted(graded.values(), reverse=True)[:k]
    idcg: float = sum(((2**rel - 1) / math.log2(i + 2) for i, rel in enumerate(ideal_order)), 0.0)
    if idcg == 0:
        return 0.0
    return dcg_at_k(retrieved, graded, k) / idcg


def citation_accuracy(cited_ids: list[str], retrieved_ids: list[str]) -> float:
    """
    Fraction of citations in the generated answer that point to retrieved sources.
    Hallucinated citations (not in retrieved set) reduce this score.
    """
    if not cited_ids:
        return 1.0  # No citations → no hallucinations (but may flag as warning)
    retrieved_set = set(retrieved_ids)
    valid = sum(1 for cid in cited_ids if cid in retrieved_set)
    return valid / len(cited_ids)


def faithfulness_score(answer: str, retrieved_texts: list[str]) -> float:
    """
    Heuristic faithfulness: estimate if the answer claims are grounded in context.

    Method: extract key noun phrases / legal terms from the answer, check what
    fraction appear in the retrieved context. This is an approximation — a full
    implementation uses an NLI model for entailment checking.

    In production, replace this with a Bedrock-powered entailment check:
      "Does the following text [context] entail [claim]? Answer Yes/No."
    """
    if not answer or not retrieved_texts:
        return 0.0

    # Extract legal-specific noun phrases as "claims"
    import re

    claim_pattern = re.compile(
        r"(?:Ind(?:iana)?\.?\s*Code\s*§\s*[\d\-\.]+|"
        r"\d+\s+(?:F\.\d+|Ind\.?|N\.E\.(?:2d|3d)?)\s+\d+|"
        r"\b[A-Z][a-z]+\s+v\.\s+[A-Z][a-z]+)",
    )
    claims = claim_pattern.findall(answer)
    if not claims:
        # Fall back to key legal terms
        legal_terms = re.findall(
            r"\b(?:statute|section|holding|court|affirmed|reversed|remanded|enjoined|convicted)\b",
            answer.lower(),
        )
        claims = legal_terms

    if not claims:
        return 0.5  # Ambiguous — neutral score

    combined_context = " ".join(retrieved_texts).lower()
    grounded = sum(1 for claim in claims if claim.lower() in combined_context)
    return grounded / len(claims)


# ── RAG Evaluator ─────────────────────────────────────────────────────────────


class RAGEvaluator:
    """
    End-to-end RAG evaluator.

    Runs the full pipeline (embed → search → rerank → generate) for each
    evaluation example and computes all metrics.

    Usage (async):
        evaluator = RAGEvaluator(embedder, searcher, reranker, generator)
        report = await evaluator.evaluate(dataset, k_values=[1, 5, 10])
    """

    def __init__(
        self,
        embedder: Any,
        searcher: Any,
        reranker: Any,
        generator: Any,
        k_values: list[int] | None = None,
    ) -> None:
        self._embedder = embedder
        self._searcher = searcher
        self._reranker = reranker
        self._generator = generator
        self._k_values = k_values or [1, 5, 10]

    async def evaluate(
        self,
        dataset: EvalDataset,
        generate_answers: bool = True,
    ) -> EvaluationReport:
        """
        Run evaluation across all examples in the dataset.

        Parameters
        ----------
        dataset:          EvalDataset with labeled queries
        generate_answers: If False, skip generation and only evaluate retrieval.
                          Set to False for fast retrieval-only eval runs.
        """
        results: list[ExampleResult] = []

        for example in dataset.examples:
            result = await self._evaluate_example(example, generate_answers)
            results.append(result)
            logger.info(
                "eval_example_done",
                query_id=example.query_id,
                mrr=round(result.reciprocal_rank, 3),
                recall_5=round(result.recall_at_k.get(5, 0), 3),
            )

        report = self._aggregate(dataset.name, results)
        logger.info(
            "eval_complete",
            dataset=dataset.name,
            mrr=round(report.mrr, 4),
            recall_5=round(report.mean_recall_at_k.get(5, 0), 4),
            citation_accuracy=round(report.mean_citation_accuracy, 4),
        )
        return report

    async def _evaluate_example(
        self, example: EvalExample, generate_answers: bool
    ) -> ExampleResult:
        from retrieval.query_parser import parse_legal_query

        parsed = parse_legal_query(example.query)
        query_vector = await self._embedder.embed_query(parsed.normalized)

        candidates = await self._searcher.search(
            query_vector=query_vector,
            query_text=parsed.normalized,
            jurisdiction=example.jurisdiction or parsed.jurisdiction,
            case_type=parsed.case_type,
        )

        ranked = await self._reranker.rerank(parsed.normalized, candidates)
        retrieved_ids = [r.source_id for r in ranked]

        answer = ""
        cited_ids: list[str] = []
        if generate_answers:
            gen_result = await self._generator.generate(
                query=example.query,
                context_chunks=ranked,
                jurisdiction=example.jurisdiction,
            )
            answer = gen_result.answer
            cited_ids = gen_result.validation.cited_source_ids

        relevant_set = set(example.relevant_source_ids)
        max_k = max(self._k_values)

        recall = {
            k: recall_at_k(retrieved_ids, example.relevant_source_ids, k) for k in self._k_values
        }
        precision = {
            k: precision_at_k(retrieved_ids, example.relevant_source_ids, k) for k in self._k_values
        }

        # Use graded_relevance if available; otherwise binary
        graded = example.graded_relevance or {sid: 1 for sid in example.relevant_source_ids}
        ndcg = {k: ndcg_at_k(retrieved_ids, graded, k) for k in self._k_values}
        rr = reciprocal_rank(retrieved_ids, relevant_set)

        cite_acc = citation_accuracy(cited_ids, retrieved_ids)
        faith = faithfulness_score(answer, [r.content for r in ranked[:5]])

        missing = [sid for sid in example.relevant_source_ids if sid not in retrieved_ids[:max_k]]
        hallucinated = [cid for cid in cited_ids if cid not in set(retrieved_ids)]

        return ExampleResult(
            query_id=example.query_id,
            query=example.query,
            retrieved_ids=retrieved_ids,
            generated_answer=answer,
            cited_ids=cited_ids,
            recall_at_k=recall,
            precision_at_k=precision,
            reciprocal_rank=rr,
            ndcg_at_k=ndcg,
            citation_accuracy=cite_acc,
            faithfulness_score=faith,
            relevant_ids=example.relevant_source_ids,
            missing_relevant=missing,
            hallucinated_citations=hallucinated,
        )

    def _aggregate(self, dataset_name: str, results: list[ExampleResult]) -> EvaluationReport:
        n = len(results)
        if n == 0:
            return EvaluationReport(
                dataset_name=dataset_name,
                num_examples=0,
                k_values=self._k_values,
                mean_recall_at_k={},
                mean_precision_at_k={},
                mrr=0.0,
                mean_ndcg_at_k={},
                mean_citation_accuracy=0.0,
                mean_faithfulness=0.0,
                per_example=[],
            )

        mean_recall = {k: sum(r.recall_at_k.get(k, 0) for r in results) / n for k in self._k_values}
        mean_precision = {
            k: sum(r.precision_at_k.get(k, 0) for r in results) / n for k in self._k_values
        }
        mean_ndcg = {k: sum(r.ndcg_at_k.get(k, 0) for r in results) / n for k in self._k_values}
        mrr = sum(r.reciprocal_rank for r in results) / n
        mean_cite_acc = sum(r.citation_accuracy for r in results) / n
        mean_faith = sum(r.faithfulness_score for r in results) / n

        return EvaluationReport(
            dataset_name=dataset_name,
            num_examples=n,
            k_values=self._k_values,
            mean_recall_at_k=mean_recall,
            mean_precision_at_k=mean_precision,
            mrr=mrr,
            mean_ndcg_at_k=mean_ndcg,
            mean_citation_accuracy=mean_cite_acc,
            mean_faithfulness=mean_faith,
            per_example=results,
        )
