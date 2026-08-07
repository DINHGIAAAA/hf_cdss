import { useEffect } from "react";

/**
 * Full-screen review dialog. Replaces the side preview panel.
 */
export function AdminDetailModal({ ariaLabel, onClose, children, className = "" }) {
  useEffect(() => {
    const onKey = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div className="admin-detail-modal" onClick={onClose} role="presentation">
      <div
        aria-label={ariaLabel}
        aria-modal="true"
        className={`admin-detail-panel admin-detail-panel--modal ${className}`.trim()}
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        {children}
      </div>
    </div>
  );
}
