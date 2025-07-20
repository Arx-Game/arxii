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
    """Run Evennia tests with correct settings."""
    setup_env()
    command = ["evennia", "test", "--settings=settings"]
    if args:
        command += args
    subprocess.run(command)


@app.command()
def manage(command: str):
    """Run arbitrary Django management commands."""
    setup_env()
    subprocess.run(["evennia", command])


@app.command()
def build():
    """Build docker images, run Makefile, etc."""
    subprocess.run(["make", "build"])  # or docker compose etc.
