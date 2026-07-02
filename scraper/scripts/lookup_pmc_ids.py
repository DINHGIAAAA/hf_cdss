"""Lookup PMC IDs for guideline registry work."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

QUERIES: dict[str, str] = {
    "stroke_2021": "DOI:10.1161/STR.0000000000000375",
    "pad_2024": "DOI:10.1161/CIR.0000000000001256",
    "osa_2021": "DOI:10.1161/CIR.0000000000000988",
    "esc_cardiomyopathy_2023": "DOI:10.1093/eurheartj/ehad194",
    "esc_diabetes_cvd_2023": "DOI:10.1093/eurheartj/ehad192",
    "chest_pain_2021": "DOI:10.1016/j.jacc.2021.11.002",
    "coronary_revasc_2021": "DOI:10.1016/j.jacc.2021.10.002",
    "cardiac_amyloid_2023": "DOI:10.1016/j.jacc.2023.09.019",
    "acc_obesity_2024": "DOI:10.1016/j.jacc.2024.05.008",
    "kdigo_bp_2021": "TITLE:KDIGO 2021 Clinical Practice Guideline for the Management of Blood Pressure in Chronic Kidney Disease",
    "kdigo_anemia_2023": "TITLE:KDIGO 2023 Clinical Practice Guideline for Anemia in Chronic Kidney Disease",
    "osa_2021": "DOI:10.1161/CIR.0000000000000988",
    "stroke_2021": "DOI:10.1161/STR.0000000000000375",
    "pad_2024": "DOI:10.1161/CIR.0000000000001256",
}


def lookup(query: str) -> list[dict]:
    url = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
        f"query={urllib.parse.quote(query)}&format=json&pageSize=3"
    )
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.load(response)
    return payload.get("resultList", {}).get("result", [])


if __name__ == "__main__":
    for label, query in QUERIES.items():
        results = lookup(query)
        if not results:
            print(f"{label}: NOT FOUND")
            continue
        for row in results[:2]:
            print(f"{label}: {row.get('pmcid', '-')} | {(row.get('title') or '')[:90]}")
