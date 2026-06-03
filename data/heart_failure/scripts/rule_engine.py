import argparse
import json
import re
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def threshold_matches(actual: float | None, expression: str | None) -> bool:
    if actual is None or not expression:
        return False
    if expression.startswith("<="):
        return actual <= float(expression[2:])
    if expression.startswith(">="):
        return actual >= float(expression[2:])
    if expression.startswith("<"):
        return actual < float(expression[1:])
    if expression.startswith(">"):
        return actual > float(expression[1:])
    if "-" in expression:
        low, high = expression.split("-", 1)
        return float(low) <= actual <= float(high)
    return False


def value_matches(actual, expected) -> bool:
    if isinstance(expected, str) and expected[:1] in {"<", ">"}:
        return threshold_matches(actual, expected)
    if isinstance(expected, str) and re.fullmatch(r"-?\d+(\.\d+)?--?\d+(\.\d+)?", expected):
        return threshold_matches(actual, expected)
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


def rule_matches(rule: dict, patient: dict) -> bool:
    condition = rule.get("condition") or {}
    if not condition:
        return False
    for field, expected in condition.items():
        if field == "current_drugs_contains":
            if expected not in patient.get("current_drugs", []):
                return False
            continue
        if not value_matches(patient.get(field), expected):
            return False
    if rule.get("drug") and patient.get("drug") and rule.get("drug") != patient.get("drug"):
        return False
    return True


def evaluate(rules: list[dict], patient: dict) -> list[dict]:
    return [rule for rule in rules if rule_matches(rule, patient)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate generated rules against a simple patient context.")
    parser.add_argument("--rules", default="artifacts/rules/rules.jsonl", type=Path)
    parser.add_argument("--drug", required=True)
    parser.add_argument("--egfr", type=float)
    parser.add_argument("--potassium", type=float)
    parser.add_argument("--sbp", type=float)
    parser.add_argument("--heart-rate", type=float)
    parser.add_argument("--indication")
    parser.add_argument("--diabetes-type")
    args = parser.parse_args()

    patient = {
        "drug": args.drug,
        "egfr": args.egfr,
        "potassium": args.potassium,
        "sbp": args.sbp,
        "heart_rate": args.heart_rate,
        "indication": args.indication,
        "diabetes_type": args.diabetes_type,
    }
    matches = evaluate(read_jsonl(args.rules), patient)
    print(json.dumps(matches, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
