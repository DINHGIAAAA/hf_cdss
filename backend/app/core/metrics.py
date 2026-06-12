from __future__ import annotations

import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Iterator


_lock = threading.Lock()
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
_histograms: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = defaultdict(list)


def _labels(labels: dict[str, str] | None = None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((labels or {}).items()))


def increment(name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
    with _lock:
        _counters[(name, _labels(labels))] += value


def observe(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    with _lock:
        samples = _histograms[(name, _labels(labels))]
        samples.append(value)
        if len(samples) > 1000:
            del samples[: len(samples) - 1000]


@contextmanager
def timer(name: str, labels: dict[str, str] | None = None) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        observe(name, time.perf_counter() - started, labels)


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    encoded = ",".join(f'{key}="{value}"' for key, value in labels)
    return f"{{{encoded}}}"


def _format_quantile_labels(labels: tuple[tuple[str, str], ...], quantile: str) -> str:
    all_labels = (("quantile", quantile), *labels)
    return _format_labels(all_labels)


def render_prometheus() -> str:
    lines: list[str] = []
    with _lock:
        counters = dict(_counters)
        histograms = {key: list(values) for key, values in _histograms.items()}

    metric_names = {name for name, _ in counters}
    for name in sorted(metric_names):
        lines.append(f"# TYPE {name} counter")
    for (name, labels), value in sorted(counters.items()):
        lines.append(f"{name}{_format_labels(labels)} {value:g}")

    histogram_names = {name for name, _ in histograms}
    for name in sorted(histogram_names):
        lines.append(f"# TYPE {name}_seconds summary")
    for (name, labels), values in sorted(histograms.items()):
        if not values:
            continue
        count = len(values)
        total = sum(values)
        sorted_values = sorted(values)
        p50 = sorted_values[int((count - 1) * 0.5)]
        p95 = sorted_values[int((count - 1) * 0.95)]
        label_text = _format_labels(labels)
        lines.append(f"{name}_seconds_count{label_text} {count}")
        lines.append(f"{name}_seconds_sum{label_text} {total:.6f}")
        lines.append(f"{name}_seconds{_format_quantile_labels(labels, '0.5')} {p50:.6f}")
        lines.append(f"{name}_seconds{_format_quantile_labels(labels, '0.95')} {p95:.6f}")

    return "\n".join(lines) + "\n"
