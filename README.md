# Arx II

Arx II is the sequel to Arx: After the Reckoning, built on the Evennia framework.

## Development Setup (Windows)

This project uses [mise](https://mise.jdx.dev/) to manage runtime versions and [`uv`](https://github.com/astral-sh/uv) to manage Python dependencies.

### Prerequisites

- [Git ≥ 2.29](https://git-scm.com/)
- [mise](https://mise.jdx.dev/installation.html)
- [PowerShell 7+](https://github.com/PowerShell/PowerShell/releases) (Windows PowerShell 5.1 is not supported for shell hooks)

Note: Python 3.13 will be automatically installed by mise.

Install `mise` using winget in PowerShell 7+:

```powershell
winget install jdx.mise
```

⚠️ Ensure Python, Git, and mise are in your system PATH. After installing mise, you may need to restart your terminal.

### PowerShell 7+ Setup

1. **Install PowerShell 7+**
   - Download the latest version from: [PowerShell GitHub Releases](https://github.com/PowerShell/PowerShell/releases)
   - Or install using winget:
     ```powershell
     winget install --id Microsoft.PowerShell --source winget
     ```

2. **Set as Default Shell (Recommended)**
   - Open Windows Terminal
   - Click the down arrow next to the tab and select "Settings"
   - Under "Startup > Default Profile", select "PowerShell"
   - Click "Save"

## Installation
Open PowerShell and run the following commands:
### Clone the repository
```powershell
git clone https://github.com/Arx-Game/arxii.git
cd arxii
```

### Set up development environment

1. First, trust the project's configuration (you'll be prompted to confirm):

```powershell
mise trust
```

2. Install the required tools:

```powershell
mise install
```

### Making mise available in your terminal

3. Set up mise to be available in all terminal sessions by adding it to your PowerShell profile. First, ensure the profile directory exists and create it if needed:

```powershell
# Create the PowerShell profile directory if it doesn't exist
if (-not (Test-Path -Path "$HOME\Documents\PowerShell")) {
    New-Item -ItemType Directory -Path "$HOME\Documents\PowerShell" -Force
}

# Add mise activation to your PowerShell profile (with proper newline)
Add-Content -Path $PROFILE -Value "`nmise activate pwsh | Out-String | Invoke-Expression"
# Note: The backtick before 'n ensures this starts on a new line in your profile
```

4. Close and reopen your terminal for the changes to take effect. The next time you open PowerShell, mise will be automatically activated.

5. In your new terminal session, verify the installations:

```powershell
node --version  # Should show v20.0.0
python --version  # Should show Python 3.13.x
uv --version  # Should show the installed version
```

Note: If you don't want to restart your current terminal, you can manually activate mise in your current session with:

```powershell
mise activate pwsh | Out-String | Invoke-Expression
```

### Set up the virtual environment and install dependencies
```powershell
uv venv
uv sync
```

### Verify installations
Check that the correct versions are being used:

```powershell
python --version  # Should show Python 3.13.x
node --version   # Should show v20.x.x
npm --version    # Should show 11.5.1
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
