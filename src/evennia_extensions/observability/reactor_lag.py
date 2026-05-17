"""Twisted reactor event-loop lag gauge.

This module provides :class:`ReactorLagProbe`, which measures how late the
Twisted reactor delivers scheduled callbacks.  High lag indicates the reactor
was blocked by synchronous work (CPU-bound computation, blocking I/O, etc.).

The probe schedules a repeating tick at a fixed *interval* and, on each tick,
computes::

    lag = now() - expected_fire_time

where ``now`` is an injectable callable returning monotonic seconds and
``expected_fire_time`` is advanced by *interval* on each tick.  Injecting both
the time source and the Twisted scheduler (``IReactorTime``) makes the probe
fully deterministic in unit tests without real sleeping or the real reactor.
"""

from __future__ import annotations

from collections.abc import Callable

from twisted.internet.task import LoopingCall


class ReactorLagProbe:
    """Measure Twisted reactor event-loop lag via a fixed-interval tick.

    The probe schedules a :class:`~twisted.internet.task.LoopingCall` that
    fires every *interval* seconds.  On each invocation it computes the lag as
    the difference between when the tick *actually* fired (reported by ``now``)
    and when it was *scheduled* to fire.

    The expected fire time is tracked on a **fixed LoopingCall cadence**
    (start + N * interval) rather than relative to the actual fire time.
    This is critical: LoopingCall anchors its schedule to the start time and
    does NOT reset after a late tick.  Tracking the baseline relative to the
    actual fire time (``actual + interval``) would overshoot LoopingCall's
    true next fire time after any stall, causing the subsequent recovery tick
    to report a negative lag and corrupt alerting thresholds.

    Both the time source and the Twisted reactor clock are injectable so that
    unit tests can drive the probe deterministically using
    :class:`~twisted.internet.task.Clock` without touching the real reactor or
    sleeping.

    Args:
        interval: Seconds between ticks.  Must be positive.
        now: Callable returning the current time in monotonic seconds.  In
            production pass ``time.monotonic``; in tests pass
            ``twisted_clock.seconds``.
        clock: An ``IReactorTime`` provider used to schedule the
            :class:`~twisted.internet.task.LoopingCall`.  Defaults to
            ``twisted.internet.reactor`` when *None*.

    Example::

        import time
        from twisted.internet import reactor
        from evennia_extensions.observability.reactor_lag import ReactorLagProbe

        probe = ReactorLagProbe(interval=5.0, now=time.monotonic)
        probe.start()
        # … later …
        print(probe.current_lag())
        probe.stop()
    """

    def __init__(
        self,
        interval: float,
        now: Callable[[], float],
        clock: object | None = None,
    ) -> None:
        """Initialise the probe without starting it.

        Args:
            interval: Seconds between ticks.
            now: Callable returning current time in monotonic seconds.
            clock: Optional ``IReactorTime`` provider; defaults to the real
                Twisted reactor when *None*.
        """
        self._interval = interval
        self._now = now
        self._clock = clock

        self._lag: float = 0.0
        self._next_expected: float | None = None

        self._loop = LoopingCall(self._tick)
        if clock is not None:
            self._loop.clock = clock

    def _tick(self) -> None:
        """Record the lag for the current tick.

        Computes ``now() - expected_fire_time`` and stores the result in
        ``_lag``.  Advances ``_next_expected`` by a **fixed interval** (not
        relative to the actual fire time) to stay aligned with LoopingCall's
        start-anchored cadence.

        Using ``actual + interval`` instead would overshoot after any late
        tick: LoopingCall's next scheduled time would still be
        ``start + N * interval``, but ``_next_expected`` would be ahead of it,
        making the immediately-following on-time tick appear to have negative
        lag and corrupting alerting.
        """
        actual = self._now()
        if self._next_expected is not None:
            self._lag = actual - self._next_expected
            self._next_expected += self._interval

    def start(self) -> None:
        """Start the periodic lag measurement.

        The first tick fires after one full *interval* (``now=False``) so that
        the probe can measure the lag of that first scheduled callback rather
        than firing immediately.
        """
        # Record when we expect the first tick.
        self._next_expected = self._now() + self._interval
        self._loop.start(self._interval, now=False)

    def current_lag(self) -> float:
        """Return the most recently measured lag in seconds.

        Returns:
            Lag in seconds (``actual_fire_time - expected_fire_time``).
            Returns ``0.0`` before the first tick has fired.
        """
        return self._lag

    def stop(self) -> None:
        """Stop the periodic measurement and cancel the pending callback.

        Safe to call before the first tick fires.  Idempotent — calling
        ``stop()`` on an already-stopped probe does not raise.
        """
        if self._loop.running:
            self._loop.stop()
