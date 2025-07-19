# Arx II

Arx II is the sequel to Arx: After the Reckoning, built on the Evennia framework.

## Development Setup (Windows)

This project uses [`uv`](https://github.com/astral-sh/uv) to manage dependencies and the virtual environment.

### Prerequisites

- [Python 3.12](https://www.python.org/downloads/)
- [Git ≥ 2.29](https://git-scm.com/)
- [uv](https://github.com/astral-sh/uv)

Install `uv` globally with:

```powershell
pip install uv
```
⚠️ Ensure Python, Git, and uv are in your system PATH.

## Installation
Open PowerShell and run the following commands:
### Clone the repository
```powershell
git clone https://github.com/YOUR_USERNAME/arxii.git
cd arxii
```

### Create the virtual environment and install dependencies
```powershell
uv venv
uv sync
```

### Create an empty .env file inside the src directory
```powershell
New-Item -Path .\src\.env -ItemType File
```

### Install pre-commit hooks
```powershell
pre-commit install
```

## Using the arx CLI
After setup, use the arx command-line tool:

### Run tests:

```powershell
arx test
```
### Launch a Django shell:

```powershell
arx shell
```
