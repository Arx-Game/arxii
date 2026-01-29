"""Reset all migrations to a clean state without losing data.

This script:
1. Fake-migrates all apps down to zero (clears migration history only)
2. Deletes all migration files (except __init__.py)
3. Regenerates fresh migrations with makemigrations
4. Fake-migrates up (marks as applied without running, since schema exists)

Safe because:
- --fake means no actual schema changes
- Data stays in place throughout
- We're just resetting migration history and files
"""

from pathlib import Path
import shutil
import subprocess
import sys

# Apps to reset (in dependency order for migrate zero)
# Listed in reverse dependency order so dependents are zeroed before dependencies
APPS_REVERSE_ORDER = [
    # Apps that depend on others (zero these first)
    "codex",
    "character_creation",
    "roster",
    "progression",
    "stories",
    "scenes",
    "goals",
    "societies",
    # Mid-level apps
    "character_sheets",
    "conditions",
    "magic",
    "skills",
    "classes",
    "relationships",
    # Base apps (zero these last)
    "distinctions",
    "forms",
    "species",
    "traits",
    "mechanics",
    "consent",
]

# For makemigrations, we want base apps first
APPS_DEPENDENCY_ORDER = list(reversed(APPS_REVERSE_ORDER))

SRC_DIR = Path(__file__).parent.parent / "src"
WORLD_DIR = SRC_DIR / "world"


def run_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(  # noqa: S603
        cmd, check=False, cwd=SRC_DIR, capture_output=True, text=True
    )
    if check and result.returncode != 0:
        print(f"  FAILED: {result.stderr}")
        sys.exit(1)
    return result


def fake_migrate_zero():
    """Fake-migrate all apps to zero."""
    print("\n" + "=" * 60)
    print("Step 1: Fake-migrate all apps to zero")
    print("=" * 60)

    for app in APPS_REVERSE_ORDER:
        print(f"\nMigrating {app} to zero...")
        result = run_command(
            ["uv", "run", "arx", "manage", "migrate", app, "zero", "--fake"], check=False
        )
        if result.returncode != 0:
            if "No installed app" in result.stderr or "does not have migrations" in result.stderr:
                print(f"  Skipping {app} (no migrations)")
            else:
                print(f"  Warning: {result.stderr.strip()}")
        else:
            print("  Done")


def delete_migration_files():
    """Delete all migration files except __init__.py."""
    print("\n" + "=" * 60)
    print("Step 2: Delete migration files")
    print("=" * 60)

    total_deleted = 0
    for app in APPS_DEPENDENCY_ORDER:
        migrations_dir = WORLD_DIR / app / "migrations"
        if not migrations_dir.exists():
            print(f"  {app}: no migrations directory")
            continue

        deleted = 0
        for f in migrations_dir.glob("*.py"):
            if f.name != "__init__.py":
                f.unlink()
                deleted += 1

        # Also delete __pycache__
        pycache = migrations_dir / "__pycache__"
        if pycache.exists():
            shutil.rmtree(pycache)

        print(f"  {app}: deleted {deleted} migration file(s)")
        total_deleted += deleted

    print(f"\nTotal: deleted {total_deleted} migration files")


def generate_fresh_migrations():
    """Generate fresh migrations for all apps."""
    print("\n" + "=" * 60)
    print("Step 3: Generate fresh migrations")
    print("=" * 60)

    # Run makemigrations for all apps at once
    # Our custom makemigrations command handles Evennia correctly
    print("\nRunning makemigrations for all world apps...")
    result = run_command(
        ["uv", "run", "arx", "manage", "makemigrations", *APPS_DEPENDENCY_ORDER], check=False
    )

    if result.returncode != 0:
        print(f"  Error: {result.stderr}")
        print("\nTrying apps individually...")
        for app in APPS_DEPENDENCY_ORDER:
            print(f"\n  makemigrations {app}...")
            run_command(["uv", "run", "arx", "manage", "makemigrations", app], check=False)
    else:
        print(result.stdout)


def fake_migrate_up():
    """Fake-migrate all apps to apply the new migrations."""
    print("\n" + "=" * 60)
    print("Step 4: Fake-migrate to mark new migrations as applied")
    print("=" * 60)

    print("\nRunning migrate --fake...")
    result = run_command(["uv", "run", "arx", "manage", "migrate", "--fake"], check=False)
    if result.returncode != 0:
        print(f"  Warning: {result.stderr}")
    else:
        print(result.stdout)


def verify_state():
    """Verify the migration state is clean."""
    print("\n" + "=" * 60)
    print("Step 5: Verify migration state")
    print("=" * 60)

    print("\nChecking for pending migrations...")
    result = run_command(["uv", "run", "arx", "manage", "showmigrations", "--list"], check=False)
    print(result.stdout)

    # Check for unapplied migrations
    if "[ ]" in result.stdout:
        print("\nWARNING: Some migrations are not applied!")
        print("Run 'arx manage migrate --fake' to mark them as applied.")
    else:
        print("\nAll migrations are applied.")


def main():
    print("=" * 60)
    print("Migration Reset Script")
    print("=" * 60)
    print("\nThis will reset all world app migrations to a clean state.")
    print("Data will NOT be affected (using --fake migrations).")
    print("\nApps to reset:")
    for app in APPS_DEPENDENCY_ORDER:
        print(f"  - {app}")

    response = input("\nProceed? [y/N] ")
    if response.lower() != "y":
        print("Aborted.")
        sys.exit(0)

    fake_migrate_zero()
    delete_migration_files()
    generate_fresh_migrations()
    fake_migrate_up()
    verify_state()

    print("\n" + "=" * 60)
    print("Migration reset complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Review the generated migrations in world/*/migrations/")
    print("2. Run 'arx test' to verify everything works")
    print("3. Commit the new migrations")


if __name__ == "__main__":
    main()
