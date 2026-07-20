#!/usr/bin/env python3
"""Generate source registry entries for drug labels from DailyMed."""

import json
import sys
from pathlib import Path

# Extended drug list with new drugs added to drug_aliases.json
DRUGS = [
    # SGLT2i
    {"slug": "dapagliflozin", "query": "dapagliflozin", "name": "Dapagliflozin"},
    {"slug": "empagliflozin", "query": "empagliflozin", "name": "Empagliflozin"},
    {"slug": "canagliflozin", "query": "canagliflozin", "name": "Canagliflozin"},
    {"slug": "ertugliflozin", "query": "ertugliflozin", "name": "Ertugliflozin"},
    # ARNI
    {"slug": "sacubitril_valsartan", "query": "sacubitril valsartan", "name": "Sacubitril/Valsartan"},
    # MRA
    {"slug": "spironolactone", "query": "spironolactone", "name": "Spironolactone"},
    {"slug": "eplerenone", "query": "eplerenone", "name": "Eplerenone"},
    {"slug": "finerenone", "query": "finerenone", "name": "Finerenone"},
    # Beta Blockers
    {"slug": "metoprolol_succinate", "query": "metoprolol succinate", "name": "Metoprolol Succinate"},
    {"slug": "bisoprolol", "query": "bisoprolol fumarate", "name": "Bisoprolol"},
    {"slug": "carvedilol", "query": "carvedilol", "name": "Carvedilol"},
    {"slug": "nebivolol", "query": "nebivolol", "name": "Nebivolol"},
    {"slug": "atenolol", "query": "atenolol", "name": "Atenolol"},
    {"slug": "propranolol", "query": "propranolol", "name": "Propranolol"},
    {"slug": "metoprolol_tartrate", "query": "metoprolol tartrate", "name": "Metoprolol Tartrate"},
    # ACEi
    {"slug": "enalapril", "query": "enalapril maleate", "name": "Enalapril"},
    {"slug": "lisinopril", "query": "lisinopril", "name": "Lisinopril"},
    {"slug": "ramipril", "query": "ramipril", "name": "Ramipril"},
    {"slug": "quinapril", "query": "quinapril", "name": "Quinapril"},
    {"slug": "benazepril", "query": "benazepril", "name": "Benazepril"},
    {"slug": "captopril", "query": "captopril", "name": "Captopril"},
    {"slug": "fosinopril", "query": "fosinopril", "name": "Fosinopril"},
    {"slug": "trandolapril", "query": "trandolapril", "name": "Trandolapril"},
    {"slug": "perindopril", "query": "perindopril", "name": "Perindopril"},
    {"slug": "moexipril", "query": "moexipril", "name": "Moexipril"},
    # ARB
    {"slug": "losartan", "query": "losartan potassium", "name": "Losartan"},
    {"slug": "valsartan", "query": "valsartan", "name": "Valsartan"},
    {"slug": "candesartan", "query": "candesartan cilexetil", "name": "Candesartan"},
    {"slug": "telmisartan", "query": "telmisartan", "name": "Telmisartan"},
    {"slug": "olmesartan", "query": "olmesartan medoxomil", "name": "Olmesartan"},
    {"slug": "irbesartan", "query": "irbesartan", "name": "Irbesartan"},
    {"slug": "azilsartan", "query": "azilsartan medoxomil", "name": "Azilsartan"},
    {"slug": "eprosartan", "query": "eprosartan", "name": "Eprosartan"},
    # Loop Diuretics
    {"slug": "furosemide", "query": "furosemide", "name": "Furosemide"},
    {"slug": "bumetanide", "query": "bumetanide", "name": "Bumetanide"},
    {"slug": "torsemide", "query": "torsemide", "name": "Torsemide"},
    {"slug": "ethacrynic_acid", "query": "ethacrynic acid", "name": "Ethacrynic Acid"},
    # Anticoagulants
    {"slug": "apixaban", "query": "apixaban", "name": "Apixaban"},
    {"slug": "rivaroxaban", "query": "rivaroxaban", "name": "Rivaroxaban"},
    {"slug": "edoxaban", "query": "edoxaban", "name": "Edoxaban"},
    {"slug": "dabigatran", "query": "dabigatran etexilate", "name": "Dabigatran"},
    {"slug": "warfarin", "query": "warfarin sodium", "name": "Warfarin"},
    # Other HF drugs
    {"slug": "digoxin", "query": "digoxin", "name": "Digoxin"},
    {"slug": "ivabradine", "query": "ivabradine", "name": "Ivabradine"},
    {"slug": "hydralazine", "query": "hydralazine", "name": "Hydralazine"},
    {"slug": "isosorbide_dinitrate", "query": "isosorbide dinitrate", "name": "Isosorbide Dinitrate"},
    {"slug": "nitroglycerin", "query": "nitroglycerin", "name": "Nitroglycerin"},
    {"slug": "vericiguat", "query": "vericiguat", "name": "Vericiguat"},
    {"slug": "omecamtiv_mecarbil", "query": "omecamtiv mecarbil", "name": "Omecamtiv Mecarbil"},
    # Antiarrhythmics
    {"slug": "amiodarone", "query": "amiodarone", "name": "Amiodarone"},
    {"slug": "sotalol", "query": "sotalol", "name": "Sotalol"},
    {"slug": "dofetilide", "query": "dofetilide", "name": "Dofetilide"},
    {"slug": "propafenone", "query": "propafenone", "name": "Propafenone"},
    {"slug": "flecainide", "query": "flecainide", "name": "Flecainide"},
    # Thiazides
    {"slug": "chlorthalidone", "query": "chlorthalidone", "name": "Chlorthalidone"},
    {"slug": "hydrochlorothiazide", "query": "hydrochlorothiazide", "name": "Hydrochlorothiazide"},
    # Electrolytes
    {"slug": "potassium_chloride", "query": "potassium chloride", "name": "Potassium Chloride"},
    # Combos
    {"slug": "hydralazine_isosorbide", "query": "hydralazine isosorbide dinitrate", "name": "Hydralazine/Isosorbide"},
]


def generate_sources():
    """Generate source registry entries for drug labels."""
    sources = []

    for drug in DRUGS:
        slug = drug["slug"]
        query = drug["query"]
        name = drug["name"]

        source = {
            "source_id": f"{slug}_label",
            "title": f"{name} - FDA Label",
            "source_type": "drug_label_xml",
            "download_strategy": "dailymed_spl",
            "publisher": "FDA DailyMed",
            "topic": "drug_label",
            "slug": slug,
            "query": query,
            "required_terms": [query.upper()],
            "target_path": f"raw/drug_labels/{slug}/{slug}_label.xml",
            "license_note": "Public domain FDA label. Safe for ingestion."
        }
        sources.append(source)

    return sources


def main():
    """Main entry point."""
    sources = generate_sources()

    # Output as JSON
    print(json.dumps(sources, indent=2, ensure_ascii=False))

    # Also save to file
    output_path = Path(__file__).parent.parent / "data" / "heart_failure" / "sources" / "generated_drug_sources.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(sources, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nGenerated {len(sources)} source entries")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
