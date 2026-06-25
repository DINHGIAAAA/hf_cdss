import { useHorizontalResize } from "../hooks/useHorizontalResize.js";

export function ResizableSplit({
  ariaLabel = "Resize panels",
  className = "",
  initial = 300,
  listMin = 200,
  listMax = 520,
  storageKey,
  list,
  detail,
}) {
  const { width, containerRef, onPointerDown } = useHorizontalResize({
    collapseThreshold: 120,
    edge: "left",
    initial,
    max: listMax,
    min: listMin,
    storageKey,
  });

  return (
    <div
      className={`resizable-split${className ? ` ${className}` : ""}`}
      ref={containerRef}
      style={{ "--split-list-width": `${width}px` }}
    >
      <div className="resizable-split-list admin-clip">{list}</div>
      <div
        aria-label={ariaLabel}
        aria-orientation="vertical"
        aria-valuemax={listMax}
        aria-valuemin={listMin}
        aria-valuenow={Math.round(width)}
        className="resizable-split-handle"
        onPointerDown={onPointerDown}
        role="separator"
        tabIndex={0}
      />
      <div className="resizable-split-detail admin-clip">{detail}</div>
    </div>
  );
}
