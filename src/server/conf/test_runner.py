"""
Custom Evennia test runner with timing information.

This runner extends Evennia's EvenniaTestSuiteRunner to add timing data
for individual tests, similar to how migrations display timing.
"""

import os
import sys
import time
import unittest

from evennia.server.tests.testrunner import EvenniaTestSuiteRunner


class TimedEvenniaTestRunner(EvenniaTestSuiteRunner):
    """
    Custom test runner that extends EvenniaTestSuiteRunner with timing information.

    Timing is displayed when ARX_TEST_TIMING environment variable is set.
    Uses a minimal approach that doesn't interfere with result class inheritance.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_timings = []

    def setup_test_environment(self, **kwargs):
        """Set up test environment with timing notification."""
        super().setup_test_environment(**kwargs)
        if os.environ.get("ARX_TEST_TIMING") and self.verbosity >= 2:
            print("Running tests with timing information...")
            sys.stdout.flush()

        # Set up timing tracking if requested
        if os.environ.get("ARX_TEST_TIMING"):
            self._setup_timing()

    def _setup_timing(self):
        """Set up minimal timing tracking by patching unittest.TestCase."""
        # Store original methods
        if not hasattr(unittest.TestCase, "_original_run"):
            unittest.TestCase._original_run = unittest.TestCase.run

        # Store reference to runner instance for access in the patched method
        runner_instance = self

        def timed_run(self, result=None):
            """Run a test with timing."""
            start_time = time.time()
            test_result = unittest.TestCase._original_run(self, result)
            duration = time.time() - start_time

            # Store timing data
            test_name = (
                f"{self.__class__.__module__}.{self.__class__.__name__}."
                f"{self._testMethodName}"
            )
            runner_instance.test_timings.append((test_name, duration))

            # Only show timing info at higher verbosity
            if os.environ.get("ARX_TEST_TIMING"):
                print(f"  {test_name} ... {duration:.3f}s")
                sys.stdout.flush()

            return test_result

        # Apply the patch
        unittest.TestCase.run = timed_run

    def teardown_test_environment(self, **kwargs):
        """Clean up test environment and restore original methods."""
        # Print slowest tests summary if timing was enabled
        if os.environ.get("ARX_TEST_TIMING") and self.test_timings:
            self._print_slowest_tests()

        # Restore original methods if we patched them
        if hasattr(unittest.TestCase, "_original_run"):
            unittest.TestCase.run = unittest.TestCase._original_run
            delattr(unittest.TestCase, "_original_run")

        super().teardown_test_environment(**kwargs)

    def _print_slowest_tests(self):
        """Print the 10 slowest tests."""
        if not self.test_timings:
            return

        # Sort by duration (descending) and take top 10
        slowest = sorted(self.test_timings, key=lambda x: x[1], reverse=True)[:10]

        print("\n" + "=" * 70)
        print("10 SLOWEST TESTS")
        print("=" * 70)

        for i, (test_name, duration) in enumerate(slowest, 1):
            print(f"{i:2d}. {test_name}")
            print(f"    {duration:.3f}s")
            print()

        print("=" * 70)
        sys.stdout.flush()
