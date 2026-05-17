#requires -Version 5.1
<#
  Bootstraps the Windows host for the arxii devcontainer sandbox.
  Idempotent + detection-first: safe to re-run. Does NOT reboot or self-elevate;
  it reports what needs an admin shell / reboot / interactive Docker Desktop step.
  Exit code: 0 = host ready; 1 = action required (admin shell and/or reboot).
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
function Info($m){ Write-Host "[bootstrap] $m" }
function Warn($m){ Write-Warning $m }

$needsAdmin = $false
$needsReboot = $false

# 1. WSL2 ---------------------------------------------------------------
$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wsl) {
  Warn "WSL not present. Run THIS in an ADMIN PowerShell:  wsl --install"
  Warn "That installs WSL2 + Ubuntu and requires a REBOOT, then re-run this script."
  $needsAdmin = $true; $needsReboot = $true
} else {
  # Prefer the per-distro VERSION column from `wsl -l -v`; fall back to the
  # global default version. Never match a bare digit (false positives).
  $verbose = (wsl -l -v) 2>&1 | Out-String
  $hasV2Distro = $verbose -split "`n" | Where-Object { $_ -match '\s2\s*$' }
  $defaultV2 = ((wsl --status) 2>&1 | Out-String) -match 'Default Version:\s*2'
  if ($hasV2Distro -or $defaultV2) {
    Info "WSL2 present."
  } else {
    Warn "WSL present but no v2 distro / default not v2. Run (admin):  wsl --set-default-version 2"
    $needsAdmin = $true
  }
  $distros = (wsl -l -q) 2>&1 | Out-String
  if (-not ($distros -match '\S')) {
    Warn "No WSL distro installed. Run (admin):  wsl --install -d Ubuntu  (then reboot)"
    $needsAdmin = $true; $needsReboot = $true
  } else { Info "WSL distro present." }
}

# 2. Docker Desktop -----------------------------------------------------
$docker = Get-Command docker.exe -ErrorAction SilentlyContinue
if (-not $docker) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Info "Installing Docker Desktop via winget..."
    winget install --id Docker.DockerDesktop -e --accept-source-agreements --accept-package-agreements
    Warn "Docker Desktop installed. LAUNCH it once, accept the EULA, and ensure"
    Warn "Settings -> Resources -> WSL Integration is ENABLED. This step is interactive."
    $needsReboot = $true
  } else {
    Warn "winget unavailable. Install Docker Desktop manually: https://www.docker.com/products/docker-desktop/"
  }
} else {
  try { docker version --format '{{.Server.Version}}' | Out-Null; Info "Docker engine reachable." }
  catch { Warn "docker present but engine not reachable - start Docker Desktop and enable WSL integration." }
}

# 3. devcontainer CLI ---------------------------------------------------
$dc = Get-Command devcontainer -ErrorAction SilentlyContinue
if (-not $dc) {
  if (Get-Command npm -ErrorAction SilentlyContinue) {
    Info "Installing @devcontainers/cli globally..."
    npm install -g @devcontainers/cli
  } else {
    Warn "npm not found. Install Node.js for Windows from https://nodejs.org then re-run,"
    Warn "or run:  npm install -g @devcontainers/cli"
  }
} else { Info "devcontainer CLI present." }

# Summary ---------------------------------------------------------------
Info "--- Summary ---"
if ($needsAdmin)  { Warn "ACTION: re-run the flagged commands in an ADMINISTRATOR PowerShell." }
if ($needsReboot) { Warn "ACTION: REBOOT, then re-run this script to verify." }
if ($needsAdmin -or $needsReboot) {
  Warn "Host not ready yet - resolve the actions above and re-run."
  exit 1
}
Info "Host looks ready. Next:  just dc-up   then   just dc-shell"
exit 0
