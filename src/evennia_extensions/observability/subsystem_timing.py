"""Per-subsystem timing histograms for Arx II observability.

Provides :func:`time_subsystem`, a context manager that records the elapsed
duration of a named operation into a per-subsystem Prometheus Histogram.

When observability is disabled (the default), the context manager is a cheap
no-op: it does not create or touch any Prometheus metric object, and it still
lets exceptions propagate unchanged.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
import time

from prometheus_client import CollectorRegistry, Histogram

from evennia_extensions.observability.settings import observability_config

# Module-owned registry — never touches the global default registry.
_registry: CollectorRegistry = CollectorRegistry()

# One Histogram per subsystem name; keyed by subsystem string.
_histograms: dict[str, Histogram] = {}


def get_registry() -> CollectorRegistry:
    """Return the module-owned Prometheus CollectorRegistry.

    Returns:
        The CollectorRegistry that holds all subsystem timing Histograms.
    """
    return _registry


def _get_or_create_histogram(subsystem: str) -> Histogram:
    """Return the Histogram for *subsystem*, creating it on first call.

    Uses a simple dict cache so the same Histogram object is always returned
    for a given *subsystem* string.  This avoids the ``ValueError: Duplicate
    timeseries`` error that prometheus_client raises if you attempt to register
    the same metric name twice.

    Args:
        subsystem: Short string identifying the subsystem (e.g. "command",
            "flow", "script").

    Returns:
        The Histogram registered for this subsystem.
    """
    if subsystem not in _histograms:
        metric_name = f"subsystem_{subsystem}_duration_seconds"
        _histograms[subsystem] = Histogram(
            metric_name,
            f"Duration of {subsystem} operations in seconds",
            ["name"],
            registry=_registry,
        )
    return _histograms[subsystem]


@contextmanager
def time_subsystem(subsystem: str, name: str) -> Generator[None]:
    """Time the wrapped block and record its duration as a Prometheus observation.

    When observability is disabled, this is a cheap no-op context manager that
    still allows exceptions to propagate.

    On normal exit the elapsed seconds are recorded into the Histogram for
    *subsystem* with ``name`` as the label value.  On exception the duration
    is recorded **before** the exception is re-raised unchanged.

    Args:
        subsystem: Identifies the Histogram to use (e.g. ``"command"``,
            ``"flow"``, ``"script"``).  One Histogram is created per unique
            subsystem value; subsequent calls for the same subsystem reuse the
            existing Histogram (idempotent).
        name: Label value for this specific operation (e.g. the command name
            or flow name).  Recorded as the ``name`` label on the sample.

    Yields:
        Nothing — used only for ``with`` statement protocol.

    Example::

        with time_subsystem("command", "look"):
            handle_look_command()
    """
    if not observability_config().enabled:
        # Fast disabled path: no metric objects touched.
        try:
            yield
        finally:
            pass
        return

    histogram = _get_or_create_histogram(subsystem)
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        histogram.labels(name=name).observe(elapsed)


def _reset_for_testing() -> None:
    """Reset module-level registry and histogram cache.

    **For use in tests only.**  Replaces the module-level registry and
    histogram dict with fresh instances so each test starts from a clean
    slate, preventing cross-test state leakage.
    """
    global _registry, _histograms  # noqa: PLW0603
    _registry = CollectorRegistry()
    _histograms = {}
