"""
Custom Django test runner with timing information.

This runner wraps Django's default DiscoverRunner to add timing data
for individual tests, similar to how migrations display timing.
"""

import sys
import time

from django.test.runner import DebugSQLTextTestResult, DiscoverRunner


class TimedTestResult(DebugSQLTextTestResult):
    """Test result class that adds timing information."""

    def __init__(self, stream, descriptions, verbosity, **kwargs):
        super().__init__(stream, descriptions, verbosity)
        self.verbosity = verbosity
        self.test_timings = {}

    def startTest(self, test):
        """Start timing a test."""
        self.test_timings[test] = time.time()
        super().startTest(test)

    def stopTest(self, test):
        """Stop timing a test and display timing if verbose enough."""
        super().stopTest(test)

        end_time = time.time()
        start_time = self.test_timings.get(test)

        if start_time is not None:
            duration = end_time - start_time

            # Only show timing at verbosity 2 or higher
            if self.verbosity >= 2:
                test_name = (
                    f"{test.__class__.__module__}.{test.__class__.__name__}"
                    f".{test._testMethodName}"
                )
                self.stream.write(f"  {test_name} ... {duration:.3f}s\n")
                self.stream.flush()


class TimedTestRunner(DiscoverRunner):
    """
    Custom test runner that adds timing information for individual tests.

    Timing is displayed when verbosity >= 2, similar to migration timing.
    """

    def get_resultclass(self):
        """Return our custom result class."""
        return TimedTestResult

    def setup_test_environment(self, **kwargs):
        """Set up test environment with timing notification."""
        super().setup_test_environment(**kwargs)
        if self.verbosity >= 2:
            print("Running tests with timing information...")
            sys.stdout.flush()
