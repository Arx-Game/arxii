#!/usr/bin/env python
"""
Script to run the phantom migration test explicitly.

This test is normally skipped, but this script allows running it
to verify our makemigrations fix is working correctly.

Usage:
    python src/core_management/tests/run_phantom_migration_test.py
"""

from pathlib import Path
import sys
import unittest

# Add the src directory to Python path
script_dir = Path(__file__).resolve().parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

if __name__ == "__main__":
    print("Running phantom migration test to verify our makemigrations fix...")
    print("=" * 60)

    # Import and run the specific test, removing the skip decorator
    from core_management.tests.test_makemigrations_fix import (
        TestMakemigrationsEvenniaFix,
    )

    # Remove the skip decorator to actually run the test
    TestMakemigrationsEvenniaFix.__unittest_skip__ = False
    TestMakemigrationsEvenniaFix.__unittest_skip_why__ = None

    # Run the tests
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMakemigrationsEvenniaFix)
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("SUCCESS: Our makemigrations fix is working correctly!")
        print("   - Phantom Evennia migrations are being prevented")
        print("   - EXCLUDED_APPS configuration is comprehensive")
        print("   - The fix demonstrates clear before/after behavior")
    else:
        print("FAILURE: There may be an issue with our makemigrations fix")
        print("   - Check the test output above for details")

    sys.exit(0 if result.wasSuccessful() else 1)
