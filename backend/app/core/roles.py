VALID_USER_ROLES = frozenset({"admin", "clinical_lead", "clinician", "viewer"})


def normalize_roles(roles: list[str] | tuple[str, ...] | None) -> list[str]:
    if not roles:
        return []
    normalized: list[str] = []
    for role in roles:
        value = str(role).strip()
        if not value:
            continue
        if value not in VALID_USER_ROLES:
            raise ValueError(f"Unsupported role: {value}")
        if value not in normalized:
            normalized.append(value)
    return normalized
