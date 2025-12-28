# scripts/arx.py
import json
import os
import shutil
import sys
from pathlib import Path
import subprocess
from datetime import UTC, datetime

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
    # Load .env first to allow DJANGO_SETTINGS_MODULE override
    if ENV_FILE.exists():
        from dotenv import load_dotenv

        load_dotenv(ENV_FILE, override=True)

    # Set default settings module if not specified in .env
    if "DJANGO_SETTINGS_MODULE" not in os.environ:
        os.environ["DJANGO_SETTINGS_MODULE"] = "server.conf.settings"


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


@app.command(name="test")
def run_tests(
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

    The function name differs from the CLI command to keep ``arx test`` stable
    without relying on test discovery conventions.

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


@app.command(name="testfast")
def run_tests_fast(
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
    cmd = ["evennia", "start"]
    # If using custom settings (not default), pass --settings flag
    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "server.conf.settings")
    if settings_module != "server.conf.settings":
        # Extract module name (e.g., "dev_settings" from "server.conf.dev_settings")
        settings_file = settings_module.split(".")[-1]
        cmd.extend(["--settings", settings_file])
    subprocess.run(cmd, check=False)


@app.command()
def stop():
    """Stop the Evennia server."""
    setup_env()
    subprocess.run(["evennia", "stop"], check=False)


@app.command()
def reload():
    """Reload the Evennia server."""
    setup_env()
    cmd = ["evennia", "reload"]
    # If using custom settings (not default), pass --settings flag
    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "server.conf.settings")
    if settings_module != "server.conf.settings":
        # Extract module name (e.g., "dev_settings" from "server.conf.dev_settings")
        settings_file = settings_module.split(".")[-1]
        cmd.extend(["--settings", settings_file])
    subprocess.run(cmd, check=False)


@app.command()
def integration_test():
    """Set up integration test environment with automated ngrok configuration.

    SAFETY CHECK: Requires ALLOW_INTEGRATION_TESTS=true in .env
    This prevents accidentally running integration tests in production.

    This command automates the tedious parts of integration testing:
    - Starts ngrok tunnel on port 3000
    - Backs up and updates .env with ngrok URL
    - Provides clear instructions for manual testing steps
    - Restores .env on Ctrl+C

    After running this command, you'll need to:
    1. Start Django backend (new terminal): uv run arx manage runserver
    2. Start frontend (new terminal): cd frontend && pnpm dev
    3. Follow the testing checklist in src/integration_tests/QUICKSTART.md

    Examples:
        arx integration-test    # Start integration test environment
    """
    setup_env()

    # Safety check: require explicit opt-in
    if os.environ.get("ALLOW_INTEGRATION_TESTS", "").lower() != "true":
        typer.echo("ERROR: Integration tests are not enabled.")
        typer.echo("")
        typer.echo("To enable integration testing, add this to src/.env:")
        typer.echo("  ALLOW_INTEGRATION_TESTS=true")
        typer.echo("")
        typer.echo("This safety check prevents accidentally running integration tests")
        typer.echo("in production environments.")
        raise typer.Exit(1)

    integration_script = SRC_DIR / "integration_tests" / "setup_integration_env.py"
    subprocess.run([sys.executable, str(integration_script)], check=False)


# MCP Server Management
mcp_app = typer.Typer(help="Manage MCP servers in Claude Desktop config")
app.add_typer(mcp_app, name="mcp")

# MCP servers registry - maps server name to config
MCP_DIR = Path("D:/dev/mcp")
MCP_SERVERS = {
    "arxdev": {
        "command": "node",
        "args": [str(MCP_DIR / "arxdev" / "src" / "index.js")],
        "env": {"ARX_PROJECT_ROOT": str(PROJECT_ROOT)},
    },
    "arxdev-integration": {
        "command": "node",
        "args": [str(MCP_DIR / "arxdev-integration" / "src" / "index.js")],
        "env": {"ARX_PROJECT_ROOT": str(PROJECT_ROOT)},
    },
}


def get_mcp_config_path():
    """Get path to project .mcp.json file."""
    return PROJECT_ROOT / ".mcp.json"


def read_mcp_config():
    """Read project .mcp.json file."""
    config_path = get_mcp_config_path()

    if not config_path.exists():
        return {"mcpServers": {}}

    try:
        with config_path.open(encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        typer.echo(f"ERROR: Invalid JSON in {config_path}: {e}")
        raise typer.Exit(1) from e


def write_mcp_config(config):
    """Write project .mcp.json file with backup."""
    config_path = get_mcp_config_path()

    # Create backup
    if config_path.exists():
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
        backup_path = config_path.with_suffix(f".{timestamp}.backup")
        shutil.copy2(config_path, backup_path)
        typer.echo(f"Backup created: {backup_path}")

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Write config
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    typer.echo(f"Config updated: {config_path}")


@mcp_app.command("list")
def mcp_list():
    """List available MCP servers and their status."""
    config = read_mcp_config()
    enabled_servers = config.get("mcpServers", {})

    typer.echo("\nAvailable MCP Servers:")
    typer.echo("=" * 50)

    for name in MCP_SERVERS:
        status = "ENABLED" if name in enabled_servers else "disabled"
        typer.echo(f"  {name:25} [{status}]")

    typer.echo("\nEnabled servers:")
    if enabled_servers:
        for name in enabled_servers:
            if name not in MCP_SERVERS:
                typer.echo(f"  {name:25} [UNKNOWN - not in registry]")
    else:
        typer.echo("  (none)")

    typer.echo("\nUse 'arx mcp enable <name>' to enable a server")
    typer.echo("Use 'arx mcp disable <name>' to disable a server")


@mcp_app.command("enable")
def mcp_enable(server_name: str):
    """Enable an MCP server in project .mcp.json."""
    if server_name not in MCP_SERVERS:
        typer.echo(f"ERROR: Unknown server '{server_name}'")
        typer.echo("\nAvailable servers:")
        for name in MCP_SERVERS:
            typer.echo(f"  - {name}")
        raise typer.Exit(1)

    config = read_mcp_config()

    # Ensure mcpServers key exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    # Check if already enabled
    if server_name in config["mcpServers"]:
        typer.echo(f"Server '{server_name}' is already enabled")
        return

    # Add server
    config["mcpServers"][server_name] = MCP_SERVERS[server_name]
    write_mcp_config(config)

    typer.echo(f"\nSUCCESS: Enabled '{server_name}' in .mcp.json")


@mcp_app.command("disable")
def mcp_disable(server_name: str):
    """Disable an MCP server from project .mcp.json."""
    config = read_mcp_config()

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    # Check if server is enabled
    if server_name not in config["mcpServers"]:
        typer.echo(f"Server '{server_name}' is not enabled")
        return

    # Remove server
    del config["mcpServers"][server_name]
    write_mcp_config(config)

    typer.echo(f"\nSUCCESS: Disabled '{server_name}' from .mcp.json")
