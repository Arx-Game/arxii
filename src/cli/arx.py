# scripts/arx.py
import os
from pathlib import Path
import subprocess

import typer

app = typer.Typer()
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"
ENV_FILE = SRC_DIR / ".env"

# Define typer options/arguments as module-level variables to avoid B008
TEST_ARGS_ARG = typer.Argument(None, help="Test apps/modules to run")
PARALLEL_OPTION = typer.Option(False, "--parallel", "-p", help="Run tests in parallel")
KEEPDB_OPTION = typer.Option(
    False,
    "--keepdb",
    "-k",
    help="Keep test database between runs",
)
FAILFAST_OPTION = typer.Option(False, "--failfast", "-f", help="Stop on first failure")
VERBOSITY_OPTION = typer.Option(1, "--verbosity", "-v", help="Verbosity level (0-3)")
TIMING_OPTION = typer.Option(
    False,
    "--timing",
    "-t",
    help="Show test timing with unittest -v flag",
)
COVERAGE_OPTION = typer.Option(
    False,
    "--coverage",
    "-c",
    help="Report test coverage after running",
)
PRODUCTION_SETTINGS_OPTION = typer.Option(
    False,
    "--production-settings",
    help="Use production settings instead of optimized test settings",
)
SHELL_COMMAND_OPTION = typer.Option(
    None,
    "-c",
    "--command",
    help="Execute code in the shell and exit",
)


def setup_env():
    os.chdir(SRC_DIR)
    os.environ["DJANGO_SETTINGS_MODULE"] = "server.conf.settings"
    if ENV_FILE.exists():
        from dotenv import load_dotenv

        load_dotenv(ENV_FILE, override=True)


def ensure_frontend_deps():
    """Check if frontend dependencies need to be installed."""
    frontend_dir = PROJECT_ROOT / "frontend"
    node_modules = frontend_dir / "node_modules"
    package_json = frontend_dir / "package.json"

    # If node_modules doesn't exist, definitely need to install
    if not node_modules.exists():
        typer.echo("Frontend dependencies not found, installing...")
        subprocess.run(["pnpm", "install"], cwd=frontend_dir, check=True)
        return

    # Quick check: if package.json is newer than node_modules, reinstall
    if (
        package_json.exists()
        and package_json.stat().st_mtime > node_modules.stat().st_mtime
    ):
        typer.echo("Package.json updated, reinstalling frontend dependencies...")
        subprocess.run(["pnpm", "install"], cwd=frontend_dir, check=True)


@app.command()
def shell(command: str | None = SHELL_COMMAND_OPTION):
    """Start Evennia shell with correct settings."""
    setup_env()
    cmd = ["evennia", "shell"]
    if command:
        cmd += ["-c", command]
    subprocess.run(cmd, check=False)


@app.command()
def test(
    args: list[str] = TEST_ARGS_ARG,
    parallel: bool = PARALLEL_OPTION,
    keepdb: bool = KEEPDB_OPTION,
    failfast: bool = FAILFAST_OPTION,
    verbosity: int = VERBOSITY_OPTION,
    timing: bool = TIMING_OPTION,
    coverage: bool = COVERAGE_OPTION,
    production_settings: bool = PRODUCTION_SETTINGS_OPTION,
):
    """Run Evennia tests with optimized test settings for performance.

    By default, uses test_settings.py which provides:
    - In-memory SQLite database for speed
    - Disabled migrations for faster database creation
    - Fast password hashing
    - Reduced logging

    If this is a fresh environment, run ``arx manage migrate`` first so the
    database exists or the tests will fail.

    Examples:
        arx test                           # Run all tests (optimized)
        arx test world.roster              # Run specific app tests
        arx test --parallel --keepdb       # Fast test run
        arx test --failfast -v2            # Stop on first failure, verbose
        arx test --timing                  # Show individual test timings
        arx test --coverage                # Display coverage report
        arx test --production-settings     # Use production settings instead
    """
    setup_env()
    # Use optimized test settings by default, production settings if requested
    settings_module = "settings" if production_settings else "test_settings"
    command = ["evennia", "test", f"--settings={settings_module}"]

    # Add performance options
    if parallel:
        command.append("--parallel")
    if keepdb:
        command.append("--keepdb")
    if failfast:
        command.append("--failfast")

    # Add verbosity
    MIN_VERBOSITY_FOR_TIMING = 2
    if timing and verbosity < MIN_VERBOSITY_FOR_TIMING:
        verbosity = MIN_VERBOSITY_FOR_TIMING  # Need verbosity 2 for our timing wrapper
    command.append(f"--verbosity={verbosity}")

    # Add timing wrapper if requested
    if timing:
        # Set environment variable to enable our timing wrapper
        os.environ["ARX_TEST_TIMING"] = "1"

    # Add test arguments
    if args:
        command += args

    if coverage:
        subprocess.run(
            [
                "coverage",
                "run",
                "--source=.",
                "--omit=*/tests/*",
                "-m",
                *command,
            ],
            check=False,
        )
        subprocess.run(["coverage", "report"], check=False)
    else:
        subprocess.run(command, check=False)


@app.command()
def testfast(
    args: list[str] = TEST_ARGS_ARG,
    production_settings: bool = PRODUCTION_SETTINGS_OPTION,
):
    """Run tests with performance optimizations (no parallel on Windows).

    Uses optimized test settings by default.
    Equivalent to: arx test --keepdb --failfast -v1
    """
    setup_env()
    settings_module = "settings" if production_settings else "test_settings"
    command = [
        "evennia",
        "test",
        f"--settings={settings_module}",
        "--keepdb",
        "--failfast",
        "--verbosity=1",
    ]

    if args:
        command += args

    subprocess.run(command, check=False)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def manage(ctx: typer.Context, command: str):
    """Run arbitrary Django management commands."""
    setup_env()
    cmd_list = ["evennia", command]
    if ctx.args:
        cmd_list += list(ctx.args)
    subprocess.run(cmd_list, check=False)


@app.command()
def build():
    """Build the frontend assets."""
    ensure_frontend_deps()
    subprocess.run(["pnpm", "build"], cwd=PROJECT_ROOT / "frontend", check=True)


@app.command()
def serve():
    """Build frontend, gather static files, and start Evennia.

    This runs the React production build, collects static assets, and then
    launches the Evennia server. Automatically installs frontend dependencies
    if needed.
    """
    build()
    setup_env()
    subprocess.run(["evennia", "collectstatic", "--noinput"], check=False)
    subprocess.run(["evennia", "start"], check=False)


@app.command()
def start():
    """Start the Evennia server."""
    setup_env()
    subprocess.run(["evennia", "start"], check=False)


@app.command()
def stop():
    """Stop the Evennia server."""
    setup_env()
    subprocess.run(["evennia", "stop"], check=False)


@app.command()
def reload():
    """Reload the Evennia server."""
    setup_env()
    subprocess.run(["evennia", "reload"], check=False)
