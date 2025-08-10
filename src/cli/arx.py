# scripts/arx.py

import os
from pathlib import Path
import subprocess
from typing import List

import typer

app = typer.Typer()
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"
ENV_FILE = SRC_DIR / ".env"

# Define typer options/arguments as module-level variables to avoid B008
TEST_ARGS_ARG = typer.Argument(None, help="Test apps/modules to run")
PARALLEL_OPTION = typer.Option(False, "--parallel", "-p", help="Run tests in parallel")
KEEPDB_OPTION = typer.Option(
    False, "--keepdb", "-k", help="Keep test database between runs"
)
FAILFAST_OPTION = typer.Option(False, "--failfast", "-f", help="Stop on first failure")
VERBOSE_OPTION = typer.Option(1, "--verbose", "-v", help="Verbosity level (0-3)")
TIMING_OPTION = typer.Option(
    False, "--timing", "-t", help="Show test timing with unittest -v flag"
)
COVERAGE_OPTION = typer.Option(
    False, "--coverage", "-c", help="Report test coverage after running"
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
def shell():
    """Start Evennia shell with correct settings."""
    setup_env()
    subprocess.run(["evennia", "shell"])


@app.command()
def test(
    args: List[str] = TEST_ARGS_ARG,
    parallel: bool = PARALLEL_OPTION,
    keepdb: bool = KEEPDB_OPTION,
    failfast: bool = FAILFAST_OPTION,
    verbose: int = VERBOSE_OPTION,
    timing: bool = TIMING_OPTION,
    coverage: bool = COVERAGE_OPTION,
):
    """Run Evennia tests with correct settings and performance optimizations.

    If this is a fresh environment, run ``arx manage migrate`` first so the
    database exists or the tests will fail.

    Examples:
        arx test                           # Run all tests
        arx test world.roster              # Run specific app tests
        arx test --parallel --keepdb       # Fast test run
        arx test --failfast -v2            # Stop on first failure, verbose
        arx test --timing                  # Show individual test timings
        arx test --coverage                # Display coverage report
    """
    setup_env()
    command = ["evennia", "test", "--settings=settings"]

    # Add performance options
    if parallel:
        command.append("--parallel")
    if keepdb:
        command.append("--keepdb")
    if failfast:
        command.append("--failfast")

    # Add verbosity
    if timing and verbose < 2:
        verbose = 2  # Need verbosity 2 for our timing wrapper
    command.append(f"--verbosity={verbose}")

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
            ]
        )
        subprocess.run(["coverage", "report"])
    else:
        subprocess.run(command)


@app.command()
def testfast(
    args: List[str] = TEST_ARGS_ARG,
):
    """Run tests with performance optimizations (no parallel on Windows).

    Equivalent to: arx test --keepdb --failfast -v1
    """
    setup_env()
    command = [
        "evennia",
        "test",
        "--settings=settings",
        "--keepdb",
        "--failfast",
        "--verbosity=1",
    ]

    if args:
        command += args

    subprocess.run(command)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def manage(ctx: typer.Context, command: str):
    """Run arbitrary Django management commands."""
    setup_env()
    cmd_list = ["evennia", command]
    if ctx.args:
        cmd_list += list(ctx.args)
    subprocess.run(cmd_list)


@app.command()
def build():
    """Build docker images, run Makefile, etc."""
    subprocess.run(["make", "build"])  # or docker compose etc.


@app.command()
def serve():
    """Build frontend, gather static files, and start Evennia.

    This runs the React production build, collects static assets, and then
    launches the Evennia server. Automatically installs frontend dependencies
    if needed.
    """
    ensure_frontend_deps()
    subprocess.run(["pnpm", "build"], cwd=PROJECT_ROOT / "frontend", check=True)
    setup_env()
    subprocess.run(["evennia", "collectstatic", "--noinput"])
    subprocess.run(["evennia", "start"])


@app.command()
def stop():
    """Stop the Evennia server."""
    setup_env()
    subprocess.run(["evennia", "stop"])


@app.command()
def reload():
    """Reload the Evennia server."""
    setup_env()
    subprocess.run(["evennia", "reload"])
