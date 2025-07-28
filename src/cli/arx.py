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


def setup_env():
    os.chdir(SRC_DIR)
    os.environ["DJANGO_SETTINGS_MODULE"] = "server.conf.settings"
    if ENV_FILE.exists():
        from dotenv import load_dotenv

        load_dotenv(ENV_FILE, override=True)


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
):
    """Run Evennia tests with correct settings and performance optimizations.

    If this is a fresh environment, run ``arx manage migrate`` first so the
    database exists or the tests will fail.

    Examples:
        arx test                           # Run all tests
        arx test world.roster              # Run specific app tests
        arx test --parallel --keepdb       # Fast test run
        arx test --failfast -v2            # Stop on first failure, verbose
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
    command.append(f"--verbosity={verbose}")

    # Add test arguments
    if args:
        command += args

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
