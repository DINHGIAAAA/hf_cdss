#!/usr/bin/env python3
"""Download missing FDA DailyMed SPL XMLs for drugs in drug_aliases.json."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ALIASES_PATH = ROOT / "data" / "heart_failure" / "config" / "drug_aliases.json"
# Local cache only; durable copy is uploaded to S3 in download_one().
LABELS_DIR = Path(
    os.environ.get(
        "HF_CDSS_RAW_ROOT",
        str(ROOT / ".work" / "heart_failure" / "raw"),
    )
) / "drug_labels"
USER_AGENT = (
    "Mozilla/5.0 (compatible; hf_cdss-label-fetcher/1.0; +https://github.com/DINHGIAAAA/hf_cdss)"
)

# Prefer these brand/set titles when present in DailyMed results.
PREFERRED_TITLE_HINTS: dict[str, tuple[str, ...]] = {
    "vericiguat": ("VERQUVO",),
    "rivaroxaban": ("XARELTO",),
    "edoxaban": ("SAVAYSA",),
    "dabigatran_etexilate": ("PRADAXA",),
    "ivabradine": ("CORLANOR",),
    "eplerenone": ("INSPRA",),
    "finerenone": ("KERENDIA",),
    "sacubitril_and_valsartan": ("ENTRESTO",),
    "hydralazine_and_isosorbide_dinitrate": ("BIDIL",),
    "dofetilide": ("TIKOSYN",),
    "canagliflozin": ("INVOKANA",),
    "ertugliflozin": ("STEGLATRO",),
    "metformin": ("GLUCOPHAGE", "METFORMIN HYDROCHLORIDE TABLET"),
    "olmesartan_medoxomil": ("BENICAR",),
    "eprosartan": ("TEVETEN",),
    "chlorthalidone_and_clonidine": ("CLORPRES",),
    "sotagliflozin": ("INPEFA",),
    "semaglutide": ("OZEMPIC", "WEGOVY", "RYBELSUS"),
    "tirzepatide": ("MOUNJARO", "ZEPBOUND"),
    "tolvaptan": ("SAMSCA",),
    "dronedarone": ("MULTAQ",),
    "metolazone": ("ZAROXOLYN",),
    "ferric_carboxymaltose": ("INJECTAFER",),
    "iron_sucrose": ("VENOFER",),
    "ranolazine": ("RANEXA",),
    "clopidogrel": ("PLAVIX",),
    "atorvastatin": ("LIPITOR",),
    "rosuvastatin": ("CRESTOR",),
    "sodium_polystyrene_sulfonate": ("KAYEXALATE",),
    "patiromer": ("VELTASSA",),
    "sodium_zirconium_cyclosilicate": ("LOKELMA",),
    "amlodipine": ("NORVASC",),
    "diltiazem": ("CARDIZEM",),
    "verapamil": ("CALAN",),
    "prasugrel": ("EFFIENT",),
    "ticagrelor": ("BRILINTA",),
    "enoxaparin": ("LOVENOX",),
    "fondaparinux": ("ARIXTRA",),
    "bivalirudin": ("ANGIOMAX",),
    "alteplase": ("ACTIVASE",),
    "tenecteplase": ("TNKASE",),
    "evolocumab": ("REPATHA",),
    "alirocumab": ("PRALUENT",),
    "inclisiran": ("LEQVIO",),
    "bempedoic_acid": ("NEXLETOL",),
    "icosapent_ethyl": ("VASCEPA",),
    "ezetimibe": ("ZETIA",),
    "simvastatin": ("ZOCOR",),
    "sildenafil": ("REVATIO",),
    "tadalafil": ("ADCIRCA",),
    "bosentan": ("TRACLEER",),
    "ambrisentan": ("LETAIRIS",),
    "macitentan": ("OPSUMIT",),
    "riociguat": ("ADEMPAS",),
    "selexipag": ("UPTRAVI",),
    "clevidipine": ("CLEVIPREX",),
    "esmolol": ("BREVIBLOC",),
    "cangrelor": ("KENGREAL",),
    "vorapaxar": ("ZONTIVITY",),
    "idarucizumab": ("PRAXBIND",),
    "andexanet_alfa": ("ANDEXXA",),
    "angiotensin_ii": ("GIAPREZA",),
    "colchicine": ("LODOCO", "COLCRYS"),
    "heparin": ("HEPARIN SODIUM INJECTION",),
    "niacin": ("NIASPAN", "NIACIN TABLET"),
    "phenylephrine": ("PHENYLEPHRINE HYDROCHLORIDE INJECTION",),
    "lidocaine": ("LIDOCAINE HYDROCHLORIDE INJECTION", "XYLOCAINE"),
    "timolol": ("BLOCADREN", "TIMOLOL MALEATE TABLET"),
    "alteplase": ("ACTIVASE",),
    "iloprost": ("VENTAVIS",),
}


def fetch_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_json(url: str, timeout: int = 60) -> dict[str, Any]:
    return json.loads(fetch_bytes(url, timeout).decode("utf-8"))


def parse_date(value: str | None) -> date:
    if not value:
        return date.min
    for candidate, fmt in (
        (value[:10], "%Y-%m-%d"),
        (value, "%b %d, %Y"),
        (value, "%B %d, %Y"),
    ):
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return date.min


def query_for_entry(pipeline_id: str, entry: dict[str, Any]) -> str:
    display = str(entry.get("display_name") or "").strip()
    if display:
        return display
    return pipeline_id.replace("_", " ")


def required_terms(pipeline_id: str, entry: dict[str, Any]) -> list[str]:
    query = query_for_entry(pipeline_id, entry).upper()
    # Keep meaningful tokens; drop short connectors.
    tokens = [t for t in re.split(r"[^A-Z0-9]+", query) if len(t) >= 3]
    # Combo products need both sides.
    if "_and_" in pipeline_id or "/" in str(entry.get("display_name") or ""):
        return tokens
    # Single-ingredient: require the main drug token(s), not salt suffixes alone.
    saltish = {"SODIUM", "POTASSIUM", "HYDROCHLORIDE", "MALEATE", "FUMARATE", "MEDOXOMIL", "CILEXETIL", "ETEXILATE"}
    core = [t for t in tokens if t not in saltish]
    return core or tokens


def dailymed_candidates(query: str, timeout: int) -> list[dict[str, Any]]:
    base = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
    encoded = urllib.parse.quote(query)
    for name_type in ("generic", "both"):
        payload = fetch_json(f"{base}?drug_name={encoded}&name_type={name_type}&pagesize=100", timeout)
        rows = payload.get("data") or []
        if rows:
            return rows
    return []


# Explicit near-duplicates already on disk (do not use fuzzy prefix matching).
COVERED_BY: dict[str, str] = {
    "hydralazine": "hydralazine_hydrochloride",
}

# Tokens that indicate a multi-ingredient product when looking for a single drug.
FOREIGN_DRUG_HINTS = (
    "HYDROCHLOROTHIAZIDE",
    "HCTZ",
    "AMLODIPINE",
    "GLYBURIDE",
    "GLIPIZIDE",
    "METFORMIN",
    "LISINOPRIL",
    "LOSARTAN",
    "VALSARTAN",
    "OLMESARTAN",
    "TELMISARTAN",
    "IRBESARTAN",
    "ATENOLOL",
    "CLONIDINE",
    "SPIRONOLACTONE",
    "ATORVASTATIN",
    "ISOSORBIDE",
    "HYDRALAZINE",
    "ASPIRIN",
    "CLOPIDOGREL",
)


def is_unwanted_combo_title(title: str, pipeline_id: str, required: list[str]) -> bool:
    """Reject fixed-dose combination SPLs when downloading a single ingredient."""
    upper = title.upper()
    if any(
        bad in upper
        for bad in (
            "HOMEOPATHIC",
            "HOMOEOPATHIC",
            "DESERET BIOLOGICALS",
            "NATURAL RELIEF",
            "HPUS",
        )
    ):
        return True
    # Ignore manufacturer suffix like [ELI LILLY AND COMPANY]
    product = re.sub(r"\[.*?\]", " ", upper)
    # Reject obvious non-systemic / multi-vitamin noise for CV formulary downloads.
    if pipeline_id in {
        "niacin",
        "phenylephrine",
        "timolol",
        "lidocaine",
        "dopamine",
        "magnesium_sulfate",
        "alteplase",
        "iloprost",
    }:
        if any(
            bad in product
            for bad in (
                "FOLIC ACID",
                "THIAMINE",
                "RIBOFLAVIN",
                "ACETAMINOPHEN",
                "CHLORPHENIRAMINE",
                "DORZOLAMIDE",
                "SOLUTION/ DROPS",
                "OPHTHALMIC",
                "OINTMENT",
                "CREAM",
                "EPSOM",
                "SINUS",
                "CONGESTION",
                "CATHFLO",
            )
        ):
            return True
        if pipeline_id == "phenylephrine" and "INJECTION" not in product:
            return True
        if pipeline_id == "alteplase" and "CATHFLO" in product:
            return True
    if " AND " in product:
        return True
    if product.count(";") >= 1:
        return True
    # e.g. OLMESARTAN MEDOXOMIL-HYDROCHLOROTHIAZIDE / GLYBURIDE-METFORMIN
    if re.search(r"[A-Z]{4,}\s*-\s*[A-Z]{4,}", product):
        return True
    self_tokens = set(required) | {t.upper() for t in pipeline_id.split("_") if len(t) >= 4}
    for hint in FOREIGN_DRUG_HINTS:
        if hint in self_tokens:
            continue
        if hint in product:
            return True
    return False


def select_candidate(
    pipeline_id: str,
    entry: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    required = required_terms(pipeline_id, entry)
    wants_combo = "_and_" in pipeline_id or str(entry.get("gdmt_class") or "").endswith("_combo")
    preferred = PREFERRED_TITLE_HINTS.get(pipeline_id, ())

    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        title = str(candidate.get("title") or "").upper()
        if not all(term in title for term in required):
            continue
        if not wants_combo and is_unwanted_combo_title(title, pipeline_id, required):
            continue
        if wants_combo:
            # Combo products should mention both sides somehow.
            if " AND " not in title and "-" not in title and "/" not in title:
                # Still allow brand-only titles like BIDIL via preferred hints.
                if not any(hint in title for hint in preferred):
                    continue
        matches.append(candidate)

    if not matches:
        raise ValueError(f"No DailyMed SPL matched required terms {required}")

    def score(item: dict[str, Any]) -> tuple:
        title = str(item.get("title") or "").upper()
        pref = any(hint in title for hint in preferred)
        form_bonus = 1 if any(x in title for x in ("TABLET", "CAPSULE", "INJECTION", "SOLUTION")) else 0
        if pipeline_id in {
            "dobutamine",
            "dopamine",
            "milrinone",
            "norepinephrine",
            "nitroprusside",
            "magnesium_sulfate",
            "ferric_carboxymaltose",
            "iron_sucrose",
            "semaglutide",
            "tirzepatide",
        }:
            form_bonus += 2 if "INJECTION" in title else 0
        repack_penalty = 1 if "REMEDYREPACK" in title or "REPACK" in title else 0
        junk_penalty = 1 if any(x in title for x in ("EPSOM", "CREAM", "GRANULE", "HOMEOPATHIC", "HOMO")) else 0
        return (
            1 if pref else 0,
            form_bonus,
            -repack_penalty,
            -junk_penalty,
            parse_date(item.get("published_date")),
            int(item.get("spl_version") or 0),
        )

    return sorted(matches, key=score, reverse=True)[0]


def existing_label_dirs() -> set[str]:
    if not LABELS_DIR.exists():
        return set()
    return {p.name for p in LABELS_DIR.iterdir() if p.is_dir()}


def already_covered(pipeline_id: str, existing: set[str]) -> str | None:
    if pipeline_id in existing:
        xml = LABELS_DIR / pipeline_id / f"{pipeline_id}_label.xml"
        if xml.is_file():
            return pipeline_id
        if list((LABELS_DIR / pipeline_id).glob("*_label.xml")):
            return pipeline_id
    related = COVERED_BY.get(pipeline_id)
    if related and related in existing and list((LABELS_DIR / related).glob("*_label.xml")):
        return related
    return None


def candidate_queries(pipeline_id: str, entry: dict[str, Any]) -> list[str]:
    queries: list[str] = []
    primary = query_for_entry(pipeline_id, entry)
    queries.append(primary)
    for hint in PREFERRED_TITLE_HINTS.get(pipeline_id, ()):
        # Brand-only token before parenthesis text.
        token = hint.split()[0].strip("()")
        if token and token.lower() not in {q.lower() for q in queries}:
            queries.append(token)
    for alias in entry.get("aliases") or []:
        alias_s = str(alias).strip()
        if not alias_s or re.search(r"\d", alias_s):
            continue
        if alias_s.lower() not in {q.lower() for q in queries}:
            queries.append(alias_s)
    return queries


def download_one(pipeline_id: str, entry: dict[str, Any], timeout: int, dry_run: bool) -> dict[str, Any]:
    last_error: Exception | None = None
    best = None
    query = query_for_entry(pipeline_id, entry)
    for try_query in candidate_queries(pipeline_id, entry):
        candidates = dailymed_candidates(try_query, timeout)
        if not candidates:
            continue
        try:
            best = select_candidate(pipeline_id, entry, candidates)
            query = try_query
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    if best is None:
        raise ValueError(str(last_error) if last_error else f"No DailyMed results for {pipeline_id}")

    setid = best["setid"]
    url = f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{setid}.xml"
    out_dir = LABELS_DIR / pipeline_id
    out_path = out_dir / f"{pipeline_id}_label.xml"
    result = {
        "pipeline_id": pipeline_id,
        "query": query,
        "setid": setid,
        "title": best.get("title"),
        "published_date": best.get("published_date"),
        "target": str(out_path.relative_to(ROOT)).replace("\\", "/"),
        "status": "planned" if dry_run else "downloaded",
    }
    if dry_run:
        return result

    payload = fetch_bytes(url, timeout)
    if not payload.lstrip().startswith(b"<?xml") and b"<document" not in payload[:2000]:
        raise ValueError(f"Response does not look like SPL XML ({len(payload)} bytes)")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(payload)
    result["bytes"] = len(payload)

    # Durable copy: upload to raw S3 (same layout as download_sources).
    try:
        from scraper.acquisition.download_sources import ensure_bucket, s3_key
        from scraper.s3_client import s3_client

        endpoint = os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566")
        bucket = os.environ.get("HF_CDSS_RAW_BUCKET", "hf-cdss-raw")
        prefix = os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure")
        client = s3_client(endpoint)
        ensure_bucket(client, bucket)
        rel = f"raw/drug_labels/{pipeline_id}/{pipeline_id}_label.xml"
        key = s3_key(prefix, rel)
        client.put_object(Bucket=bucket, Key=key, Body=payload)
        result["storage_uri"] = f"s3://{bucket}/{key}"
    except Exception as exc:  # noqa: BLE001 — local file still usable for offline tools
        result["s3_upload_error"] = str(exc)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", action="append", help="Limit to pipeline_id(s)")
    parser.add_argument("--force", action="store_true", help="Re-download even if label exists")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--sleep", type=float, default=0.4, help="Pause between DailyMed calls")
    args = parser.parse_args()

    aliases = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    existing = existing_label_dirs()
    wanted = sorted(aliases.keys())
    if args.only:
        wanted = [k for k in wanted if k in set(args.only)]

    summary = {"skipped": [], "downloaded": [], "failed": []}
    for pipeline_id in wanted:
        entry = aliases[pipeline_id]
        covered = None if args.force else already_covered(pipeline_id, existing)
        if covered:
            summary["skipped"].append({"pipeline_id": pipeline_id, "covered_by": covered})
            print(f"SKIP  {pipeline_id} (covered by {covered})")
            continue
        try:
            row = download_one(pipeline_id, entry, args.timeout, args.dry_run)
            summary["downloaded"].append(row)
            print(f"{'PLAN' if args.dry_run else 'OK  '} {pipeline_id} <- {row.get('title')}")
            existing.add(pipeline_id)
        except Exception as exc:  # noqa: BLE001 - collect per-drug failures
            summary["failed"].append({"pipeline_id": pipeline_id, "error": str(exc)})
            print(f"FAIL  {pipeline_id}: {exc}")
        time.sleep(args.sleep)

    report_path = ROOT / "data" / "heart_failure" / "artifacts" / "manifests" / "drug_label_download_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"\nDone. skipped={len(summary['skipped'])} "
        f"downloaded={len(summary['downloaded'])} failed={len(summary['failed'])}"
    )
    print(f"Report: {report_path}")
    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
