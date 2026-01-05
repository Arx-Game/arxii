# scripts/arx.py
import json
import os
from pathlib import Path
import subprocess
import sys

import typer

app = typer.Typer()
mcp_app = typer.Typer(help="Manage MCP servers for Claude Code sessions")
app.add_typer(mcp_app, name="mcp")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"
ENV_FILE = SRC_DIR / ".env"
MCP_CONFIG_FILE = PROJECT_ROOT / ".mcp.json"
MCP_SERVERS_DIR = PROJECT_ROOT / "mcp"

# Registry of available MCP servers
MCP_SERVERS: dict[str, dict] = {
    "arxdev-evennia": {
        "description": "Evennia-specific development tools and rules",
        "command": "node",
        "args": ["mcp/arxdev-evennia/dist/index.js"],
    },
}

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


def _load_mcp_config() -> dict:
    """Load .mcp.json configuration."""
    if MCP_CONFIG_FILE.exists():
        return json.loads(MCP_CONFIG_FILE.read_text())
    return {"mcpServers": {}}


def _save_mcp_config(config: dict) -> None:
    """Save .mcp.json configuration."""
    MCP_CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n")


@mcp_app.command(name="list")
def mcp_list() -> None:
    """List available MCP servers and their status."""
    config = _load_mcp_config()
    enabled_servers = config.get("mcpServers", {})

    typer.echo("Available MCP servers:\n")
    for name, info in MCP_SERVERS.items():
        status = "✓ enabled" if name in enabled_servers else "○ disabled"
        typer.echo(f"  {name}: {status}")
        typer.echo(f"    {info['description']}")
        typer.echo()

    if not MCP_SERVERS:
        typer.echo("  No MCP servers registered.")


@mcp_app.command(name="enable")
def mcp_enable(server: str) -> None:
    """Enable an MCP server in .mcp.json."""
    if server not in MCP_SERVERS:
        typer.echo(f"ERROR: Unknown MCP server '{server}'")
        typer.echo(f"Available servers: {', '.join(MCP_SERVERS.keys())}")
        raise typer.Exit(1)

    server_info = MCP_SERVERS[server]
    server_dir = MCP_SERVERS_DIR / server

    # Check if server is built
    if not (server_dir / "dist" / "index.js").exists():
        typer.echo(f"MCP server '{server}' not built. Building now...")
        subprocess.run(["npm", "install"], cwd=server_dir, check=True)
        subprocess.run(["npm", "run", "build"], cwd=server_dir, check=True)

    config = _load_mcp_config()
    config["mcpServers"][server] = {
        "command": server_info["command"],
        "args": server_info["args"],
        "cwd": "${workspaceFolder}",
    }
    _save_mcp_config(config)

    typer.echo(f"SUCCESS: Enabled MCP server '{server}'")
    typer.echo("Restart Claude Code session for changes to take effect.")


@mcp_app.command(name="disable")
def mcp_disable(server: str) -> None:
    """Disable an MCP server from .mcp.json."""
    config = _load_mcp_config()

    if server not in config.get("mcpServers", {}):
        typer.echo(f"MCP server '{server}' is not enabled.")
        raise typer.Exit(0)

    del config["mcpServers"][server]
    _save_mcp_config(config)

    typer.echo(f"SUCCESS: Disabled MCP server '{server}'")
    typer.echo("Restart Claude Code session for changes to take effect.")


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
    import platform

    frontend_dir = PROJECT_ROOT / "frontend"
    node_modules = frontend_dir / "node_modules"
    package_json = frontend_dir / "package.json"

    # On Windows, we need shell=True for pnpm to be found via PATH
    use_shell = platform.system() == "Windows"

    # If node_modules doesn't exist, definitely need to install
    if not node_modules.exists():
        typer.echo("Frontend dependencies not found, installing...")
        subprocess.run(["pnpm", "install"], cwd=frontend_dir, check=True, shell=use_shell)
        return

    # Quick check: if package.json is newer than node_modules, reinstall
    if package_json.exists() and package_json.stat().st_mtime > node_modules.stat().st_mtime:
        typer.echo("Package.json updated, reinstalling frontend dependencies...")
        subprocess.run(["pnpm", "install"], cwd=frontend_dir, check=True, shell=use_shell)


