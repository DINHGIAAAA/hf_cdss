# Guideline Scope — Heart Failure CDSS

MVP focuses on adult HFrEF GDMT, contraindication checks, and physician-facing explanation. The registry also ingests **comorbidity guidelines** that change HF therapy, monitoring, or prognosis.

## Primary Clinical Scope

- Adult patients with suspected or established heart failure.
- HFrEF-oriented GDMT where LVEF ≤ 40%.
- Safety checks: renal function, potassium, blood pressure, heart rate, allergies, polypharmacy.
- Output categories: `recommend`, `consider`, `caution`, `avoid`.

## Comorbidity → Guideline Coverage

| Comorbidity / risk | Why it matters for HF | Registry topics / sources |
|--------------------|----------------------|---------------------------|
| Heart failure | Core GDMT, phenotypes, decompensation | AHA/ACC/HFSA 2022; ESC 2021; ESC 2023 focused update |
| Atrial fibrillation | Rate/rhythm, anticoagulation, GDMT interaction | ACC/AHA/ACCP/HRS 2023; ESC 2024 AF |
| Hypertension | Afterload, RAAS titration, symptom overlap | ACC/AHA 2017 hypertension |
| Type 2 diabetes | SGLT2i, GLP-1 RA, glycemic targets | ADA 2024 Standards of Care (full supplement, PMC) |
| CKD | RAAS/MRA eligibility, SGLT2i, K+ | KDIGO 2024 CKD; ADA/KDIGO diabetes–CKD consensus; ADA CKD section |
| Dyslipidemia | Statin therapy, ASCVD risk | ACC/AHA 2018 cholesterol (PMC) |
| ASCVD / primary prevention | Risk factor modification | ACC/AHA 2019 primary prevention (PMC); ESC 2021 CVD prevention |
| Valvular heart disease | AS/MR → HF; intervention timing | ACC/AHA 2020 valvular (PDF) |
| Hypertrophic cardiomyopathy | HFpEF, outflow obstruction, SCD | ACC/AHA 2020 HCM (PDF) |
| Pulmonary hypertension | RV failure, exercise intolerance | ESC/ERS 2022 pulmonary hypertension |
| COPD | Beta-blocker caution, hypoxia, polypharmacy | GOLD 2024 COPD report |
| Obstructive sleep apnea | HFpEF, resistant HTN, hypoxia | AASM 2017 OSA diagnostic (PMC) |
| Peripheral artery disease | ASCVD overlap, exercise, statin | ACC/AHA 2024 PAD (PMC) |
| Obesity | HFpEF, diabetes overlap | ADA 2024 obesity section |
| Older adults | Deprescribing, hypoglycemia, frailty | ADA 2024 older adults section |
| Anemia / iron deficiency | Symptoms, IV iron in HFrEF | Covered in ESC HF 2021/2023 updates (iron recommendations) |

## ADA 2024 Supplement Sections (complete)

All sections use PMC HTML mirrors (`pmc.ncbi.nlm.nih.gov`):

| Section | Topic |
|---------|-------|
| 1 | Population health |
| 2 | Diagnosis & classification |
| 3 | Prevention / delay of diabetes |
| 4 | Comprehensive evaluation & comorbidities |
| 5 | Health behaviors & well-being |
| 6 | Glycemic goals & hypoglycemia |
| 7 | Diabetes technology |
| 8 | Obesity & weight management |
| 9 | Pharmacologic glycemic treatment |
| 10 | Cardiovascular disease & risk management |
| 11 | CKD & risk management |
| 12 | Retinopathy, neuropathy, foot care |
| 13 | Older adults |
| 14 | Children & adolescents *(low HF relevance)* |
| 15 | Diabetes in pregnancy |
| 16 | Hospital care |
| 17 | Advocacy *(low clinical relevance)* |

## Sources not yet in registry (publisher paywall / no stable mirror)

These may be added when a reliable open PDF/HTML mirror is found:

- 2021 chest pain / coronary revascularization (ACC/AHA)
- 2023 ACC cardiac amyloidosis guideline
- 2024 ACC obesity pharmacotherapy expert consensus
- 2023 ESC cardiomyopathy & ESC diabetes/CVD guidelines (full PDF)
- KDIGO 2021 blood pressure in CKD (direct PDF path changed on kdigo.org)
- 2021 AHA/ASA secondary stroke prevention (no PMC full text)
- 2021 AHA OSA & cardiovascular disease scientific statement (no PMC full text)

## How to add more guidelines

1. Add entry to `sources/sources.example.json` with `source_type` `guideline_pdf` or `guideline_html`.
2. Prefer **PMC HTML** for journal articles; use **official PDF mirrors** (KDIGO, GOLD, EAS, institutional repos) when PMC is unavailable.
3. Verify URL with `scraper/scripts/test_guideline_urls.py` or `lookup_pmc_ids.py`.
4. Re-run Airflow DAG: `download_sources` → `run_kg_pipeline` (`--timeout 180` for large PDFs).
5. Restart backend to re-index Chroma.

## Week 1 Data Artifacts

- `gdmt_medication_groups.json`: GDMT medication class vocabulary.
- `clinical_risk_table.json`: risk flags and affected drug classes.
- `synthetic_cases/day1_sample_cases.json`: sample patient profiles.
