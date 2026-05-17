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