@app.command()
def shell(command: str | None = SHELL_COMMAND_OPTION) -> None:
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
) -> None:
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
) -> None:
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
def manage(ctx: typer.Context, command: str) -> None:
    """Run arbitrary Django management commands."""
    setup_env()
    cmd_list = ["evennia", command]
    if ctx.args:
        cmd_list += list(ctx.args)
    subprocess.run(cmd_list, check=False)


@app.command()
def build():
    """Build the frontend assets."""
    import platform

    ensure_frontend_deps()
    use_shell = platform.system() == "Windows"
    subprocess.run(["pnpm", "build"], cwd=PROJECT_ROOT / "frontend", check=True, shell=use_shell)


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


def _backup_env_file(env_file: Path, env_backup: Path) -> None:
    """Backup .env file."""
    typer.echo(f"Backing up .env to {env_backup}...")
    if not env_file.exists():
        typer.echo(f"ERROR: .env file not found at {env_file}")
        typer.echo("Please copy .env.example to .env first.")
        raise typer.Exit(1) from None

    content = env_file.read_text()
    env_backup.write_text(content)
    typer.echo("SUCCESS: Backed up .env")


def _restore_env_file(env_file: Path, env_backup: Path) -> None:
    """Restore .env file from backup."""
    if not env_backup.exists():
        typer.echo("WARNING: No .env backup found to restore")
        return

    typer.echo("\nRestoring original .env...")
    content = env_backup.read_text()
    env_file.write_text(content)
    env_backup.unlink()
    typer.echo("SUCCESS: Restored original .env")


def _get_ngrok_status() -> dict | None:
    """Get current ngrok tunnel status from local API.

    Returns dict with tunnel info if ngrok is running, None otherwise.
    """
    try:
        import requests

        response = requests.get("http://localhost:4040/api/tunnels", timeout=2)
        if response.status_code == 200:  # noqa: PLR2004
            data = response.json()
            tunnels = data.get("tunnels", [])
            if tunnels:
                # Return the first HTTPS tunnel
                for tunnel in tunnels:
                    if tunnel.get("proto") == "https":
                        config_addr = tunnel.get("config", {}).get("addr", "")
                        port = config_addr.split(":")[-1]
                        return {
                            "url": tunnel.get("public_url"),
                            "port": port,
                        }
    except Exception:  # noqa: BLE001, S110
        pass
    return None


def _kill_ngrok() -> None:
    """Kill any running ngrok processes."""
    import platform

    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(
                ["taskkill", "/F", "/IM", "ngrok.exe"],
                capture_output=True,
                check=False,
            )
        else:
            subprocess.run(["pkill", "-9", "ngrok"], capture_output=True, check=False)
    except Exception:  # noqa: BLE001, S110
        pass


