#!/usr/bin/env python3
"""Download open PMC guideline PDFs into hf-cdss-raw S3."""

from __future__ import annotations

import boto3
import httpx

PMC_PDFS = {
    "esc_2021_hf_guideline": ("PMC8490362", "heart_failure/2021 ESC guidelines HF.pdf"),
    "esc_2024_af_guideline": ("PMC11379312", "atrial_fibrillation/2024 ESC Atrial Fibrillation Guidelines.pdf"),
    "acc_aha_2017_bp_guideline": ("PMC6676913", "hypertension/2017 ACC AHA Hypertension Guideline.pdf"),
    # PMC7403606 EuropePMC render 500; PMC6525462 is open full-text PDF mirror.
    "acc_aha_2018_cholesterol_guideline": ("PMC6525462", "dyslipidemia/2018 ACC AHA Cholesterol Guideline.pdf"),
    "acc_aha_2019_primary_prevention_guideline": ("PMC7734661", "ascvd_prevention/2019 ACC AHA Primary Prevention Guideline.pdf"),
    "esc_2021_valvular_heart_disease": ("PMC9725093", "valvular_heart_disease/2021 ESC EACTS Valvular Heart Disease.pdf"),
}

ENDPOINT = "http://localhost:4566"
BUCKET = "hf-cdss-raw"
PREFIX = "heart_failure"


def main() -> None:
    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; hf-cdss-ingest/1.0; research)",
        "Accept": "application/pdf,*/*",
    }
    ok = 0
    for sid, (pmc, rel) in PMC_PDFS.items():
        url = f"https://europepmc.org/articles/{pmc}?pdf=render"
        key = f"{PREFIX}/guidelines/{rel}"
        print(f"GET {url}")
        try:
            with httpx.Client(timeout=120.0, follow_redirects=True, headers=headers) as client:
                response = client.get(url)
            ctype = (response.headers.get("content-type") or "").lower()
            body = response.content
            if response.status_code != 200 or ("pdf" not in ctype and not body.startswith(b"%PDF")):
                print(f"  FAIL {sid}: status={response.status_code} ctype={ctype} bytes={len(body)}")
                continue
            s3.put_object(Bucket=BUCKET, Key=key, Body=body, ContentType="application/pdf")
            print(f"  OK s3://{BUCKET}/{key} ({len(body)} bytes)")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ERR {sid}: {exc}")
    print(f"uploaded {ok}/{len(PMC_PDFS)}")

    pdf_n = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=f"{PREFIX}/guidelines/"):
        for obj in page.get("Contents") or []:
            if obj["Key"].lower().endswith(".pdf"):
                pdf_n += 1
                print(" ", obj["Key"], obj["Size"])
    print("guideline pdfs in s3:", pdf_n)


if __name__ == "__main__":
    main()
