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
- **Defaults to our apps only**: `flows`, `evennia_extensions`, `roster`, `traits`, `behaviors`
- **Filters out Evennia app migrations** using `write_migration_files()` override
- **Shows clear warnings** when ignoring Evennia proxy model migrations

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

The solution works at two levels:

1. **App Selection**: When no apps are specified, defaults to our custom apps only (`flows`, `evennia_extensions`, `roster`, `traits`, `behaviors`)

2. **Migration Filtering**: Overrides `write_migration_files()` to filter out any detected changes to Evennia apps before writing them to disk:

```python
def write_migration_files(self, changes, update_previous_migration_paths=None):
    # Filter out changes to Evennia apps
    filtered_changes = {}
    for app_label, operations in changes.items():
        if app_label not in self.EVENNIA_APPS:
            filtered_changes[app_label] = operations
        else:
            # Show warning but don't create the migration
            self.stdout.write(f"Ignoring proxy model migration for Evennia app: {app_label}")

    return super().write_migration_files(filtered_changes, update_previous_migration_paths)
```

This dual approach ensures:
- Django detects proxy model changes in Evennia apps (normal behavior)
- But those changes are filtered out before being written to disk
- Our app migrations are created normally
- Dependencies to existing Evennia migrations continue to work
- Clear user feedback about what's being ignored