def _update_env_with_ngrok_url(env_file: Path, ngrok_url: str) -> None:
    """Update .env file with ngrok URL."""
    typer.echo("\nUpdating .env with ngrok URL...")
    lines = env_file.read_text().splitlines(keepends=True)

    updated_lines = []
    found_frontend_url = False
    found_csrf_origins = False

    for line in lines:
        if line.startswith("FRONTEND_URL="):
            updated_lines.append(f"FRONTEND_URL={ngrok_url}\n")
            found_frontend_url = True
        elif line.startswith("CSRF_TRUSTED_ORIGINS="):
            updated_lines.append(
                f"CSRF_TRUSTED_ORIGINS={ngrok_url},http://localhost:4001,http://localhost:3000\n"
            )
            found_csrf_origins = True
        else:
            updated_lines.append(line)

    # Add if not found
    if not found_frontend_url:
        updated_lines.append("\n# Added by arx ngrok\n")
        updated_lines.append(f"FRONTEND_URL={ngrok_url}\n")
    if not found_csrf_origins:
        updated_lines.append(
            f"CSRF_TRUSTED_ORIGINS={ngrok_url},http://localhost:4001,http://localhost:3000\n"
        )

    env_file.write_text("".join(updated_lines))
    typer.echo(f"SUCCESS: Updated FRONTEND_URL={ngrok_url}")
    typer.echo(
        f"SUCCESS: Updated CSRF_TRUSTED_ORIGINS={ngrok_url},http://localhost:4001,http://localhost:3000"
    )

    # Also update frontend/.env with VITE_ALLOWED_HOSTS
    frontend_env = env_file.parent.parent / "frontend" / ".env"
    ngrok_hostname = ngrok_url.replace("https://", "").replace("http://", "")

    if frontend_env.exists():
        frontend_lines = frontend_env.read_text().splitlines(keepends=True)
        updated_frontend = []
        found_vite_hosts = False

        for line in frontend_lines:
            if line.startswith("VITE_ALLOWED_HOSTS="):
                updated_frontend.append(f"VITE_ALLOWED_HOSTS={ngrok_hostname}\n")
                found_vite_hosts = True
            else:
                updated_frontend.append(line)

        if not found_vite_hosts:
            updated_frontend.append("\n# Added by arx ngrok\n")
            updated_frontend.append(f"VITE_ALLOWED_HOSTS={ngrok_hostname}\n")

        frontend_env.write_text("".join(updated_frontend))
        typer.echo(f"SUCCESS: Updated frontend/.env VITE_ALLOWED_HOSTS={ngrok_hostname}")
    else:
        # Create frontend/.env if it doesn't exist
        frontend_env.write_text(f"# Added by arx ngrok\nVITE_ALLOWED_HOSTS={ngrok_hostname}\n")
        typer.echo(f"SUCCESS: Created frontend/.env with VITE_ALLOWED_HOSTS={ngrok_hostname}")


