# ============================================================
#  Installation de l'agent FreeStream (Windows, PowerShell)
#  Usage : clic droit > Executer avec PowerShell, ou :
#    powershell -ExecutionPolicy Bypass -File scripts\install.ps1
# ============================================================
$ErrorActionPreference = "Stop"
$agent = Split-Path -Parent $PSScriptRoot
Set-Location $agent

Write-Host "1/4 Verification de Python..."
python --version
if ($LASTEXITCODE -ne 0) { throw "Python introuvable : installez Python 3.11+ depuis python.org (cochez 'Add to PATH')." }

Write-Host "2/4 Creation de l'environnement virtuel .venv..."
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "3/4 Verification de FFmpeg..."
$ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ff) {
  Write-Warning "FFmpeg absent du PATH. Installation via winget (Gyan.FFmpeg)..."
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  Write-Warning "Fermez et rouvrez PowerShell pour que FFmpeg soit dans le PATH."
}

Write-Host "4/4 Copie de la configuration d'exemple..."
if (-not (Test-Path "config.json")) { Copy-Item config.example.json config.json }

Write-Host ""
Write-Host "Installation terminee. Pensez au pilote ViGEmBus pour la manette virtuelle :"
Write-Host "  https://github.com/nefarius/ViGEmBus/releases"
Write-Host "Lancement : scripts\start-agent.bat"
