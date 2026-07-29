"""Filter HF claims in staged passes and report accuracy after each pass.

Writes:
  artifacts/claims/claims_filtered.jsonl  (final)
  evaluation/reports/claim_filter_progression.json
  evaluation/reports/claim_filter_progression.md
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from scraper.eval.auto_judge import (
    HARD_TYPES,
    TYPE_CUES,
    _has_type_cues,
    _is_weak_span,
    aggregate_auto_metrics,
    heuristic_noise_score,
    heuristic_verdict,
)
from scraper.eval.sample_gold_candidates import CLAIM_TYPES
from scraper.io.jsonl import read_jsonl, write_jsonl
from scraper.paths import data_root
from scraper.process.create_claims import HF_DRUG_PATTERNS
from scraper.validation.claim_type_gates import passes_claim_type_gate_for_claim

# Explicit non-HF-primary / peripheral agents that dilute GraphRAG.
OFF_SCOPE_DRUG_TOKENS = (
    "metformin",
    "bempedoic",
    "colesevelam",
    "protamine",
    "heparin",
    "insulin",
    "atorvastatin",
    "rosuvastatin",
    "simvastatin",
    "ezetimibe",
    "nitroglycerin",
    "ticlopidine",
    "patiromer",
    "riociguat",
    "tadalafil",
    "treprostinil",
    "semaglutide",
    "liraglutide",
    "dulaglutide",
    "adempas",
    "inpefa",  # keep sotagliflozin via allowlist name; brand alone often PK noise
)

TRIAL_PK_DEVICE_PATTERNS = (
    re.compile(r"\brandomized\b", re.I),
    re.compile(r"\bplacebo\b", re.I),
    re.compile(r"\bn\s*=\s*\d+", re.I),
    re.compile(r"\bbaseline (egfr|weight|creatinine)\b", re.I),
    re.compile(r"\bhas not been studied\b", re.I),
    re.compile(r"\blimited (clinical )?experience\b", re.I),
    re.compile(r"\bit is not known\b", re.I),
    re.compile(r"\bNDC:\s*\d", re.I),
    re.compile(r"\bDOSAGE:\s*TABLET\b", re.I),
    re.compile(r"\bdo not use the pen\b", re.I),
    re.compile(r"\bprefilled (pen|syringe)\b", re.I),
    re.compile(r"\bpackaging is open\b", re.I),
    re.compile(r"\bmean baseline\b", re.I),
    re.compile(r"\bpediatric study\b", re.I),
    re.compile(r"\bcolored or cloudy\b", re.I),
    re.compile(r"\bparticulate matter\b", re.I),
    re.compile(r"\banimal (studies|reproduction|reproductive)\b", re.I),
    re.compile(r"\bpregnant rats\b", re.I),
    re.compile(r"\bmaternally toxic\b", re.I),
    re.compile(r"\be-cigarettes?\b", re.I),
    re.compile(r"\bexamine their feet\b", re.I),
    re.compile(r"\bWATCHMAN\b", re.I),
    re.compile(r"\bleft atrial appendage closure\b", re.I),
)

OFF_SCOPE_DRUG_TOKENS = (
    "metformin",
    "bempedoic",
    "colesevelam",
    "protamine",
    "heparin",
    "insulin",
    "atorvastatin",
    "rosuvastatin",
    "simvastatin",
    "ezetimibe",
    "nitroglycerin",
    "ticlopidine",
    "patiromer",
    "riociguat",
    "tadalafil",
    "treprostinil",
    "semaglutide",
    "liraglutide",
    "dulaglutide",
    "adempas",
    "inpefa",
    "esmolol",
    "epinephrine",
    "bosentan",
    "doxazosin",
    "argatroban",
    "andexanet",
    "azilsartan",
    "dronedarone",
    "fosinopril",
    "pravastatin",
    "isradipine",
    "procainamide",
    "metolazone",
    "icosapent",
    "timolol",
)

ACTIONABLE_CUES = (
    re.compile(r"\b(contraindicat|do not|must not|avoid|not recommended|discontinue|withhold)\b", re.I),
    re.compile(r"\b(monitor|check|measure|titrate|reduce|adjust|initiate|start)\b", re.I),
    re.compile(r"\b(egfr|crcl|creatinine|potassium|hyperkalemia)\b.{0,40}\b(<|>|≤|≥|less than|greater than|below|above|\d)", re.I),
)


def _drug_text(claim: dict[str, Any]) -> str:
    drug = claim.get("drug")
    if drug is None:
        return ""
    if isinstance(drug, dict):
        return json.dumps(drug, ensure_ascii=False).lower()
    return str(drug).lower().strip()


def _evidence(claim: dict[str, Any]) -> str:
    return str(claim.get("evidence") or claim.get("claim") or "")


def drop_type_mismatch(claim: dict[str, Any]) -> bool:
    ctype = claim.get("claim_type")
    if not ctype or ctype not in TYPE_CUES:
        return True
    return _has_type_cues(_evidence(claim), str(ctype))


def require_drug_on_hard(claim: dict[str, Any]) -> bool:
    ctype = claim.get("claim_type")
    if ctype not in HARD_TYPES:
        return True
    return bool(_drug_text(claim))


def drop_off_scope_drug(claim: dict[str, Any]) -> bool:
    text = f"{_drug_text(claim)} {_evidence(claim).lower()}"
    # Only drop when the *drug field* is off-scope, or drug empty but evidence
    # is clearly about an off-scope agent as the subject.
    drug = _drug_text(claim)
    if drug and any(tok in drug for tok in OFF_SCOPE_DRUG_TOKENS):
        return False
    if not drug and any(tok in text for tok in OFF_SCOPE_DRUG_TOKENS):
        # Keep HF safety text that merely mentions metformin etc. in passing
        # only if claim_type is guideline_recommendation with HF cues.
        hf_cues = ("heart failure", "hfref", "gdmt", "ejection fraction", "sglt2", "mra", "arni")
        if any(c in text for c in hf_cues):
            return True
        return False
    return True


def drop_noise_weak(claim: dict[str, Any]) -> bool:
    ev = _evidence(claim)
    if heuristic_noise_score(ev) >= 0.66:
        return False
    if _is_weak_span(ev):
        return False
    if len(ev.strip()) < 15:
        return False
    return True


def drop_trial_pk_device_noise(claim: dict[str, Any]) -> bool:
    ev = _evidence(claim)
    if any(p.search(ev) for p in TRIAL_PK_DEVICE_PATTERNS):
        # Keep only if clearly actionable clinical instruction remains.
        if not any(p.search(ev) for p in ACTIONABLE_CUES):
            return False
        # Trial arms / NDC blocks are almost never usable KG facts.
        if re.search(r"\bn\s*=\s*\d+", ev, flags=re.I) or "NDC:" in ev:
            return False
    return True


@lru_cache(maxsize=1)
def _hf_allowlist() -> set[str]:
    tokens: set[str] = set()
    for _pat, name in HF_DRUG_PATTERNS:
        tokens.add(str(name).lower().replace("_", " "))
        tokens.add(str(name).lower().replace("_", "/"))
        tokens.add(str(name).lower())
    scope = data_root() / "scope" / "gdmt_medication_groups.json"
    if scope.is_file():
        for group in json.loads(scope.read_text(encoding="utf-8")):
            for key in ("examples", "aliases"):
                for item in group.get(key) or []:
                    tokens.add(str(item).lower())
            if group.get("name"):
                tokens.add(str(group["name"]).lower())
    # Class tokens commonly stored in drug field.
    tokens.update(
        {
            "acei",
            "ace inhibitor",
            "arb",
            "arni",
            "mra",
            "sglt2i",
            "sglt2",
            "beta blocker",
            "beta_blocker",
            "loop diuretic",
            "loop_diuretic",
        }
    )
    return {t for t in tokens if len(t) >= 3}


def keep_hf_formulary_drug(claim: dict[str, Any]) -> bool:
    drug = _drug_text(claim)
    if not drug:
        # Guideline claims without drug OK if HF class language present.
        ev = _evidence(claim).lower()
        return any(
            tok in ev
            for tok in (
                "heart failure",
                "hfref",
                "hfpef",
                "gdmt",
                "ejection fraction",
                "sglt2",
                "mineralocorticoid",
                "neprilysin",
                "ace inhibitor",
                "angiotensin",
            )
        )
    allow = _hf_allowlist()
    if any(tok in drug for tok in allow):
        return True
    # Normalize separators.
    norm = drug.replace("-", " ").replace("/", " ")
    return any(tok in norm for tok in allow)


def require_actionable_hard(claim: dict[str, Any]) -> bool:
    """Hard/safety types need an actionable verb or numeric lab threshold."""
    ctype = claim.get("claim_type")
    if ctype not in HARD_TYPES and ctype not in {"adverse_reaction", "usage_constraint", "dose_recommendation"}:
        return True
    ev = _evidence(claim)
    return any(p.search(ev) for p in ACTIONABLE_CUES)


def drop_weak_dose_renal(claim: dict[str, Any]) -> bool:
    """Balanced gate aligned with create_claims / LLM extraction."""
    ctype = claim.get("claim_type")
    if ctype not in {"dose_recommendation", "renal_constraint"}:
        return True
    return passes_claim_type_gate_for_claim(claim)


PASS_SPECS: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
    ("0_baseline", lambda _c: True),
    ("1_type_evidence_gate", drop_type_mismatch),
    ("2_require_drug_hard_types", require_drug_on_hard),
    ("3_drop_off_scope_drugs", drop_off_scope_drug),
    ("4_drop_noise_weak_spans", drop_noise_weak),
    ("5_drop_trial_pk_device", drop_trial_pk_device_noise),
    # Milder than full formulary wipe: drop empty-drug ADR / interaction only.
    ("6_drop_empty_drug_weak_types", lambda c: not (
        c.get("claim_type") in {"adverse_reaction", "drug_interaction"} and not _drug_text(c)
    )),
    # ADR without actionable clinical verb is usually table noise.
    ("7_drop_nonactionable_adr", lambda c: (
        c.get("claim_type") != "adverse_reaction" or require_actionable_hard(c)
    )),
    ("8_drop_weak_dose_renal", drop_weak_dose_renal),
]


def stratified_sample(claims: list[dict[str, Any]], *, per_type: int, seed: int) -> list[dict[str, Any]]:
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        ctype = claim.get("claim_type")
        if ctype in CLAIM_TYPES:
            by_type[str(ctype)].append(claim)
    rng = random.Random(seed)
    sampled: list[dict[str, Any]] = []
    for ctype in CLAIM_TYPES:
        pool = by_type.get(ctype, [])
        rng.shuffle(pool)
        sampled.extend(pool[:per_type])
    return sampled


def corpus_quality(claims: list[dict[str, Any]]) -> dict[str, float]:
    """Deterministic quality rates on the full remaining corpus."""
    n = len(claims) or 1
    type_ok = sum(1 for c in claims if drop_type_mismatch(c))
    hard = [c for c in claims if c.get("claim_type") in HARD_TYPES]
    hard_n = len(hard) or 1
    hard_drug = sum(1 for c in hard if _drug_text(c))
    offscope = sum(1 for c in claims if not drop_off_scope_drug(c))
    return {
        "type_cue_rate": round(type_ok / n, 4),
        "hard_types_with_drug_rate": round(hard_drug / hard_n, 4),
        "offscope_rate": round(offscope / n, 4),
        "hard_types_n": len(hard),
    }


def sample_heuristic_precision(claims: list[dict[str, Any]], *, per_type: int, seed: int) -> dict[str, Any]:
    sample = stratified_sample(claims, per_type=per_type, seed=seed)
    judgments = []
    for claim in sample:
        judged = heuristic_verdict(claim)
        judgments.append(
            {
                "claim_type": claim.get("claim_type"),
                "verdict": judged["verdict"],
                "reasons": judged["reasons"],
            }
        )
    metrics = aggregate_auto_metrics(judgments)
    # Stricter proxy closer to the LLM audit: type cues required for accept.
    strict_accept = 0
    for claim in sample:
        ok = (
            drop_type_mismatch(claim)
            and drop_noise_weak(claim)
            and drop_off_scope_drug(claim)
            and drop_trial_pk_device_noise(claim)
            and drop_weak_dose_renal(claim)
        )
        if claim.get("claim_type") in HARD_TYPES:
            ok = ok and bool(_drug_text(claim))
        if claim.get("claim_type") in {"adverse_reaction", "drug_interaction"} and not _drug_text(claim):
            ok = False
        if claim.get("claim_type") == "adverse_reaction" and not require_actionable_hard(claim):
            ok = False
        if ok:
            strict_accept += 1
    metrics["strict_structural_precision"] = round(strict_accept / len(sample), 4) if sample else 0.0
    metrics["sampled"] = len(sample)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Staged claim filtering with accuracy progression.")
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--per-type", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/reports"))
    args = parser.parse_args()

    root = data_root()
    src = args.input or (root / "artifacts" / "claims" / "claims.jsonl")
    claims = read_jsonl(src)
    rows: list[dict[str, Any]] = []
    current = claims

    for pass_name, pred in PASS_SPECS:
        if pass_name == "0_baseline":
            current = claims
            dropped = 0
        else:
            before = len(current)
            current = [c for c in current if pred(c)]
            dropped = before - len(current)

        cq = corpus_quality(current)
        heur = sample_heuristic_precision(current, per_type=args.per_type, seed=args.seed)
        row = {
            "pass": pass_name,
            "claims_remaining": len(current),
            "dropped_this_pass": dropped,
            "retention_vs_baseline": round(len(current) / len(claims), 4) if claims else 0.0,
            "type_cue_rate": cq["type_cue_rate"],
            "hard_types_with_drug_rate": cq["hard_types_with_drug_rate"],
            "offscope_rate": cq["offscope_rate"],
            "heuristic_precision": heur["estimated_precision"],
            "heuristic_hard_precision": heur["hard_types"]["estimated_precision"],
            "strict_structural_precision": heur["strict_structural_precision"],
            "sample_n": heur["sampled"],
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

    out_claims = root / "artifacts" / "claims" / "claims_filtered.jsonl"
    write_jsonl(current, out_claims)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(src),
        "output_claims": str(out_claims),
        "baseline_n": len(claims),
        "final_n": len(current),
        "seed": args.seed,
        "per_type": args.per_type,
        "passes": rows,
        "note": (
            "strict_structural_precision = stratified sample share that passes "
            "type-cue + hard-drug + not-offscope + not-noise/weak. "
            "heuristic_precision uses auto_judge heuristics (often optimistic). "
            "Re-run LLM auto_eval on claims_filtered.jsonl for semantic acc."
        ),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "claim_filter_progression.json"
    md_path = args.output_dir / "claim_filter_progression.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    headers = [
        "Pass",
        "Claims left",
        "Dropped",
        "Retain %",
        "Type-cue %",
        "Hard+drug %",
        "Off-scope %",
        "Heuristic prec.",
        "Hard heur. prec.",
        "Strict struct. prec.",
    ]
    lines = [
        "# Claim filter accuracy progression",
        "",
        f"Input: `{src}`  ",
        f"Output: `{out_claims}`  ",
        f"Generated: {report['generated_at']}",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" if i == 0 else "---:" for i in range(len(headers))) + " |",
    ]
    for r in rows:
        lines.append(
            "| {pname} | {claims_remaining:,} | {dropped_this_pass:,} | {ret:.1%} | {type_cue_rate:.1%} | "
            "{hard_types_with_drug_rate:.1%} | {offscope_rate:.1%} | {heuristic_precision:.1%} | "
            "{heuristic_hard_precision:.1%} | {strict_structural_precision:.1%} |".format(
                pname=r["pass"],
                claims_remaining=r["claims_remaining"],
                dropped_this_pass=r["dropped_this_pass"],
                ret=r["retention_vs_baseline"],
                type_cue_rate=r["type_cue_rate"],
                hard_types_with_drug_rate=r["hard_types_with_drug_rate"],
                offscope_rate=r["offscope_rate"],
                heuristic_precision=r["heuristic_precision"],
                heuristic_hard_precision=r["heuristic_hard_precision"],
                strict_structural_precision=r["strict_structural_precision"],
            )
        )
    lines.extend(
        [
            "",
            "## How to read",
            "",
            "- **Strict struct. prec.** is the main accuracy proxy for this table (same gates as the filters).",
            "- **Heuristic prec.** matches `run_auto_eval --no-llm` and stays high even on noisy data.",
            "- For semantic LLM accuracy, run:",
            "",
            "```powershell",
            "py -m scraper.eval.run_auto_eval --input data/heart_failure/artifacts/claims/claims_filtered.jsonl --per-type 10",
            "```",
            "",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_claims}")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
