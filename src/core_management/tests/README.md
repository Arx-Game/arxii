# Core Management Tests

## Phantom Migration Test

The `test_makemigrations_fix.py` contains tests that verify our custom `makemigrations` command prevents phantom Evennia migrations.

### Why These Tests Are Skipped by Default

These tests are **demonstration tests**, not regression tests. They prove our fix works but aren't needed for normal development since:

1. The problem we solved is architectural, not code-based
2. We're not worried about regressions in this specific fix
3. The tests serve more as documentation of the problem we solved

### Running the Tests

```bash
python src/core_management/tests/run_phantom_migration_test.py
```

### What Gets Tested

1. **Filtering Works**: Our command successfully filters out Evennia app migrations
2. **Comprehensive Exclusion**: All problematic Evennia apps are in our exclusion list  
3. **Problem Demonstration**: Shows the issue exists without our fix and is resolved with it

### Test Results

- **PASS**: Our fix is working correctly, phantom migrations are prevented
- **FAIL**: Something is wrong with our EXCLUDED_APPS configuration or filtering logic

The tests are designed to fail if someone accidentally removes our `EXCLUDED_APPS` configuration, making them a safeguard against breaking the fix.
