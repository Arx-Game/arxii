"""Tests for evennia_extensions.observability.subsystem_timing."""

from django.test import TestCase, override_settings


class SubsystemTimingEnabledTests(TestCase):
    """time_subsystem records histogram values when observability is enabled."""

    def setUp(self) -> None:
        """Reset module-level histogram state before each test."""
        from evennia_extensions.observability import subsystem_timing

        subsystem_timing._reset_for_testing()

    @override_settings(OBSERVABILITY_ENABLED=True)
    def test_records_duration_when_enabled(self) -> None:
        """A completed block increments count to 1 and records a positive sum."""
        from evennia_extensions.observability.subsystem_timing import get_registry, time_subsystem

        with time_subsystem("flow", "emit_event"):
            pass

        registry = get_registry()
        count = registry.get_sample_value(
            "subsystem_flow_duration_seconds_count", {"name": "emit_event"}
        )
        total = registry.get_sample_value(
            "subsystem_flow_duration_seconds_sum", {"name": "emit_event"}
        )
        self.assertEqual(count, 1.0)
        self.assertGreater(total, 0.0)

    @override_settings(OBSERVABILITY_ENABLED=True)
    def test_exception_still_records_and_reraises(self) -> None:
        """An exception inside the block still increments the count AND propagates."""
        from evennia_extensions.observability.subsystem_timing import get_registry, time_subsystem

        err_msg = "boom"
        with self.assertRaises(ValueError):
            with time_subsystem("flow", "exploding_flow"):
                raise ValueError(err_msg)

        registry = get_registry()
        count = registry.get_sample_value(
            "subsystem_flow_duration_seconds_count", {"name": "exploding_flow"}
        )
        self.assertEqual(count, 1.0)

    def test_disabled_is_noop(self) -> None:
        """When observability is disabled, time_subsystem is a no-op that touches no metrics."""
        from evennia_extensions.observability.subsystem_timing import get_registry, time_subsystem

        # Normal exit: no error, no metric created.
        with time_subsystem("flow", "emit_event"):
            pass

        registry = get_registry()
        count = registry.get_sample_value(
            "subsystem_flow_duration_seconds_count", {"name": "emit_event"}
        )
        self.assertIsNone(count)

    def test_disabled_still_propagates_exceptions(self) -> None:
        """When disabled, exceptions raised inside the block still propagate."""
        from evennia_extensions.observability.subsystem_timing import time_subsystem

        exc_msg = "should escape"
        with self.assertRaises(RuntimeError):
            with time_subsystem("flow", "bad_flow"):
                raise RuntimeError(exc_msg)

    @override_settings(OBSERVABILITY_ENABLED=True)
    def test_repeated_calls_reuse_histogram(self) -> None:
        """Multiple calls for the same subsystem do not raise and accumulate counts."""
        from evennia_extensions.observability.subsystem_timing import get_registry, time_subsystem

        with time_subsystem("command", "look"):
            pass
        with time_subsystem("command", "look"):
            pass

        registry = get_registry()
        count = registry.get_sample_value(
            "subsystem_command_duration_seconds_count", {"name": "look"}
        )
        self.assertEqual(count, 2.0)

    @override_settings(OBSERVABILITY_ENABLED=True)
    def test_different_subsystems_use_separate_histograms(self) -> None:
        """Each subsystem gets its own Histogram metric, independently."""
        from evennia_extensions.observability.subsystem_timing import get_registry, time_subsystem

        with time_subsystem("command", "look"):
            pass
        with time_subsystem("script", "weather_tick"):
            pass

        registry = get_registry()
        cmd_count = registry.get_sample_value(
            "subsystem_command_duration_seconds_count", {"name": "look"}
        )
        script_count = registry.get_sample_value(
            "subsystem_script_duration_seconds_count", {"name": "weather_tick"}
        )
        self.assertEqual(cmd_count, 1.0)
        self.assertEqual(script_count, 1.0)
