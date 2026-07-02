export function ruleVisibilityMeta(status) {
  if (status === "approved") {
    return {
      label: "Published",
      shortLabel: "Live in chat",
      hint: "Used by chat recommendations after clinical approval.",
      tone: "published",
    };
  }
  if (status === "draft") {
    return {
      label: "Draft",
      shortLabel: "Admin only",
      hint: "Visible here for review only. Chat will not use this rule until approved.",
      tone: "draft",
    };
  }
  return {
    label: "Retired",
    shortLabel: "Not in chat",
    hint: "Removed from active clinical use.",
    tone: "retired",
  };
}

export function tabVisibilityBanner(tab) {
  if (tab === "draft") {
    return {
      tone: "warning",
      title: "Draft rules",
      message: "These rules are admin-only. They do not appear in chat until approved by clinical_lead.",
    };
  }
  if (tab === "approved") {
    return {
      tone: "success",
      title: "Published rules",
      message: "Approved rules are live in chat recommendations and the CDSS constraint engine.",
    };
  }
  if (tab === "retired") {
    return {
      tone: "danger",
      title: "Retired rules",
      message: "Retired rules are kept for audit but are no longer applied in chat.",
    };
  }
  return {
    tone: "info",
    title: "All rule statuses",
    message: "Draft = admin review only · Published = live in chat · Retired = archived",
  };
}
