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


test_args = typer.Argument(None, help="Arguments to pass to test command.")


@app.command()
def test(args: List[str] = test_args):
    """Run Evennia tests with correct settings.

    If this is a fresh environment, run ``arx manage migrate`` first so the
    database exists or the tests will fail.
    """
    setup_env()
    command = ["evennia", "test", "--settings=settings"]
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
