"""Tests for evennia_extensions.observability.reactor_lag."""

from django.test import TestCase
from twisted.internet.task import Clock


class ReactorLagProbeInitTests(TestCase):
    """ReactorLagProbe reports zero lag before the first tick fires."""

    def test_lag_is_zero_before_first_tick(self) -> None:
        """A freshly constructed probe returns 0.0 from current_lag()."""
        from evennia_extensions.observability.reactor_lag import ReactorLagProbe

        clock = Clock()
        probe = ReactorLagProbe(interval=1.0, now=clock.seconds, clock=clock)
        probe.start()
        self.assertEqual(probe.current_lag(), 0.0)
        probe.stop()


class ReactorLagProbeMeasurementTests(TestCase):
    """ReactorLagProbe measures the difference between scheduled and actual firing time."""

    def test_lag_is_measured(self) -> None:
        """Advancing the clock by interval+0.4 yields a measured lag of ~0.4 s."""
        from evennia_extensions.observability.reactor_lag import ReactorLagProbe

        clock = Clock()
        probe = ReactorLagProbe(interval=1.0, now=clock.seconds, clock=clock)
        probe.start()

        # Advance the clock by 1.4 s instead of exactly 1.0 s — simulates
        # the reactor being blocked for an extra 0.4 s before the tick fires.
        clock.advance(1.4)

        self.assertAlmostEqual(probe.current_lag(), 0.4, places=5)
        probe.stop()

    def test_lag_updates_on_subsequent_ticks(self) -> None:
        """After a second tick the lag reflects the most recent measurement only."""
        from evennia_extensions.observability.reactor_lag import ReactorLagProbe

        clock = Clock()
        probe = ReactorLagProbe(interval=1.0, now=clock.seconds, clock=clock)
        probe.start()

        # First tick fires on time (1.0 s advance → lag ≈ 0.0).
        clock.advance(1.0)
        self.assertAlmostEqual(probe.current_lag(), 0.0, places=5)

        # Second tick fires 0.2 s late.
        clock.advance(1.2)
        self.assertAlmostEqual(probe.current_lag(), 0.2, places=5)
        probe.stop()


class ReactorLagProbeRecoveryTests(TestCase):
    """ReactorLagProbe reports non-negative lag after a stall-then-recovery tick sequence."""

    def test_post_stall_recovery_lag_is_not_negative(self) -> None:
        """After a stall tick, the subsequent on-cadence tick must not report negative lag.

        LoopingCall anchors its cadence to start time (start+1·interval,
        start+2·interval, …).  After a late tick the next scheduled fire time
        is still start+2·interval — it does NOT reset relative to when the
        stall tick actually fired.  Tracking _next_expected relative to the
        actual fire time (actual + interval) would overshoot that anchor and
        produce a negative lag on the recovery tick.  Tracking with a fixed
        increment (_next_expected += interval) stays aligned with LoopingCall
        and keeps the recovery lag >= 0.
        """
        from evennia_extensions.observability.reactor_lag import ReactorLagProbe

        clock = Clock()
        probe = ReactorLagProbe(interval=1.0, now=clock.seconds, clock=clock)
        probe.start()

        # Tick 1: on time (1.0 s elapsed → lag ≈ 0.0).
        clock.advance(1.0)
        self.assertAlmostEqual(probe.current_lag(), 0.0, places=5)

        # Tick 2: stall — 0.4 s late (1.4 s elapsed → lag ≈ 0.4).
        clock.advance(1.4)
        self.assertAlmostEqual(probe.current_lag(), 0.4, places=5)

        # Tick 3: recovery — LoopingCall fires at start+3·interval = 3.0 s.
        # After the stall tick fired at 2.4 s, LoopingCall schedules the next
        # tick at 3.0 s (it re-anchors to the original cadence).  We advance
        # exactly 0.6 s so the clock reaches 3.0 s and exactly one tick fires.
        clock.advance(0.6)
        recovery_lag = probe.current_lag()
        # Must NOT be negative (the core correctness invariant).
        self.assertGreaterEqual(recovery_lag, 0.0)
        # Must be close to zero: LoopingCall fired at exactly 3.0 s, expected 3.0 s.
        self.assertAlmostEqual(recovery_lag, 0.0, places=5)

        probe.stop()


class ReactorLagProbeStopTests(TestCase):
    """ReactorLagProbe.stop() cancels further measurement cleanly."""

    def test_stop_cancels_further_measurements(self) -> None:
        """After stop(), advancing the clock does not change current_lag() and does not raise."""
        from evennia_extensions.observability.reactor_lag import ReactorLagProbe

        clock = Clock()
        probe = ReactorLagProbe(interval=1.0, now=clock.seconds, clock=clock)
        probe.start()

        # Let one tick fire so we have a non-zero lag baseline.
        clock.advance(1.4)
        lag_before_stop = probe.current_lag()

        probe.stop()

        # Advancing the clock after stop() must not raise and must not update lag.
        clock.advance(10.0)
        self.assertAlmostEqual(probe.current_lag(), lag_before_stop, places=5)

    def test_stop_before_any_tick_does_not_raise(self) -> None:
        """Calling stop() before the first tick fires is safe and leaves lag at 0.0."""
        from evennia_extensions.observability.reactor_lag import ReactorLagProbe

        clock = Clock()
        probe = ReactorLagProbe(interval=1.0, now=clock.seconds, clock=clock)
        probe.start()
        probe.stop()

        self.assertEqual(probe.current_lag(), 0.0)
