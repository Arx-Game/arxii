"""
Custom Evennia test runner with timing information and parallel-worker compatibility.

This runner extends Evennia's EvenniaTestSuiteRunner to add:
- Timing data for individual tests (when ARX_TEST_TIMING env var is set)
- Parallel worker compatibility on Windows (spawn start method)

## Windows parallel worker issue

On Windows, multiprocessing uses the "spawn" start method: each worker boots a fresh
interpreter. Django's parallel test runner calls `django.setup()` then
`setup_test_environment()` (the bare utility function from django.test.utils) in workers.
The bare utility function does NOT call `evennia._init()`, so `evennia.SESSION_HANDLER`
stays None in workers.

When `AccountFactory()` is called in `setUpTestData`, Evennia tries to add the default
cmdset. If the cmdset import fails for any reason, Evennia tries to emit an error via
`account.msg()`, which accesses `evennia.SESSION_HANDLER.sessions_from_account()` and
crashes with AttributeError because SESSION_HANDLER is None.

The fix: subclass `ParallelTestSuite` with a custom `init_worker` that calls
`evennia._init()` AFTER `django.setup()` completes (via the base `_init_worker`).
This initializes `SESSION_HANDLER` so account creation in workers doesn't crash.
"""

import os
import sys
import time
import unittest

from django.test.runner import ParallelTestSuite
from evennia.server.tests.testrunner import EvenniaTestSuiteRunner


def _arx_init_worker(*args, **kwargs) -> None:
    """
    Worker initializer for ArxParallelTestSuite.

    Wraps Django's _init_worker to also call evennia._init() in workers where
    SESSION_HANDLER would otherwise remain None (Windows spawn workers).

    Lives at module level (not as a method) because Django accesses the
    init_worker class attribute via ``self.init_worker.__func__``, which requires
    the attribute to be a bound method (not a staticmethod or plain function).
    Assigning a module-level function to a class attribute creates the required
    descriptor so that ``instance.init_worker.__func__`` resolves correctly.

    The *args/**kwargs forwarding insulates this wrapper from Django version
    drift — Django passes initargs positionally, so we forward both positional
    and keyword arguments to the base _init_worker.
    """
    from django.test.runner import _init_worker

    _init_worker(*args, **kwargs)

    # Initialize evennia in workers where SESSION_HANDLER is not already set.
    # On Linux fork workers, the parent's evennia._init() carries over via the
    # forked memory image. On Windows spawn workers, the worker is a fresh
    # interpreter and evennia is uninitialized. The SESSION_HANDLER check
    # handles both cases without needing a platform-specific branch.
    import evennia

    if evennia.SESSION_HANDLER is None:
        evennia._init()


class ArxParallelTestSuite(ParallelTestSuite):
    """
    ParallelTestSuite that initializes evennia in each spawn worker.

    Overrides init_worker to call evennia._init() after django.setup()
    so that SESSION_HANDLER and other evennia globals are available in workers.
    """

    init_worker = _arx_init_worker  # type: ignore[assignment]


class TimedEvenniaTestRunner(EvenniaTestSuiteRunner):
    """
    Custom test runner that extends EvenniaTestSuiteRunner with timing information
    and parallel worker compatibility.

    Timing is displayed when ARX_TEST_TIMING environment variable is set.
    Uses a minimal approach that doesn't interfere with result class inheritance.
    """

    parallel_test_suite = ArxParallelTestSuite

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
                f"{self.__class__.__module__}.{self.__class__.__name__}.{self._testMethodName}"
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
