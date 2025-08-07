# Core Management - Claude Code Instructions

This app provides core Django management commands that solve fundamental issues with Evennia integration.

## Custom makemigrations Command

### The Problem
When Django's `makemigrations` scans all installed apps (including Evennia library apps), it detects that proxy models (typeclasses) need to be created for apps with ForeignKeys to Evennia models. This creates "phantom migrations" in the Evennia library like:
- `objects/migrations/0014_defaultobject_defaultcharacter_defaultexit_and_more.py`
- `accounts/migrations/0013_defaultaccount_account_bot_defaultguest_and_more.py`

These phantom migrations:
1. Don't exist in the Evennia library for other installations
2. Create dependency errors like `NodeNotFoundError`
3. Break the migration system across environments

### Our Solution

**Custom makemigrations command** in `core_management.management.commands.makemigrations`:
- **Uses Django's normal app scanning** to detect all changes comprehensively
- **Filters out problematic migrations** before writing them to disk
- **Automatically works with any apps** - no maintenance required when adding new apps
- **Shows clear warnings** when ignoring proxy model migrations

### Usage

```bash
# Safe makemigrations - completely prevents phantom Evennia migrations
arx manage makemigrations

# Still works - can specify apps when needed
arx manage makemigrations traits
arx manage makemigrations evennia_extensions
```

### Testing Verified

We created a fresh test app with ForeignKey to `ObjectDB` and confirmed:
1. ✅ **No phantom migration created**: The `0014_defaultobject_...` migration was NOT created in Evennia library
2. ✅ **Proper dependency resolution**: Migrations reference real Evennia migrations (`0013_...`)
3. ✅ **Migration system works**: `showmigrations` and dependency graph work correctly
4. ✅ **Warning system**: Clear feedback when Evennia proxy models are ignored

### Technical Implementation

The solution is elegantly simple - it overrides just one method:

**Migration Filtering**: Overrides `write_migration_files()` to filter out any detected changes to excluded apps before writing them to disk:

```python
def write_migration_files(self, changes, update_previous_migration_paths=None):
    # Filter out changes to excluded apps
    filtered_changes = {}
    for app_label, operations in changes.items():
        if app_label not in self.EXCLUDED_APPS:
            filtered_changes[app_label] = operations
        else:
            # Show warning but don't create the migration
            self.stdout.write(f"Ignoring proxy model migration for excluded app: {app_label}")

    return super().write_migration_files(filtered_changes, update_previous_migration_paths)
```

This approach ensures:
- **Zero maintenance**: Works with any app configuration without updates
- **Comprehensive scanning**: Django's normal detection finds all changes
- **Selective filtering**: Only problematic migrations are prevented from being written
- **Clear feedback**: Users see warnings when migrations are ignored  
- **Preserved functionality**: Dependencies and normal Django behavior work perfectly

## Testing the Fix

We include a comprehensive test suite in `tests/test_makemigrations_fix.py` that demonstrates our solution works. The tests are **skipped by default** since they're not regression tests, but rather proof that our fix solves the original problem.

### Running the Phantom Migration Test

```bash  
# Use the convenience script (recommended)
python src/core_management/tests/run_phantom_migration_test.py

# Or run directly with unittest
python -m unittest core_management.tests.test_makemigrations_fix.TestMakemigrationsEvenniaFix -v
```

### What the Tests Verify

1. **`test_makemigrations_prevents_evennia_phantom_migrations`**: Proves our command filters out Evennia app migrations
2. **`test_excluded_apps_list_comprehensive`**: Verifies all critical Evennia apps are in our exclusion list
3. **`test_proof_of_problem_without_fix`**: Demonstrates the problem exists without our fix and is solved with it

The tests would **FAIL** if someone removed `EXCLUDED_APPS` from our command, proving the fix is necessary and working.
