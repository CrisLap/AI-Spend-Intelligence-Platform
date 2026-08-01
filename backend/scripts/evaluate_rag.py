"""
RAG evaluation script using RAGAS-inspired metrics.

Evaluates retrieval precision, answer relevance, and faithfulness
of the spend intelligence RAG pipeline against a curated test set.

Usage:
    python scripts/evaluate_rag.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ai import cosine_similarity, embed_text
from app.services.chat_service import _retrieve_context, answer_question

TEST_CASES = [
    {
        "question": "How much did we spend on toner?",
        "expected_keywords": ["toner"],
        "expected_source": "toner",
    },
    {
        "question": "Show me all consulting purchases",
        "expected_keywords": ["consulting", "consultancy"],
    },
    {
        "question": "Which suppliers have the highest spend?",
        "expected_keywords": ["supplier"],
    },
]


def evaluate_retrieval_precision(test_cases: list[dict]) -> dict:
    scores = []
    for tc in test_cases:
        ctx = _retrieve_context(tc["question"], top_k=5)
        if not ctx:
            scores.append(0.0)
            continue
        q_vec = embed_text(tc["question"])
        relevances = []
        for c in ctx:
            c_vec = embed_text(c["text"])
            relevances.append(cosine_similarity(q_vec, c_vec))
        avg_rel = sum(relevances) / len(relevances) if relevances else 0.0
        keyword_hit = any(
            kw.lower() in " ".join(c["text"] for c in ctx).lower()
            for kw in tc.get("expected_keywords", [])
        )
        scores.append(avg_rel * (1.0 if keyword_hit else 0.5))
    return {
        "metric": "retrieval_precision",
        "score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "num_cases": len(test_cases),
    }


def evaluate_answer_relevance(test_cases: list[dict]) -> dict:
    scores = []
    for tc in test_cases:
        result = answer_question(tc["question"], session_id=None, user_id=1)
        reply = result.get("reply", "")
        if not reply:
            scores.append(0.0)
            continue
        q_vec = embed_text(tc["question"])
        a_vec = embed_text(reply)
        relevance = cosine_similarity(q_vec, a_vec)
        keyword_hit = any(
            kw.lower() in reply.lower()
            for kw in tc.get("expected_keywords", [])
        )
        scores.append(relevance * (1.0 if keyword_hit else 0.6))
    return {
        "metric": "answer_relevance",
        "score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "num_cases": len(test_cases),
    }


def evaluate_faithfulness(test_cases: list[dict]) -> dict:
    scores = []
    for tc in test_cases:
        result = answer_question(tc["question"], session_id=None, user_id=1)
        reply = result.get("reply", "")
        sources = result.get("sources", [])
        if not reply or not sources:
            scores.append(0.0)
            continue
        reply_vec = embed_text(reply)
        source_vecs = [embed_text(s["text"]) for s in sources if s.get("text")]
        if not source_vecs:
            scores.append(0.0)
            continue
        faithfulness = max(cosine_similarity(reply_vec, sv) for sv in source_vecs)
        scores.append(faithfulness)
    return {
        "metric": "faithfulness",
        "score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "num_cases": len(test_cases),
    }


def main():
    print("=" * 55)
    print("  RAG Evaluation - AI Spend Intelligence Platform")
    print("=" * 55)

    if not TEST_CASES:
        print("\nNo test cases defined. Add question/answer pairs to TEST_CASES.")
        return

    print(f"\nTest cases: {len(TEST_CASES)}")

    retrieval = evaluate_retrieval_precision(TEST_CASES)
    relevance = evaluate_answer_relevance(TEST_CASES)
    faithfulness = evaluate_faithfulness(TEST_CASES)

    print(f"\n  retrieval_precision : {retrieval['score']}")
    print(f"  answer_relevance    : {relevance['score']}")
    print(f"  faithfulness        : {faithfulness['score']}")

    avg = (retrieval["score"] + relevance["score"] + faithfulness["score"]) / 3
    print(f"\n  Overall RAG score   : {avg:.4f}")
    print(f"\n{'=' * 55}")


if __name__ == "__main__":
    main()
