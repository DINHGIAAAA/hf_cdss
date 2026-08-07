"""Evaluate pipeline claims against the gold claim set."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scraper.io.jsonl import read_jsonl
from scraper.paths import data_root


POSITIVE_LABELS = {"valid_claim", "should_extract"}
NEGATIVE_LABELS = {"invalid_extraction"}


def _norm_text(value: str | None) -> str:
    text = (value or "").lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _token_set(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9]+", _norm_text(text)) if len(tok) > 2}


def evidence_similarity(a: str, b: str) -> float:
    """Jaccard token overlap — robust to light paraphrase / OCR noise."""
    ta, tb = _token_set(a), _token_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _drug_compatible(gold_drug: str | None, pred_drug: str | None) -> bool:
    if not gold_drug:
        return True
    if not pred_drug:
        return False
    g = _norm_text(gold_drug).replace(" ", "_")
    p = _norm_text(pred_drug).replace(" ", "_")
    return g == p or g in p or p in g


@dataclass
class MatchResult:
    gold: dict[str, Any]
    prediction: dict[str, Any] | None
    score: float
    matched: bool


def match_predictions_to_gold(
    gold_rows: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    *,
    min_similarity: float = 0.45,
) -> list[MatchResult]:
    # Index by document and drug so seed gold (canonical drug ids) can match labels.
    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_drug: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pred in predictions:
        by_doc[str(pred.get("document_id") or "")].append(pred)
        drug = _norm_text(str(pred.get("drug") or "")).replace(" ", "_")
        if drug:
            by_drug[drug].append(pred)

    results: list[MatchResult] = []
    for gold in gold_rows:
        label = gold.get("label")
        doc_id = str(gold.get("document_id") or "")
        candidates = list(by_doc.get(doc_id, []))
        gold_drug = _norm_text(str(gold.get("drug") or "")).replace(" ", "_")
        for key in {gold_drug, _norm_text(doc_id).replace(" ", "_")}:
            if not key:
                continue
            for pred in by_drug.get(key, []):
                if pred not in candidates:
                    candidates.append(pred)
        if not candidates and label in NEGATIVE_LABELS:
            candidates = predictions

        best: dict[str, Any] | None = None
        best_score = 0.0
        gold_evidence = str(gold.get("evidence") or "")
        gold_type = gold.get("claim_type")
        for pred in candidates:
            score = evidence_similarity(gold_evidence, str(pred.get("evidence") or pred.get("claim") or ""))
            if gold_type and pred.get("claim_type") == gold_type:
                score += 0.08
            if _drug_compatible(gold.get("drug"), pred.get("drug")):
                score += 0.05
            if score > best_score:
                best_score = score
                best = pred

        if label in POSITIVE_LABELS:
            matched = bool(
                best is not None
                and best_score >= min_similarity
                and (not gold_type or best.get("claim_type") == gold_type)
                and _drug_compatible(gold.get("drug"), best.get("drug") if best else None)
            )
        elif label in NEGATIVE_LABELS:
            # A "match" here means the pipeline incorrectly extracted something similar.
            matched = bool(best is not None and best_score >= min_similarity)
        else:
            matched = False

        results.append(
            MatchResult(
                gold=gold,
                prediction=best if best_score >= min_similarity else None,
                score=best_score,
                matched=matched,
            )
        )
    return results


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def compute_metrics(results: list[MatchResult]) -> dict[str, Any]:
    """
    Positive gold: matched => TP, unmatched => FN.
    Negative gold (invalid_extraction): matched => FP trap hit, unmatched => TN (good).
    FP from negatives counted in precision denominator via fp increment.
    """
    by_type: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    overall = {"tp": 0, "fp": 0, "fn": 0}
    hard_block = {"tp": 0, "fp": 0, "fn": 0}

    for item in results:
        gold = item.gold
        label = gold.get("label")
        claim_type = str(gold.get("claim_type") or "null")
        bucket_keys = [claim_type]
        if gold.get("safety_tier") == "hard_block":
            bucket_keys.append("__hard_block__")

        if label in POSITIVE_LABELS:
            if item.matched:
                overall["tp"] += 1
                by_type[claim_type]["tp"] += 1
                if gold.get("safety_tier") == "hard_block":
                    hard_block["tp"] += 1
            else:
                overall["fn"] += 1
                by_type[claim_type]["fn"] += 1
                if gold.get("safety_tier") == "hard_block":
                    hard_block["fn"] += 1
        elif label in NEGATIVE_LABELS:
            if item.matched:
                overall["fp"] += 1
                by_type[claim_type]["fp"] += 1
                if gold.get("safety_tier") == "hard_block":
                    hard_block["fp"] += 1

    per_type = {ctype: _prf(vals["tp"], vals["fp"], vals["fn"]) for ctype, vals in sorted(by_type.items())}
    return {
        "overall": _prf(overall["tp"], overall["fp"], overall["fn"]),
        "hard_block": _prf(hard_block["tp"], hard_block["fp"], hard_block["fn"]),
        "per_claim_type": per_type,
        "gold_positive": sum(1 for r in results if r.gold.get("label") in POSITIVE_LABELS),
        "gold_negative": sum(1 for r in results if r.gold.get("label") in NEGATIVE_LABELS),
        "matched_positives": sum(1 for r in results if r.gold.get("label") in POSITIVE_LABELS and r.matched),
        "noise_trap_hits": sum(1 for r in results if r.gold.get("label") in NEGATIVE_LABELS and r.matched),
    }


def filter_gold(
    rows: list[dict[str, Any]],
    *,
    statuses: set[str] | None,
) -> list[dict[str, Any]]:
    if not statuses:
        return rows
    return [row for row in rows if row.get("status") in statuses]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate claims.jsonl against evaluation/gold/claims_gold.jsonl")
    parser.add_argument("--gold", type=Path, default=Path("evaluation/gold/claims_gold.jsonl"))
    parser.add_argument(
        "--predictions",
        type=Path,
        default=None,
        help="Default: data_root/artifacts/claims/claims.jsonl",
    )
    parser.add_argument(
        "--status",
        action="append",
        default=None,
        help="Repeatable. Default: draft+reviewed+approved. Use --status approved for clinician-signed only.",
    )
    parser.add_argument("--min-similarity", type=float, default=0.45)
    parser.add_argument("--show-misses", action="store_true")
    args = parser.parse_args()

    statuses = set(args.status) if args.status else {"draft", "reviewed", "approved"}
    gold_rows = filter_gold(read_jsonl(args.gold), statuses=statuses)
    pred_path = args.predictions or (data_root() / "artifacts" / "claims" / "claims.jsonl")
    predictions = read_jsonl(pred_path)

    results = match_predictions_to_gold(gold_rows, predictions, min_similarity=args.min_similarity)
    metrics = compute_metrics(results)
    metrics["gold_file"] = str(args.gold)
    metrics["predictions_file"] = str(pred_path)
    metrics["statuses"] = sorted(statuses)
    metrics["min_similarity"] = args.min_similarity

    print(json.dumps(metrics, indent=2, ensure_ascii=False))

    if args.show_misses:
        print("\n# Misses / noise hits")
        for item in results:
            label = item.gold.get("label")
            if label in POSITIVE_LABELS and not item.matched:
                print(
                    f"FN {item.gold.get('gold_id')} type={item.gold.get('claim_type')} "
                    f"drug={item.gold.get('drug')} best_score={item.score:.2f}"
                )
            if label in NEGATIVE_LABELS and item.matched:
                print(
                    f"FP-trap {item.gold.get('gold_id')} matched_claim={item.prediction.get('claim_id') if item.prediction else None} "
                    f"score={item.score:.2f}"
                )


if __name__ == "__main__":
    main()
