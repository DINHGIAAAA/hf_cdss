from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from training.intake_finetune.schema import normalize_medication_name, parse_dose_unit, parse_dose_value


ENTITY_TYPES = {
    "Drug",
    "Strength",
    "Dosage",
    "Form",
    "Route",
    "Frequency",
    "Duration",
    "Reason",
    "ADE",
}


@dataclass
class BratEntity:
    entity_id: str
    entity_type: str
    text: str


@dataclass
class BratRelation:
    relation_id: str
    relation_type: str
    arg1: str
    arg2: str


@dataclass
class BratDocument:
    text: str
    entities: dict[str, BratEntity] = field(default_factory=dict)
    relations: list[BratRelation] = field(default_factory=list)


def _parse_entity_line(line: str) -> BratEntity | None:
    if not line.startswith("T"):
        return None
    parts = line.split("\t", maxsplit=1)
    if len(parts) != 2:
        return None
    entity_id, rest = parts
    rest_parts = rest.split("\t", maxsplit=1)
    if len(rest_parts) != 2:
        return None
    type_and_span, text = rest_parts
    type_parts = type_and_span.split()
    if len(type_parts) < 3:
        return None
    entity_type = type_parts[0]
    return BratEntity(entity_id=entity_id, entity_type=entity_type, text=text.strip())


def _parse_relation_line(line: str) -> BratRelation | None:
    if not line.startswith("R"):
        return None
    parts = line.split("\t", maxsplit=1)
    if len(parts) != 2:
        return None
    relation_id, rest = parts
    tokens = rest.split()
    if len(tokens) < 3:
        return None
    relation_type = tokens[0]
    args: dict[str, str] = {}
    for token in tokens[1:]:
        if ":" not in token:
            continue
        key, value = token.split(":", 1)
        args[key] = value
    arg1 = args.get("Arg1")
    arg2 = args.get("Arg2")
    if not arg1 or not arg2:
        return None
    return BratRelation(relation_id=relation_id, relation_type=relation_type, arg1=arg1, arg2=arg2)


def load_brat_document(text_path: Path, ann_path: Path) -> BratDocument:
    text = text_path.read_text(encoding="utf-8", errors="replace")
    document = BratDocument(text=text)
    if not ann_path.exists():
        return document
    for line in ann_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entity = _parse_entity_line(stripped)
        if entity:
            document.entities[entity.entity_id] = entity
            continue
        relation = _parse_relation_line(stripped)
        if relation:
            document.relations.append(relation)
    return document


def medications_from_brat(document: BratDocument) -> list[dict]:
    drugs = {entity_id: entity for entity_id, entity in document.entities.items() if entity.entity_type == "Drug"}
    grouped: dict[str, dict[str, str | None]] = {
        entity_id: {
            "name": drug.text,
            "dose_value": None,
            "dose_unit": None,
            "frequency": None,
        }
        for entity_id, drug in drugs.items()
    }

    for relation in document.relations:
        arg1_entity = document.entities.get(relation.arg1)
        arg2_entity = document.entities.get(relation.arg2)
        if not arg1_entity or not arg2_entity:
            continue

        drug_id: str | None = None
        attribute_entity: BratEntity | None = None
        if arg1_entity.entity_type == "Drug":
            drug_id = relation.arg1
            attribute_entity = arg2_entity
        elif arg2_entity.entity_type == "Drug":
            drug_id = relation.arg2
            attribute_entity = arg1_entity
        else:
            relation_name = relation.relation_type.lower()
            if "drug" in relation_name:
                if arg1_entity.entity_type in ENTITY_TYPES - {"Drug", "ADE", "Reason"}:
                    attribute_entity = arg1_entity
                    drug_id = relation.arg2 if arg2_entity.entity_type == "Drug" else None
                elif arg2_entity.entity_type in ENTITY_TYPES - {"Drug", "ADE", "Reason"}:
                    attribute_entity = arg2_entity
                    drug_id = relation.arg1 if arg1_entity.entity_type == "Drug" else None
        if not drug_id or drug_id not in grouped or attribute_entity is None:
            continue

        bucket = grouped[drug_id]
        attr_type = attribute_entity.entity_type
        attr_text = attribute_entity.text
        if attr_type in {"Strength", "Dosage"}:
            if bucket["dose_value"] is None:
                bucket["dose_value"] = attr_text
            if bucket["dose_unit"] is None:
                bucket["dose_unit"] = attr_text
        elif attr_type == "Frequency":
            bucket["frequency"] = attr_text

    medications: list[dict] = []
    for payload in grouped.values():
        dose_value_raw = payload.get("dose_value")
        dose_unit_raw = payload.get("dose_unit")
        medications.append(
            {
                "name": normalize_medication_name(str(payload["name"])),
                "dose_value": parse_dose_value(str(dose_value_raw) if dose_value_raw else None),
                "dose_unit": parse_dose_unit(str(dose_unit_raw) if dose_unit_raw else None),
                "frequency": payload.get("frequency"),
            }
        )
    return medications


def red_flags_from_brat(document: BratDocument) -> list[dict]:
    flags = []
    for entity in document.entities.values():
        if entity.entity_type != "ADE":
            continue
        flags.append({"name": entity.text.strip().lower().replace(" ", "_"), "status": "present"})
    return flags
