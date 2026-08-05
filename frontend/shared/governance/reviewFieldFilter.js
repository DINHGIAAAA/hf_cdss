/**
 * Fields omitted from governance "full review" (diff modal + payload summary).
 * Keeps clinical content and human-readable references only.
 */

import { formatSeverityRule, formatTriggerCondition } from "./triggerDisplay.js";

const REVIEW_OMIT_KEYS = new Set([
  "id",
  "content_hash",
  "chunk_id",
  "claim_id",
  "source_id",
  "extraction_method",
  "confidence",
  "created_at",
  "updated_at",
  "approved_at",
  "retired_at",
  "approved_by",
  "retired_by",
  "changed_by",
  "changed_at",
  "history_id",
  "rule_id",
  "constraint_id",
  "dose_rule_id",
  "interaction_rule_id",
  "gdmt_policy_id",
  "dose_safety_warning_id",
  "password_hash",
  "case_id",
  "conversation_id",
]);

/** Allowed under `metadata` (pipeline hashes and ids are hidden). */
const METADATA_REVIEW_KEYS = new Set([
  "safety_tier",
  "needs_condition",
  "action_type",
  "review_notes",
  "tier",
  "title",
  "publisher",
  "section",
  "source_section",
  "page",
  "page_number",
  "source_url",
  "source_type",
  "source_locator",
]);

/** Allowed direct fields on each `clinical_sources[]` item. */
const CLINICAL_SOURCE_REVIEW_KEYS = new Set([
  "evidence",
  "title",
  "source_url",
  "source_section",
  "source_type",
  "document_id",
  "publisher",
  "evidence_ref",
  "source_locator",
  "metadata",
]);

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

/**
 * Whether to skip a key when walking a diff or sanitizing JSON for review.
 * @param {string} parentPath - dotted path to parent (e.g. "clinical_sources.0")
 * @param {string} key - child key name
 */
export function shouldOmitReviewField(parentPath, key) {
  if (REVIEW_OMIT_KEYS.has(key)) return true;

  const full = parentPath ? `${parentPath}.${key}` : key;
  const parts = full.split(".").filter(Boolean);

  if (parts[0] === "metadata" && parts.length >= 2) {
    const leaf = parts[parts.length - 1];
    if (!METADATA_REVIEW_KEYS.has(leaf)) return true;
  }

  const sourceIdx = parts.indexOf("clinical_sources");
  if (sourceIdx >= 0 && parts.length > sourceIdx + 2) {
    const underSource = parts.slice(sourceIdx + 2);
    if (underSource.length === 1) {
      if (!CLINICAL_SOURCE_REVIEW_KEYS.has(underSource[0])) return true;
    } else if (underSource[0] === "metadata" && underSource.length >= 2) {
      const metaLeaf = underSource[underSource.length - 1];
      if (!METADATA_REVIEW_KEYS.has(metaLeaf)) return true;
    } else if (underSource[0] !== "metadata") {
      return true;
    }
  }

  return false;
}

export function isReviewRelevantPath(path) {
  if (!path) return true;
  const parts = String(path).split(".").filter(Boolean);
  for (let index = 0; index < parts.length; index += 1) {
    const segment = parts[index];
    if (REVIEW_OMIT_KEYS.has(segment)) return false;
    const parentPath = parts.slice(0, index).join(".");
    if (shouldOmitReviewField(parentPath, segment)) return false;
  }
  return true;
}

export function sanitizeValueForReview(value, parentPath = "") {
  if (value == null) return value;

  if (Array.isArray(value)) {
    return value
      .map((item, index) => sanitizeValueForReview(item, parentPath ? `${parentPath}.${index}` : String(index)))
      .filter((item) => item != null && !(isPlainObject(item) && !Object.keys(item).length));
  }

  if (isPlainObject(value)) {
    const out = {};
    for (const [key, child] of Object.entries(value)) {
      if (shouldOmitReviewField(parentPath, key)) continue;
      const childPath = parentPath ? `${parentPath}.${key}` : key;
      const cleaned = sanitizeValueForReview(child, childPath);
      if (cleaned == null) continue;
      if (isPlainObject(cleaned) && !Object.keys(cleaned).length) continue;
      if (Array.isArray(cleaned) && !cleaned.length) continue;
      out[key] = cleaned;
    }
    return out;
  }

  return value;
}

/** Flat label/value rows for CollapsiblePayload review mode. */
export function reviewPayloadToFields(value, parentPath = "") {
  if (value == null) return [];

  if (typeof value === "boolean" || typeof value === "number") {
    return [{ label: parentPath || "Value", value: String(value) }];
  }

  if (typeof value === "string") {
    const label = parentPath ? parentPath.split(".").pop() : "Value";
    return [{ label, value, wide: value.length > 80 }];
  }

  if (Array.isArray(value)) {
    if (!value.length) return [];
    if (value.every((item) => item == null || ["string", "number", "boolean"].includes(typeof item))) {
      const label = parentPath ? parentPath.split(".").pop() : "Items";
      return [{ label, value }];
    }
    return value.flatMap((item, index) => {
      const path = parentPath ? `${parentPath}.${index}` : String(index);
      if (Array.isArray(item)) {
        const nested = reviewPayloadToFields(item, path);
        if (nested.length) return nested;
        return [{ label: `Group ${index + 1}`, value: "—" }];
      }
      if (isPlainObject(item)) {
        if (item.operator === "always" || item.field || item.operator) {
          const text = formatSeverityRule(item) || formatTriggerCondition(item);
          return [{ label: `Condition ${index + 1}`, value: text, wide: true }];
        }
        return reviewPayloadToFields(item, path);
      }
      return [{ label: path, value: String(item) }];
    });
  }

  if (isPlainObject(value)) {
    return Object.entries(value).flatMap(([key, child]) => {
      if (shouldOmitReviewField(parentPath, key)) return [];
      const path = parentPath ? `${parentPath}.${key}` : key;
      if (isPlainObject(child) || Array.isArray(child)) {
        const nested = reviewPayloadToFields(child, path);
        if (nested.length) return nested;
        return [];
      }
      if (child == null || child === "") return [];
      return [{ label: key.replace(/_/g, " "), value: child, wide: String(child).length > 80 }];
    });
  }

  return [{ label: parentPath || "Value", value: String(value) }];
}
