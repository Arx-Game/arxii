"""
Backup Arx II data to Google Drive.

This script exports data from the database and uploads it to Google Drive
using rclone. It can be run manually or scheduled via cron/Task Scheduler.

Two backup modes:
- Configuration backup (default): Exports config/seed data as JSON fixtures
- Full database backup (--full): Uses pg_dump for complete PostgreSQL backup

Setup Instructions:
-------------------
1. Install rclone:
   - Windows: winget install rclone.rclone
   - Or download from: https://rclone.org/downloads/

2. Configure rclone for Google Drive:
   - Run: rclone config
   - Choose 'n' for new remote
   - Name it 'gdrive' (or update RCLONE_REMOTE below)
   - Choose 'drive' for Google Drive
   - Follow the prompts to authenticate via browser
   - For headless servers, use: rclone config --config rclone.conf

3. Create your backup folder in Google Drive:
   - Create a folder called 'ArxII-Backups' (or update GDRIVE_FOLDER below)

4. Run this script:
   - python scripts/backup_to_gdrive.py

Usage:
------
    python scripts/backup_to_gdrive.py [--dry-run] [--keep-local] [--full] [--cleanup]

Options:
    --dry-run       Show what would be uploaded without actually uploading
    --keep-local    Keep the local backup file after uploading (default: delete)
    --full          Full database backup using pg_dump (instead of config-only)
    --cleanup       Remove old backups beyond retention limit (default: keep all)
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

# Paths (needed before Django setup)
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
BACKUP_DIR = PROJECT_ROOT / "backups"

# Set up Django environment for model imports
os.chdir(PROJECT_ROOT / "src")
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402
from django.core import serializers  # noqa: E402

from web.admin.models import AdminExcludedModel  # noqa: E402

# Configuration
RCLONE_REMOTE = "gdrive"  # Name of your rclone remote
GDRIVE_FOLDER = "ArxII-Backups"  # Folder in Google Drive
MAX_CONFIG_BACKUPS = 30  # Keep last N config backups when --cleanup is used
MAX_FULL_BACKUPS = 10  # Keep last N full database backups when --cleanup is used

# Error messages
ERR_NO_ENV_FILE = "No .env file found at {path}"
ERR_PARSE_DB_URL = "Could not parse DATABASE_URL: {url}"
ERR_NO_DB_URL = "DATABASE_URL not found in .env"
ERR_PG_DUMP_NOT_FOUND = "pg_dump not found"
ERR_PG_DUMP_FAILED = "pg_dump failed"


def find_rclone() -> str | None:  # noqa: C901
    """Find rclone executable, checking common installation paths on Windows."""
    # First check if it's in PATH
    try:
        result = subprocess.run(
            ["rclone", "version"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return "rclone"
    except FileNotFoundError:
        pass

    # Check common Windows installation paths
    if platform.system() == "Windows":
        # Check winget installation path
        winget_base = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
        if winget_base.exists():
            for pkg_dir in winget_base.iterdir():
                if "Rclone.Rclone" in pkg_dir.name:
                    for subdir in pkg_dir.iterdir():
                        rclone_path = subdir / "rclone.exe"
                        if rclone_path.exists():
                            return str(rclone_path)

        # Check Program Files
        for prog_dir in [
            Path("C:/Program Files/rclone"),
            Path("C:/Program Files (x86)/rclone"),
        ]:
            rclone_path = prog_dir / "rclone.exe"
            if rclone_path.exists():
                return str(rclone_path)

    return None


def find_pg_dump() -> str | None:
    """Find pg_dump executable, checking common installation paths on Windows."""
    # First check if it's in PATH
    try:
        result = subprocess.run(
            ["pg_dump", "--version"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return "pg_dump"
    except FileNotFoundError:
        pass

    # Check common Windows PostgreSQL installation paths
    if platform.system() == "Windows":
        postgres_base = Path("C:/Program Files/PostgreSQL")
        if postgres_base.exists():
            # Find highest version installed
            versions = sorted(
                [d for d in postgres_base.iterdir() if d.is_dir()],
                key=lambda x: x.name,
                reverse=True,
            )
            for version_dir in versions:
                pg_dump_path = version_dir / "bin" / "pg_dump.exe"
                if pg_dump_path.exists():
                    return str(pg_dump_path)

    return None


def get_database_url() -> dict[str, str]:
    """Parse DATABASE_URL from .env file."""
    env_file = PROJECT_ROOT / "src" / ".env"
    if not env_file.exists():
        msg = ERR_NO_ENV_FILE.format(path=env_file)
        raise FileNotFoundError(msg)

    for line in env_file.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip()
            # Parse postgresql://user:pass@host:port/dbname
            match = re.match(
                r"postgresql://(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)/(?P<database>.+)",
                url,
            )
            if match:
                return match.groupdict()
            msg = ERR_PARSE_DB_URL.format(url=url)
            raise ValueError(msg)

    raise ValueError(ERR_NO_DB_URL)


def check_rclone_installed() -> str | None:
    """Check if rclone is installed and return path if found."""
    return find_rclone()


def check_rclone_configured(rclone_path: str) -> bool:
    """Check if the Google Drive remote is configured."""
    try:
        result = subprocess.run(  # noqa: S603
            [rclone_path, "listremotes"],
            capture_output=True,
            text=True,
            check=False,
        )
        return f"{RCLONE_REMOTE}:" in result.stdout
    except FileNotFoundError:
        return False


def export_full_database() -> Path:
    """Export full PostgreSQL database using pg_dump."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")  # noqa: DTZ005
    filename = f"arx-full-{timestamp}.sql.gz"

    # Ensure backup directory exists
    BACKUP_DIR.mkdir(exist_ok=True)
    backup_path = BACKUP_DIR / filename

    print(f"Exporting full database to {backup_path}...")

    # Get database credentials
    try:
        db = get_database_url()
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        raise

    # Set password via environment variable (more secure than command line)
    env = os.environ.copy()
    env["PGPASSWORD"] = db["password"]

    # Find pg_dump executable
    pg_dump_path = find_pg_dump()
    if not pg_dump_path:
        print("Error: pg_dump is not installed or not in PATH")
        print("Install PostgreSQL client tools to enable full backups")
        raise FileNotFoundError(ERR_PG_DUMP_NOT_FOUND)

    # Run pg_dump
    pg_dump_cmd = [
        pg_dump_path,
        "-h",
        db["host"],
        "-p",
        db["port"],
        "-U",
        db["user"],
        "-d",
        db["database"],
        "--no-owner",  # Don't output ownership commands
        "--no-acl",  # Don't output access privilege commands
        "-Z",
        "9",  # Maximum gzip compression
    ]

    print(f"  Host: {db['host']}:{db['port']}")
    print(f"  Database: {db['database']}")

    with backup_path.open("wb") as f:
        result = subprocess.run(  # noqa: S603
            pg_dump_cmd,
            stdout=f,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )

    if result.returncode != 0:
        print(f"Error running pg_dump: {result.stderr.decode()}")
        if backup_path.exists():
            backup_path.unlink()
        raise RuntimeError(ERR_PG_DUMP_FAILED)

    size_mb = backup_path.stat().st_size / (1024 * 1024)
    print(f"Exported full database ({size_mb:.1f} MB compressed)")

    return backup_path


