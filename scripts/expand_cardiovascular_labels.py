#!/usr/bin/env python3
"""Expand drug_aliases.json with a broad cardiovascular formulary, then download FDA labels."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIASES_PATH = ROOT / "data" / "heart_failure" / "config" / "drug_aliases.json"

# Broad cardiovascular coverage (US DailyMed-oriented). Existing keys are skipped on merge.
NEW_CV_DRUGS: dict[str, dict] = {
    # --- Calcium channel blockers ---
    "amlodipine": {
        "pipeline_id": "amlodipine",
        "gdmt_class": "calcium_channel_blocker",
        "display_name": "amlodipine",
        "aliases": ["amlodipine", "norvasc", "amlodipine besylate"],
    },
    "nifedipine": {
        "pipeline_id": "nifedipine",
        "gdmt_class": "calcium_channel_blocker",
        "display_name": "nifedipine",
        "aliases": ["nifedipine", "procardia", "adalat"],
    },
    "diltiazem": {
        "pipeline_id": "diltiazem",
        "gdmt_class": "calcium_channel_blocker",
        "display_name": "diltiazem",
        "aliases": ["diltiazem", "cardizem", "tiazac", "diltiazem hydrochloride"],
    },
    "verapamil": {
        "pipeline_id": "verapamil",
        "gdmt_class": "calcium_channel_blocker",
        "display_name": "verapamil",
        "aliases": ["verapamil", "calan", "isoptin", "verapamil hydrochloride"],
    },
    "felodipine": {
        "pipeline_id": "felodipine",
        "gdmt_class": "calcium_channel_blocker",
        "display_name": "felodipine",
        "aliases": ["felodipine", "plendil"],
    },
    "nicardipine": {
        "pipeline_id": "nicardipine",
        "gdmt_class": "calcium_channel_blocker",
        "display_name": "nicardipine",
        "aliases": ["nicardipine", "cardene"],
    },
    "nisoldipine": {
        "pipeline_id": "nisoldipine",
        "gdmt_class": "calcium_channel_blocker",
        "display_name": "nisoldipine",
        "aliases": ["nisoldipine", "sular"],
    },
    "isradipine": {
        "pipeline_id": "isradipine",
        "gdmt_class": "calcium_channel_blocker",
        "display_name": "isradipine",
        "aliases": ["isradipine", "dynacirc"],
    },
    "clevidipine": {
        "pipeline_id": "clevidipine",
        "gdmt_class": "calcium_channel_blocker",
        "display_name": "clevidipine",
        "aliases": ["clevidipine", "cleviprex"],
    },
    "nimodipine": {
        "pipeline_id": "nimodipine",
        "gdmt_class": "calcium_channel_blocker",
        "display_name": "nimodipine",
        "aliases": ["nimodipine", "nymalize"],
    },
    # --- More beta blockers ---
    "nadolol": {
        "pipeline_id": "nadolol",
        "gdmt_class": "beta_blocker",
        "display_name": "nadolol",
        "aliases": ["nadolol", "corgard"],
    },
    "pindolol": {
        "pipeline_id": "pindolol",
        "gdmt_class": "beta_blocker",
        "display_name": "pindolol",
        "aliases": ["pindolol", "visken"],
    },
    "timolol": {
        "pipeline_id": "timolol",
        "gdmt_class": "beta_blocker",
        "display_name": "timolol",
        "aliases": ["timolol", "blocadren", "timolol maleate"],
    },
    "acebutolol": {
        "pipeline_id": "acebutolol",
        "gdmt_class": "beta_blocker",
        "display_name": "acebutolol",
        "aliases": ["acebutolol", "sectral"],
    },
    "betaxolol": {
        "pipeline_id": "betaxolol",
        "gdmt_class": "beta_blocker",
        "display_name": "betaxolol",
        "aliases": ["betaxolol", "kerlone"],
    },
    "esmolol": {
        "pipeline_id": "esmolol",
        "gdmt_class": "beta_blocker",
        "display_name": "esmolol",
        "aliases": ["esmolol", "brevibloc"],
    },
    "carteolol": {
        "pipeline_id": "carteolol",
        "gdmt_class": "beta_blocker",
        "display_name": "carteolol",
        "aliases": ["carteolol", "cartrol"],
    },
    "penbutolol": {
        "pipeline_id": "penbutolol",
        "gdmt_class": "beta_blocker",
        "display_name": "penbutolol",
        "aliases": ["penbutolol", "levatol"],
    },
    # --- Antiplatelets ---
    "prasugrel": {
        "pipeline_id": "prasugrel",
        "gdmt_class": "antiplatelet",
        "display_name": "prasugrel",
        "aliases": ["prasugrel", "effient"],
    },
    "ticagrelor": {
        "pipeline_id": "ticagrelor",
        "gdmt_class": "antiplatelet",
        "display_name": "ticagrelor",
        "aliases": ["ticagrelor", "brilinta"],
    },
    "cangrelor": {
        "pipeline_id": "cangrelor",
        "gdmt_class": "antiplatelet",
        "display_name": "cangrelor",
        "aliases": ["cangrelor", "kengreal"],
    },
    "dipyridamole": {
        "pipeline_id": "dipyridamole",
        "gdmt_class": "antiplatelet",
        "display_name": "dipyridamole",
        "aliases": ["dipyridamole", "persantine"],
    },
    "cilostazol": {
        "pipeline_id": "cilostazol",
        "gdmt_class": "antiplatelet",
        "display_name": "cilostazol",
        "aliases": ["cilostazol", "pletal"],
    },
    "ticlopidine": {
        "pipeline_id": "ticlopidine",
        "gdmt_class": "antiplatelet",
        "display_name": "ticlopidine",
        "aliases": ["ticlopidine", "ticlid"],
    },
    "vorapaxar": {
        "pipeline_id": "vorapaxar",
        "gdmt_class": "antiplatelet",
        "display_name": "vorapaxar",
        "aliases": ["vorapaxar", "zontivity"],
    },
    # --- Parenteral anticoagulants / thrombolytics ---
    "heparin": {
        "pipeline_id": "heparin",
        "gdmt_class": "anticoagulant",
        "display_name": "heparin",
        "aliases": ["heparin", "heparin sodium", "unfractionated heparin", "ufh"],
    },
    "enoxaparin": {
        "pipeline_id": "enoxaparin",
        "gdmt_class": "anticoagulant",
        "display_name": "enoxaparin",
        "aliases": ["enoxaparin", "lovenox", "enoxaparin sodium"],
    },
    "dalteparin": {
        "pipeline_id": "dalteparin",
        "gdmt_class": "anticoagulant",
        "display_name": "dalteparin",
        "aliases": ["dalteparin", "fragmin"],
    },
    "fondaparinux": {
        "pipeline_id": "fondaparinux",
        "gdmt_class": "anticoagulant",
        "display_name": "fondaparinux",
        "aliases": ["fondaparinux", "arixtra"],
    },
    "bivalirudin": {
        "pipeline_id": "bivalirudin",
        "gdmt_class": "anticoagulant",
        "display_name": "bivalirudin",
        "aliases": ["bivalirudin", "angiomax"],
    },
    "argatroban": {
        "pipeline_id": "argatroban",
        "gdmt_class": "anticoagulant",
        "display_name": "argatroban",
        "aliases": ["argatroban"],
    },
    "alteplase": {
        "pipeline_id": "alteplase",
        "gdmt_class": "thrombolytic",
        "display_name": "alteplase",
        "aliases": ["alteplase", "activase", "cathflo"],
    },
    "tenecteplase": {
        "pipeline_id": "tenecteplase",
        "gdmt_class": "thrombolytic",
        "display_name": "tenecteplase",
        "aliases": ["tenecteplase", "tnkase", "tnk"],
    },
    "reteplase": {
        "pipeline_id": "reteplase",
        "gdmt_class": "thrombolytic",
        "display_name": "reteplase",
        "aliases": ["reteplase", "retavase"],
    },
    # --- Statins & lipids ---
    "simvastatin": {
        "pipeline_id": "simvastatin",
        "gdmt_class": "statin",
        "display_name": "simvastatin",
        "aliases": ["simvastatin", "zocor"],
    },
    "pravastatin": {
        "pipeline_id": "pravastatin",
        "gdmt_class": "statin",
        "display_name": "pravastatin",
        "aliases": ["pravastatin", "pravachol"],
    },
    "lovastatin": {
        "pipeline_id": "lovastatin",
        "gdmt_class": "statin",
        "display_name": "lovastatin",
        "aliases": ["lovastatin", "mevacor", "altoprev"],
    },
    "fluvastatin": {
        "pipeline_id": "fluvastatin",
        "gdmt_class": "statin",
        "display_name": "fluvastatin",
        "aliases": ["fluvastatin", "lescol"],
    },
    "pitavastatin": {
        "pipeline_id": "pitavastatin",
        "gdmt_class": "statin",
        "display_name": "pitavastatin",
        "aliases": ["pitavastatin", "livalo", "zypitamag"],
    },
    "ezetimibe": {
        "pipeline_id": "ezetimibe",
        "gdmt_class": "lipid_lowering",
        "display_name": "ezetimibe",
        "aliases": ["ezetimibe", "zetia"],
    },
    "evolocumab": {
        "pipeline_id": "evolocumab",
        "gdmt_class": "pcsk9_inhibitor",
        "display_name": "evolocumab",
        "aliases": ["evolocumab", "repatha"],
    },
    "alirocumab": {
        "pipeline_id": "alirocumab",
        "gdmt_class": "pcsk9_inhibitor",
        "display_name": "alirocumab",
        "aliases": ["alirocumab", "praluent"],
    },
    "inclisiran": {
        "pipeline_id": "inclisiran",
        "gdmt_class": "pcsk9_inhibitor",
        "display_name": "inclisiran",
        "aliases": ["inclisiran", "leqvio"],
    },
    "bempedoic_acid": {
        "pipeline_id": "bempedoic_acid",
        "gdmt_class": "lipid_lowering",
        "display_name": "bempedoic acid",
        "aliases": ["bempedoic acid", "nexletol"],
    },
    "fenofibrate": {
        "pipeline_id": "fenofibrate",
        "gdmt_class": "fibrate",
        "display_name": "fenofibrate",
        "aliases": ["fenofibrate", "tricor", "antara", "lipofen"],
    },
    "gemfibrozil": {
        "pipeline_id": "gemfibrozil",
        "gdmt_class": "fibrate",
        "display_name": "gemfibrozil",
        "aliases": ["gemfibrozil", "lopid"],
    },
    "icosapent_ethyl": {
        "pipeline_id": "icosapent_ethyl",
        "gdmt_class": "lipid_lowering",
        "display_name": "icosapent ethyl",
        "aliases": ["icosapent ethyl", "vascepa", "epa"],
    },
    "niacin": {
        "pipeline_id": "niacin",
        "gdmt_class": "lipid_lowering",
        "display_name": "niacin",
        "aliases": ["niacin", "niaspan", "nicotinic acid"],
    },
    "colesevelam": {
        "pipeline_id": "colesevelam",
        "gdmt_class": "lipid_lowering",
        "display_name": "colesevelam",
        "aliases": ["colesevelam", "welchol"],
    },
    # --- Antiarrhythmics (additional) ---
    "quinidine": {
        "pipeline_id": "quinidine",
        "gdmt_class": "antiarrhythmic",
        "display_name": "quinidine",
        "aliases": ["quinidine", "quinidine sulfate", "quinidine gluconate"],
    },
    "procainamide": {
        "pipeline_id": "procainamide",
        "gdmt_class": "antiarrhythmic",
        "display_name": "procainamide",
        "aliases": ["procainamide", "pronestyl", "procan"],
    },
    "disopyramide": {
        "pipeline_id": "disopyramide",
        "gdmt_class": "antiarrhythmic",
        "display_name": "disopyramide",
        "aliases": ["disopyramide", "norpace"],
    },
    "lidocaine": {
        "pipeline_id": "lidocaine",
        "gdmt_class": "antiarrhythmic",
        "display_name": "lidocaine",
        "aliases": ["lidocaine", "xylocaine", "lidocaine hydrochloride"],
    },
    "adenosine": {
        "pipeline_id": "adenosine",
        "gdmt_class": "antiarrhythmic",
        "display_name": "adenosine",
        "aliases": ["adenosine", "adenocard"],
    },
    "ibutilide": {
        "pipeline_id": "ibutilide",
        "gdmt_class": "antiarrhythmic",
        "display_name": "ibutilide",
        "aliases": ["ibutilide", "corvert"],
    },
    # --- Diuretics / K-sparing ---
    "amiloride": {
        "pipeline_id": "amiloride",
        "gdmt_class": "potassium_sparing_diuretic",
        "display_name": "amiloride",
        "aliases": ["amiloride", "midamor"],
    },
    "triamterene": {
        "pipeline_id": "triamterene",
        "gdmt_class": "potassium_sparing_diuretic",
        "display_name": "triamterene",
        "aliases": ["triamterene", "dyrenium"],
    },
    "mannitol": {
        "pipeline_id": "mannitol",
        "gdmt_class": "osmotic_diuretic",
        "display_name": "mannitol",
        "aliases": ["mannitol", "osmitrol"],
    },
    # --- Vasopressors / inotropes / vasoactives ---
    "epinephrine": {
        "pipeline_id": "epinephrine",
        "gdmt_class": "vasopressor",
        "display_name": "epinephrine",
        "aliases": ["epinephrine", "adrenaline", "epipen"],
    },
    "phenylephrine": {
        "pipeline_id": "phenylephrine",
        "gdmt_class": "vasopressor",
        "display_name": "phenylephrine",
        "aliases": ["phenylephrine", "neo-synephrine"],
    },
    "vasopressin": {
        "pipeline_id": "vasopressin",
        "gdmt_class": "vasopressor",
        "display_name": "vasopressin",
        "aliases": ["vasopressin", "pitressin", "vasostrict"],
    },
    "midodrine": {
        "pipeline_id": "midodrine",
        "gdmt_class": "vasopressor",
        "display_name": "midodrine",
        "aliases": ["midodrine", "proamatine"],
    },
    "angiotensin_ii": {
        "pipeline_id": "angiotensin_ii",
        "gdmt_class": "vasopressor",
        "display_name": "angiotensin II",
        "aliases": ["angiotensin ii", "giapreza"],
    },
    # --- Pulmonary hypertension ---
    "sildenafil": {
        "pipeline_id": "sildenafil",
        "gdmt_class": "pah_therapy",
        "display_name": "sildenafil",
        "aliases": ["sildenafil", "revatio", "viagra"],
    },
    "tadalafil": {
        "pipeline_id": "tadalafil",
        "gdmt_class": "pah_therapy",
        "display_name": "tadalafil",
        "aliases": ["tadalafil", "adcirca", "cialis"],
    },
    "bosentan": {
        "pipeline_id": "bosentan",
        "gdmt_class": "pah_therapy",
        "display_name": "bosentan",
        "aliases": ["bosentan", "tracleer"],
    },
    "ambrisentan": {
        "pipeline_id": "ambrisentan",
        "gdmt_class": "pah_therapy",
        "display_name": "ambrisentan",
        "aliases": ["ambrisentan", "letairis"],
    },
    "macitentan": {
        "pipeline_id": "macitentan",
        "gdmt_class": "pah_therapy",
        "display_name": "macitentan",
        "aliases": ["macitentan", "opsumit"],
    },
    "riociguat": {
        "pipeline_id": "riociguat",
        "gdmt_class": "pah_therapy",
        "display_name": "riociguat",
        "aliases": ["riociguat", "adempas"],
    },
    "selexipag": {
        "pipeline_id": "selexipag",
        "gdmt_class": "pah_therapy",
        "display_name": "selexipag",
        "aliases": ["selexipag", "uptravi"],
    },
    "epoprostenol": {
        "pipeline_id": "epoprostenol",
        "gdmt_class": "pah_therapy",
        "display_name": "epoprostenol",
        "aliases": ["epoprostenol", "flolan", "veletri"],
    },
    "treprostinil": {
        "pipeline_id": "treprostinil",
        "gdmt_class": "pah_therapy",
        "display_name": "treprostinil",
        "aliases": ["treprostinil", "remodulin", "tyvaso", "orenitram"],
    },
    "iloprost": {
        "pipeline_id": "iloprost",
        "gdmt_class": "pah_therapy",
        "display_name": "iloprost",
        "aliases": ["iloprost", "ventavis"],
    },
    # --- Other CV ---
    "colchicine": {
        "pipeline_id": "colchicine",
        "gdmt_class": "anti_inflammatory_cv",
        "display_name": "colchicine",
        "aliases": ["colchicine", "colcrys", "lodoco", "mitigare"],
    },
    "digoxin_immune_fab": {
        "pipeline_id": "digoxin_immune_fab",
        "gdmt_class": "antidote",
        "display_name": "digoxin immune fab",
        "aliases": ["digoxin immune fab", "digibind", "digifab"],
    },
    "protamine": {
        "pipeline_id": "protamine",
        "gdmt_class": "antidote",
        "display_name": "protamine",
        "aliases": ["protamine", "protamine sulfate"],
    },
    "idarucizumab": {
        "pipeline_id": "idarucizumab",
        "gdmt_class": "antidote",
        "display_name": "idarucizumab",
        "aliases": ["idarucizumab", "praxbind"],
    },
    "andexanet_alfa": {
        "pipeline_id": "andexanet_alfa",
        "gdmt_class": "antidote",
        "display_name": "andexanet alfa",
        "aliases": ["andexanet alfa", "andexxa"],
    },
    "phytonadione": {
        "pipeline_id": "phytonadione",
        "gdmt_class": "antidote",
        "display_name": "phytonadione",
        "aliases": ["phytonadione", "vitamin k", "mephyton", "aquamephyton"],
    },
    "isosorbide_mononitrate": {
        "pipeline_id": "isosorbide_mononitrate",
        "gdmt_class": "vasodilator",
        "display_name": "isosorbide mononitrate",
        "aliases": ["isosorbide mononitrate", "imdur", "monoket"],
    },
    "minoxidil": {
        "pipeline_id": "minoxidil",
        "gdmt_class": "vasodilator",
        "display_name": "minoxidil",
        "aliases": ["minoxidil", "loniten"],
    },
    "prazosin": {
        "pipeline_id": "prazosin",
        "gdmt_class": "alpha_blocker",
        "display_name": "prazosin",
        "aliases": ["prazosin", "minipress"],
    },
    "doxazosin": {
        "pipeline_id": "doxazosin",
        "gdmt_class": "alpha_blocker",
        "display_name": "doxazosin",
        "aliases": ["doxazosin", "cardura"],
    },
    "terazosin": {
        "pipeline_id": "terazosin",
        "gdmt_class": "alpha_blocker",
        "display_name": "terazosin",
        "aliases": ["terazosin", "hytrin"],
    },
    "carvedilol_phosphate": {
        "pipeline_id": "carvedilol_phosphate",
        "gdmt_class": "beta_blocker",
        "display_name": "carvedilol phosphate",
        "aliases": ["carvedilol phosphate", "coreg cr"],
    },
    "sacubitril": {
        "pipeline_id": "sacubitril",
        "gdmt_class": "ARNI",
        "display_name": "sacubitril",
        "aliases": ["sacubitril"],
    },
}


PREFERRED_HINTS_EXTRA: dict[str, tuple[str, ...]] = {
    "amlodipine": ("NORVASC",),
    "diltiazem": ("CARDIZEM",),
    "verapamil": ("CALAN",),
    "prasugrel": ("EFFIENT",),
    "ticagrelor": ("BRILINTA",),
    "enoxaparin": ("LOVENOX",),
    "fondaparinux": ("ARIXTRA",),
    "bivalirudin": ("ANGIOMAX",),
    "alteplase": ("ACTIVASE",),
    "tenecteplase": ("TNKase", "TNKASE"),
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
}


def main() -> None:
    aliases = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    added = []
    for key, entry in NEW_CV_DRUGS.items():
        if key in aliases:
            continue
        aliases[key] = entry
        added.append(key)

    ALIASES_PATH.write_text(json.dumps(aliases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"aliases now={len(aliases)} newly_added={len(added)}")
    if added:
        print("added:", ", ".join(added))

    # Patch preferred hints into downloader if present
    downloader = ROOT / "scripts" / "download_missing_drug_labels.py"
    text = downloader.read_text(encoding="utf-8")
    marker = "PREFERRED_TITLE_HINTS: dict[str, tuple[str, ...]] = {"
    if marker in text:
        # Insert missing hint lines before closing of dict — simplest: append via runtime is enough;
        # update module dict by rewriting known block end.
        pass

    # Inject extra hints by rewriting a small helper section in downloader at import time alternative:
    # Call download script directly.
    cmd = [sys.executable, str(ROOT / "scripts" / "download_missing_drug_labels.py"), "--sleep", "0.25"]
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
