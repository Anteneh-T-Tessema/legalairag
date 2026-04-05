"""Unit tests for retrieval.evaluator metric functions."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from retrieval.evaluator import (
    EvalDataset,
    EvalExample,
    EvaluationReport,
    ExampleResult,
    RAGEvaluator,
    citation_accuracy,
    dcg_at_k,
    faithfulness_score,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

# ── recall_at_k ───────────────────────────────────────────────────────────────


def test_recall_all_retrieved():
    assert recall_at_k(["a", "b"], ["a", "b"], k=2) == 1.0


def test_recall_first_hit_only():
    # 1 of 2 relevant docs retrieved in top-1
    assert recall_at_k(["a", "x"], ["a", "b"], k=1) == pytest.approx(0.5)


def test_recall_no_hits():
    assert recall_at_k(["x", "y"], ["a", "b"], k=2) == 0.0


def test_recall_empty_relevant_vacuously_true():
    assert recall_at_k(["a"], [], k=5) == 1.0


def test_recall_k_truncates_retrieved_list():
    # "a" is at position 2 but k=1 only checks position 1
    assert recall_at_k(["x", "a"], ["a"], k=1) == 0.0


def test_recall_k_larger_than_retrieved():
    assert recall_at_k(["a"], ["a", "b"], k=100) == pytest.approx(0.5)


# ── precision_at_k ────────────────────────────────────────────────────────────


def test_precision_perfect():
    assert precision_at_k(["a", "b"], ["a", "b"], k=2) == 1.0


def test_precision_half():
    assert precision_at_k(["a", "x"], ["a"], k=2) == 0.5


def test_precision_none_relevant():
    assert precision_at_k(["x", "y"], ["a"], k=2) == 0.0


def test_precision_k_zero_returns_zero():
    assert precision_at_k(["a"], ["a"], k=0) == 0.0


def test_precision_counts_only_top_k():
    # positoin 3 has "b" but k=2 → not counted
    assert precision_at_k(["x", "x", "b"], ["b"], k=2) == 0.0


# ── reciprocal_rank ───────────────────────────────────────────────────────────


def test_rr_first_position():
    assert reciprocal_rank(["a", "b"], {"a"}) == 1.0


def test_rr_second_position():
    assert reciprocal_rank(["x", "a"], {"a"}) == pytest.approx(0.5)


def test_rr_third_position():
    assert reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)


def test_rr_none_relevant():
    assert reciprocal_rank(["x", "y"], {"a"}) == 0.0


def test_rr_multiple_relevant_uses_first_found():
    # "b" is at rank 2, "a" at rank 3 → MRR = 0.5
    assert reciprocal_rank(["x", "b", "a"], {"a", "b"}) == pytest.approx(0.5)


# ── dcg_at_k ──────────────────────────────────────────────────────────────────


def test_dcg_single_perfect():
    # rel=3, at rank 1: (2^3-1)/log2(2) = 7/1 = 7
    assert dcg_at_k(["a"], {"a": 3}, k=1) == pytest.approx(7.0)


def test_dcg_irrelevant_docs_zero():
    assert dcg_at_k(["x", "y"], {"a": 3}, k=2) == 0.0


def test_dcg_degrades_with_rank():
    # rel=1 at rank 1 vs rank 2
    dcg1 = dcg_at_k(["a"], {"a": 1}, k=1)
    dcg2 = dcg_at_k(["x", "a"], {"a": 1}, k=2)
    assert dcg1 > dcg2


# ── ndcg_at_k ─────────────────────────────────────────────────────────────────


def test_ndcg_ideal_order_is_1():
    graded = {"a": 3, "b": 2, "c": 1}
    assert ndcg_at_k(["a", "b", "c"], graded, k=3) == pytest.approx(1.0)


def test_ndcg_all_irrelevant_is_0():
    graded = {"a": 0, "b": 0}
    assert ndcg_at_k(["a", "b"], graded, k=2) == 0.0


def test_ndcg_no_graded_docs():
    # No relevance for anything retrieved → IDCG=0 → 0
    assert ndcg_at_k(["x"], {}, k=1) == 0.0


def test_ndcg_partial_hit_between_0_and_1():
    graded = {"a": 3, "b": 2}
    score = ndcg_at_k(["b", "x"], graded, k=2)
    assert 0.0 < score < 1.0


def test_ndcg_single_relevant_first_position():
    # If only one relevant doc, having it first = perfect NDCG
    graded = {"a": 1}
    assert ndcg_at_k(["a"], graded, k=1) == pytest.approx(1.0)


# ── citation_accuracy ─────────────────────────────────────────────────────────


def test_citation_accuracy_all_valid():
    assert citation_accuracy(["a", "b"], ["a", "b", "c"]) == 1.0


def test_citation_accuracy_all_hallucinated():
    assert citation_accuracy(["z"], ["a", "b"]) == 0.0


def test_citation_accuracy_half():
    assert citation_accuracy(["a", "z"], ["a", "b"]) == pytest.approx(0.5)


def test_citation_accuracy_no_citations():
    assert citation_accuracy([], ["a"]) == 1.0


def test_citation_accuracy_empty_retrieved():
    # Citations with nothing retrieved → all hallucinated
    assert citation_accuracy(["a"], []) == 0.0


# ── faithfulness_score ────────────────────────────────────────────────────────


def test_faithfulness_empty_answer():
    assert faithfulness_score("", ["some context"]) == 0.0


def test_faithfulness_empty_context():
    assert faithfulness_score("some answer", []) == 0.0


def test_faithfulness_statute_ref_in_context():
    answer = "Under Ind. Code § 35-42-1-1, this applies."
    context = ["Ind. Code § 35-42-1-1 defines murder in Indiana."]
    score = faithfulness_score(answer, context)
    assert score == pytest.approx(1.0)


def test_faithfulness_legal_terms_grounded():
    answer = "The court affirmed the conviction and remanded for sentencing."
    context = ["The court affirmed and remanded the convicted defendant."]
    score = faithfulness_score(answer, context)
    assert score > 0.0


def test_faithfulness_no_claims_neutral():
    # Answer with no recognisable legal patterns → neutral 0.5
    answer = "blah blah blah"
    context = ["something completely different"]
    score = faithfulness_score(answer, context)
    assert score == pytest.approx(0.5)


# ── EvalDataset ───────────────────────────────────────────────────────────────


def _make_dataset_json(path: Path) -> None:
    data = {
        "name": "test-dataset",
        "created_by": "tester",
        "description": "Unit test dataset",
        "examples": [
            {
                "query_id": "q1",
                "query": "What is battery in Indiana?",
                "relevant_source_ids": ["src-1", "src-2"],
                "graded_relevance": {"src-1": 3, "src-2": 1},
                "expected_citations": ["I.C. 35-42-2-1"],
                "jurisdiction": "Indiana",
                "notes": "test note",
            }
        ],
    }
    path.write_text(json.dumps(data))


def test_eval_dataset_from_json():
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        tmp = Path(f.name)
    _make_dataset_json(tmp)

    dataset = EvalDataset.from_json(tmp)
    assert dataset.name == "test-dataset"
    assert len(dataset.examples) == 1
    ex = dataset.examples[0]
    assert ex.query_id == "q1"
    assert ex.graded_relevance == {"src-1": 3, "src-2": 1}
    assert ex.jurisdiction == "Indiana"
    tmp.unlink()


def test_eval_dataset_to_json_round_trip():
    example = EvalExample(
        query_id="q2",
        query="What does Ind. Code § 35-42-1-1 say?",
        relevant_source_ids=["src-3"],
        graded_relevance={"src-3": 2},
        expected_citations=["I.C. 35-42-1-1"],
        jurisdiction="Indiana",
        notes="",
    )
    dataset = EvalDataset(examples=[example], name="round-trip", created_by="dev")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = Path(f.name)

    dataset.to_json(tmp)
    reloaded = EvalDataset.from_json(tmp)

    assert reloaded.name == "round-trip"
    assert reloaded.examples[0].query_id == "q2"
    tmp.unlink()


# ── EvaluationReport ──────────────────────────────────────────────────────────


def _make_report(num_examples: int = 2) -> EvaluationReport:
    results = [
        ExampleResult(
            query_id=f"q{i}",
            query=f"query {i}",
            retrieved_ids=["src-1", "src-2"],
            generated_answer="The court held this.",
            cited_ids=["src-1"],
            recall_at_k={5: 0.8},
            precision_at_k={5: 0.4},
            reciprocal_rank=1.0,
            ndcg_at_k={5: 0.9},
            citation_accuracy=1.0,
            faithfulness_score=0.7,
            relevant_ids=["src-1"],
            missing_relevant=[],
            hallucinated_citations=[],
        )
        for i in range(num_examples)
    ]
    return EvaluationReport(
        dataset_name="test",
        num_examples=num_examples,
        k_values=[5],
        mean_recall_at_k={5: 0.8},
        mean_precision_at_k={5: 0.4},
        mrr=1.0,
        mean_ndcg_at_k={5: 0.9},
        mean_citation_accuracy=1.0,
        mean_faithfulness=0.7,
        per_example=results,
    )


def test_evaluation_report_print_summary(capsys):
    report = _make_report()
    report.print_summary()
    captured = capsys.readouterr()
    assert "EVALUATION REPORT" in captured.out
    assert "MRR" in captured.out
    assert "Citation Accuracy" in captured.out


def test_evaluation_report_to_dict():
    report = _make_report()
    d = report.to_dict()
    assert d["dataset"] == "test"
    assert "mrr" in d
    assert "recall_at_k" in d
    assert "citation_accuracy" in d


# ── RAGEvaluator ──────────────────────────────────────────────────────────────


def _make_evaluator() -> RAGEvaluator:
    mock_chunk = MagicMock()
    mock_chunk.source_id = "src-1"
    mock_chunk.content = "The Indiana Supreme Court held that battery requires touch."

    gen_result = MagicMock()
    gen_result.answer = "The court held that battery was proven."
    gen_result.validation.cited_source_ids = ["src-1"]

    embedder = MagicMock()
    embedder.embed_query = AsyncMock(return_value=[0.1] * 128)
    searcher = MagicMock()
    searcher.search = AsyncMock(return_value=[mock_chunk])
    reranker = MagicMock()
    reranker.rerank = AsyncMock(return_value=[mock_chunk])
    generator = MagicMock()
    generator.generate = AsyncMock(return_value=gen_result)

    return RAGEvaluator(embedder, searcher, reranker, generator, k_values=[1, 5])


@pytest.mark.asyncio
async def test_rag_evaluator_evaluate_returns_report():
    evaluator = _make_evaluator()
    example = EvalExample(
        query_id="q1",
        query="What is battery under Indiana law?",
        relevant_source_ids=["src-1"],
        jurisdiction="Indiana",
    )
    dataset = EvalDataset(examples=[example], name="test-eval")

    report = await evaluator.evaluate(dataset)

    assert report.num_examples == 1
    assert report.mrr == pytest.approx(1.0)
    assert 1 in report.mean_recall_at_k or 5 in report.mean_recall_at_k


@pytest.mark.asyncio
async def test_rag_evaluator_evaluate_skip_generation():
    evaluator = _make_evaluator()
    example = EvalExample(
        query_id="q2",
        query="battery Indiana",
        relevant_source_ids=["src-1"],
    )
    dataset = EvalDataset(examples=[example], name="retrieval-only")

    report = await evaluator.evaluate(dataset, generate_answers=False)

    assert report.num_examples == 1
    # generator should NOT have been called
    evaluator._generator.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_rag_evaluator_aggregate_empty_returns_zero_report():
    evaluator = _make_evaluator()
    dataset = EvalDataset(examples=[], name="empty")

    report = await evaluator.evaluate(dataset)

    assert report.num_examples == 0
    assert report.mrr == 0.0
    assert report.mean_citation_accuracy == 0.0