def export_data() -> Path:
    """Export configuration data from Django and save to a local file."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")  # noqa: DTZ005
    filename = f"arx-config-{timestamp}.json"

    # Ensure backup directory exists
    BACKUP_DIR.mkdir(exist_ok=True)
    backup_path = BACKUP_DIR / filename

    print(f"Exporting data to {backup_path}...")

    # Get excluded models
    excluded = set(AdminExcludedModel.objects.values_list("app_label", "model_name"))

    # Skip system apps
    skip_apps = {
        "sessions",
        "contenttypes",
        "django_migrations",
        "admin",
        "server",
        "scripts",
        "comms",
        "help",
        "typeclasses",
    }

    # Collect all objects
    all_objects = []
    for model in apps.get_models():
        app_label = model._meta.app_label  # noqa: SLF001
        model_name = model._meta.model_name  # noqa: SLF001

        if (app_label, model_name) in excluded:
            continue
        if app_label in skip_apps:
            continue

        try:
            objects = list(model.objects.all())
            all_objects.extend(objects)
        except Exception:  # noqa: BLE001, S112
            # Skip models that can't be queried (abstract, proxy issues, etc.)
            continue

    # Serialize with natural keys
    data = serializers.serialize(
        "json",
        all_objects,
        indent=2,
        use_natural_foreign_keys=True,
        use_natural_primary_keys=True,
    )

    # Write to file
    backup_path.write_text(data, encoding="utf-8")
    size_kb = backup_path.stat().st_size / 1024
    print(f"Exported {len(all_objects)} objects ({size_kb:.1f} KB)")

    return backup_path


def upload_to_gdrive(local_path: Path, rclone_path: str, dry_run: bool = False) -> bool:
    """Upload a file to Google Drive using rclone."""
    remote_path = f"{RCLONE_REMOTE}:{GDRIVE_FOLDER}/{local_path.name}"

    print(f"Uploading to {remote_path}...")

    cmd = [rclone_path, "copy", str(local_path), f"{RCLONE_REMOTE}:{GDRIVE_FOLDER}/"]

    if dry_run:
        cmd.append("--dry-run")
        print(f"  [DRY RUN] Would run: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603

    if result.returncode != 0:
        print(f"Error uploading: {result.stderr}")
        return False

    if not dry_run:
        print("Upload complete!")
    return True


def cleanup_old_backups_by_prefix(
    prefix: str, max_backups: int, rclone_path: str, dry_run: bool = False
) -> None:
    """Remove old backups from Google Drive by prefix, keeping only max_backups."""
    if max_backups <= 0:
        return

    print(f"Cleaning up old {prefix} backups (keeping last {max_backups})...")

    # List files in backup folder
    cmd = [
        rclone_path,
        "lsjson",
        f"{RCLONE_REMOTE}:{GDRIVE_FOLDER}/",
        "--files-only",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603

    if result.returncode != 0:
        print(f"Warning: Could not list backups: {result.stderr}")
        return

    try:
        files = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Warning: Could not parse backup list")
        return

    # Filter to matching files and sort by date (newest first)
    matching_files = [f for f in files if f["Name"].startswith(prefix)]
    matching_files.sort(key=lambda x: x["ModTime"], reverse=True)

    # Delete old files
    files_to_delete = matching_files[max_backups:]
    for f in files_to_delete:
        remote_path = f"{RCLONE_REMOTE}:{GDRIVE_FOLDER}/{f['Name']}"
        print(f"  Deleting old backup: {f['Name']}")

        if not dry_run:
            delete_cmd = ["rclone", "delete", remote_path]
            subprocess.run(delete_cmd, capture_output=True, check=False)  # noqa: S603

    if files_to_delete:
        print(f"Removed {len(files_to_delete)} old backup(s)")
    else:
        print("No old backups to remove")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Backup Arx II data to Google Drive")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes",
    )
    parser.add_argument(
        "--keep-local",
        action="store_true",
        help="Keep local backup file after upload",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full database backup using pg_dump (instead of config-only)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove old backups beyond retention limit",
    )
    args = parser.parse_args()

    # Check for environment variable overrides (set by arx backup command)
    local_only = os.environ.get("ARX_BACKUP_LOCAL_ONLY") == "1"
    full_backup = args.full or os.environ.get("ARX_BACKUP_FULL") == "1"

    backup_type = "Full Database" if full_backup else "Configuration"
    print("=" * 50)
    print(f"Arx II {backup_type} Backup")
    print("=" * 50)

    # Export data
    try:
        if full_backup:
            backup_path = export_full_database()
        else:
            backup_path = export_data()
    except Exception as e:  # noqa: BLE001
        print(f"\nError exporting data: {e}")
        return 1

    # If local-only mode, we're done
    if local_only:
        print(f"\nLocal backup saved to: {backup_path}")
        print("\nBackup complete! (local only)")
        return 0

    # Check rclone for cloud upload
    rclone_path = check_rclone_installed()
    if not rclone_path:
        print("\nError: rclone is not installed!")
        print("Install it with: winget install rclone.rclone")
        print("Or download from: https://rclone.org/downloads/")
        print(f"\nLocal backup saved to: {backup_path}")
        return 1

    if not check_rclone_configured(rclone_path):
        print(f"\nError: rclone remote '{RCLONE_REMOTE}' is not configured!")
        print("Run 'rclone config' to set up Google Drive access.")
        print(f"\nLocal backup saved to: {backup_path}")
        return 1

    # Upload to Google Drive
    if not upload_to_gdrive(backup_path, rclone_path, dry_run=args.dry_run):
        return 1

    # Cleanup old backups only if --cleanup flag is provided
    if args.cleanup:
        if full_backup:
            cleanup_old_backups_by_prefix(
                "arx-full-", MAX_FULL_BACKUPS, rclone_path, dry_run=args.dry_run
            )
        else:
            cleanup_old_backups_by_prefix(
                "arx-config-", MAX_CONFIG_BACKUPS, rclone_path, dry_run=args.dry_run
            )

    # Remove local file unless --keep-local
    if not args.keep_local and not args.dry_run:
        backup_path.unlink()
        print(f"Removed local file: {backup_path}")

    print("\nBackup complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
