import { useCallback, useEffect, useRef, useState } from "react";

export function useHorizontalResize({
  initial = 320,
  min = 0,
  max = 640,
  collapseThreshold = 56,
  storageKey,
  edge = "right",
}) {
  const [width, setWidth] = useState(() => {
    if (!storageKey) return initial;
    const raw = localStorage.getItem(storageKey);
    if (raw === null) return initial;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : initial;
  });

  const containerRef = useRef(null);
  const draggingRef = useRef(false);
  const widthRef = useRef(width);

  useEffect(() => {
    widthRef.current = width;
  }, [width]);

  const persistWidth = useCallback(
    (value) => {
      if (storageKey) {
        localStorage.setItem(storageKey, String(value));
      }
    },
    [storageKey],
  );

  const clampWidth = useCallback(
    (value) => Math.min(max, Math.max(min, value)),
    [max, min],
  );

  const onPointerDown = useCallback((event) => {
    event.preventDefault();
    draggingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }, []);

  useEffect(() => {
    function onPointerMove(event) {
      if (!draggingRef.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const next =
        edge === "right"
          ? clampWidth(rect.right - event.clientX)
          : clampWidth(event.clientX - rect.left);
      setWidth(next);
    }

    function onPointerUp() {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      persistWidth(widthRef.current);
    }

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [clampWidth, edge, persistWidth]);

  const isOpen = width > collapseThreshold;

  const snapWidth = useCallback(
    (value) => {
      const next = clampWidth(value);
      setWidth(next);
      persistWidth(next);
    },
    [clampWidth, persistWidth],
  );

  return {
    width,
    isOpen,
    containerRef,
    onPointerDown,
    setWidth: snapWidth,
  };
}
