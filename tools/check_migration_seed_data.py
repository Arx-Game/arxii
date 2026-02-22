"""Check for seed data in Django migrations.

Seed data should be managed via fixtures, not migrations.
See CLAUDE.md lines 191-198 for the fixtures policy.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

# Migrations that are allowed to have data insertion
# These are typically essential system configurations, not seed data
ALLOWED_MIGRATIONS: set[str] = set()

# Patterns that suggest seed data in migrations
SEED_FUNCTION_PATTERNS = [
    r"^seed_",
    r"^create_initial_",
    r"^populate_",
    r"^insert_",
    r"^add_default_",
    r"^load_",
]

# AST patterns that suggest data insertion (not schema changes)
DATA_INSERTION_METHODS = {
    "get_or_create",
    "create",
    "bulk_create",
    "update_or_create",
}


class SeedDataVisitor(ast.NodeVisitor):
    """AST visitor to detect seed data patterns in migration functions."""

    def __init__(self) -> None:
        self.issues: set[str] = set()
        self.current_function: str | None = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check function definitions for seed data patterns."""
        self.current_function = node.name

        # Check if function name matches seed patterns
        for pattern in SEED_FUNCTION_PATTERNS:
            if re.match(pattern, node.name, re.IGNORECASE):
                self.issues.add(
                    f"Function '{node.name}' appears to seed data (name matches '{pattern}')"
                )
                break

        # Visit function body to check for data insertion calls
        self.generic_visit(node)
        self.current_function = None

    def visit_Call(self, node: ast.Call) -> None:
        """Check for data insertion method calls."""
        method_name = None

        # Handle: Model.objects.create(...) or obj.create(...)
        if isinstance(node.func, ast.Attribute):
            method_name = node.func.attr

        if method_name in DATA_INSERTION_METHODS and self.current_function:
            # Only flag once per function
            self.issues.add(
                f"Function '{self.current_function}' calls '{method_name}()' which inserts data"
            )

        self.generic_visit(node)


def check_migration_file(filepath: Path) -> list[str]:
    """Check a single migration file for seed data patterns.

    Returns:
        List of issue descriptions found in the file.
    """
    content = filepath.read_text(encoding="utf-8")

    # Quick check: if no RunPython, skip detailed analysis
    if "RunPython" not in content:
        return []

    # Parse AST and look for seed data patterns
    try:
        tree = ast.parse(content, filename=str(filepath))
    except SyntaxError:
        return []

    visitor = SeedDataVisitor()
    visitor.visit(tree)

    return sorted(visitor.issues)


def find_migration_files() -> list[Path]:
    """Find all migration files in the project."""
    migrations: list[Path] = []

    for migrations_dir in SRC_DIR.rglob("migrations"):
        if not migrations_dir.is_dir():
            continue
        # Skip __pycache__
        if "__pycache__" in str(migrations_dir):
            continue

        for migration_file in migrations_dir.glob("*.py"):
            # Skip __init__.py
            if migration_file.name == "__init__.py":
                continue
            migrations.append(migration_file)

    return migrations


def is_allowed(filepath: Path) -> bool:
    """Check if a migration is in the allowlist."""
    rel_path = filepath.relative_to(SRC_DIR)
    # Normalize to forward slashes for comparison
    rel_path_str = str(rel_path).replace("\\", "/")
    return rel_path_str in ALLOWED_MIGRATIONS


def main() -> int:
    """Run the seed data check on all migration files.

    Returns:
        Process exit code (0 when clean, 1 when seed data found).
    """
    all_issues: dict[Path, list[str]] = {}

    for migration_file in find_migration_files():
        # Skip allowed migrations
        if is_allowed(migration_file):
            continue

        issues = check_migration_file(migration_file)
        if issues:
            all_issues[migration_file] = issues

    if not all_issues:
        print("No seed data detected in migrations.")
        return 0

    print("=" * 70)
    print("SEED DATA DETECTED IN MIGRATIONS")
    print("=" * 70)
    print()
    print("Seed data must be managed via fixtures, not migrations.")
    print("See CLAUDE.md for the fixtures policy:")
    print()
    print("  - Fixtures are gitignored via `**/fixtures/*.json`")
    print("  - Seed data is managed separately from code")
    print("  - Never use migrations for initial/seed data")
    print()
    print("Files with issues:")
    print("-" * 70)

    for filepath, issues in sorted(all_issues.items()):
        rel_path = filepath.relative_to(PROJECT_ROOT)
        print(f"\n{rel_path}:")
        for issue in issues:
            print(f"  - {issue}")

    print()
    print("=" * 70)
    print("To fix: Move seed data to fixtures/*.json files and delete the migration.")
    print("        Or add to ALLOWED_MIGRATIONS in tools/check_migration_seed_data.py")
    print("        if this is essential system configuration.")
    print("=" * 70)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