@app.command()
def ngrok(  # noqa: C901, PLR0915
    port: int = typer.Option(3000, help="Port to expose (default: 3000)"),
    force: bool = typer.Option(False, "--force", "-f", help="Kill existing ngrok and restart"),
    status_only: bool = typer.Option(False, "--status", "-s", help="Show ngrok status and exit"),
):
    """Start ngrok tunnel and update .env with public URL.

    This automates ngrok setup for manual testing:
    - Starts ngrok tunnel on specified port (default: 3000 for frontend)
    - Backs up and updates .env with ngrok URL
    - Updates FRONTEND_URL and CSRF_TRUSTED_ORIGINS
    - Keeps running until Ctrl+C
    - Restores .env on exit

    IMPORTANT: Only use in development/local environments.
    Do not run this in production!

    Before running:
    1. Make sure ngrok is installed: https://ngrok.com/download
    2. Configure ngrok auth token: ngrok config add-authtoken <token>

    After running:
    1. Start Evennia server: cd src && uv run arx start
    2. Start frontend: cd frontend && pnpm dev
    3. Access your app via the ngrok URL
    4. Press Ctrl+C when done to restore .env

    Examples:
        arx ngrok                 # Expose port 3000 (frontend)
        arx ngrok --port 4001     # Expose port 4001 (Django)
        arx ngrok --status        # Check if ngrok is running
        arx ngrok --force         # Kill existing and restart
    """
    import atexit
    import signal

    # Check status if requested
    if status_only:
        status = _get_ngrok_status()
        if status:
            typer.echo(f"Ngrok is running: {status['url']} (port {status['port']})")
            raise typer.Exit(0)
        typer.echo("Ngrok is not running")
        raise typer.Exit(0)

    # Check if ngrok is already running
    existing = _get_ngrok_status()
    if existing and not force:
        url = existing["url"]
        port = existing["port"]
        typer.echo(f"Ngrok is already running: {url} (port {port})")
        typer.echo("\nOptions:")
        typer.echo("1. Use the existing URL (shown above)")
        typer.echo("2. Run with --force to kill and restart: arx ngrok --force")
        raise typer.Exit(0)

    # Kill existing ngrok if --force
    if force and existing:
        typer.echo("Killing existing ngrok process...")
        _kill_ngrok()
        import time

        time.sleep(1)  # Give it a moment to clean up

    try:
        from pyngrok import ngrok as pyngrok
        from pyngrok.conf import PyngrokConfig
    except ImportError:
        typer.echo("ERROR: pyngrok not installed.")
        typer.echo("Install with: uv sync")
        raise typer.Exit(1) from None

    # Check we're in dev environment
    setup_env()
    if os.environ.get("RESEND_API_KEY"):
        typer.echo("WARNING: RESEND_API_KEY is set in .env")
        typer.echo("This suggests you're NOT using dev_settings.py (console email backend).")
        typer.echo("Are you sure you want to run ngrok in a production-like setup?")
        if not typer.confirm("Continue anyway?"):
            raise typer.Exit(0)

    env_file = SRC_DIR / ".env"
    env_backup = SRC_DIR / ".env.ngrok_backup"
    tunnel = None

    def cleanup():
        """Restore .env and stop ngrok."""
        nonlocal tunnel
        typer.echo("\n" + "=" * 70)
        typer.echo("CLEANUP - Stopping ngrok and restoring .env")
        typer.echo("=" * 70)

        if tunnel:
            try:
                typer.echo("\nStopping ngrok tunnel...")
                pyngrok.disconnect(tunnel.public_url)
                typer.echo("SUCCESS: Stopped ngrok tunnel")
            except Exception:  # noqa: BLE001
                typer.echo("WARNING: Error stopping ngrok")

        _restore_env_file(env_file, env_backup)

    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully."""
        typer.echo("\n\nReceived interrupt signal...")
        cleanup()
        sys.exit(0)

    # Register cleanup handlers
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, signal_handler)

    # Backup .env
    _backup_env_file(env_file, env_backup)

    # Start ngrok
    typer.echo(f"\nStarting ngrok tunnel on port {port}...")
    try:
        conf = PyngrokConfig(region="us")
        tunnel = pyngrok.connect(port, bind_tls=True, pyngrok_config=conf)
        public_url = tunnel.public_url
        typer.echo(f"SUCCESS: ngrok tunnel started: {public_url}")
    except Exception as e:  # noqa: BLE001
        typer.echo(f"ERROR: Failed to start ngrok: {e}")
        typer.echo("\nTroubleshooting:")
        typer.echo("1. Make sure ngrok is installed: https://ngrok.com/download")
        typer.echo("2. Sign up for a free ngrok account")
        typer.echo("3. Run: ngrok config add-authtoken <your-token>")
        cleanup()
        raise typer.Exit(1) from None

    # Update .env
    _update_env_with_ngrok_url(env_file, public_url)

    # Print instructions
    typer.echo("\n" + "=" * 70)
    typer.echo("NGROK TUNNEL ACTIVE")
    typer.echo("=" * 70)
    typer.echo(f"\nPublic URL: {public_url}")
    typer.echo("\nNext steps:")
    typer.echo("1. Start Evennia server: cd src && uv run arx start")
    typer.echo("2. Start frontend: cd frontend && pnpm dev")
    typer.echo(f"3. Access your app at: {public_url}")
    typer.echo("\nPress Ctrl+C to stop ngrok and restore .env")
    typer.echo("=" * 70)

    # Keep running
    try:
        while True:
            import time

            time.sleep(1)
    except KeyboardInterrupt:
        pass


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
