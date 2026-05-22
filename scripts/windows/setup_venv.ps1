# Creation et configuration de l'environnement virtuel Python
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Configuration environnement Python"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Set-Location (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent)

# Verifier Python
try {
    $pyVersion = python --version 2>&1
    Write-Host "Version Python detectee : $pyVersion"
} catch {
    Write-Host "ERREUR: Python non trouve dans le PATH" -ForegroundColor Red
    exit 1
}

# Supprimer l'ancien venv si present
if (Test-Path "venv") {
    Write-Host ""
    Write-Host "Suppression de l'ancien environnement virtuel..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "venv"
    Write-Host "   [OK]" -ForegroundColor Green
}

# Creer le venv
Write-Host ""
Write-Host "1. Creation de l'environnement virtuel..." -ForegroundColor Cyan
python -m venv venv
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERREUR: Impossible de creer le venv" -ForegroundColor Red
    exit 1
}
Write-Host "   [OK]" -ForegroundColor Green

# Activer
Write-Host ""
Write-Host "2. Mise a jour de pip..." -ForegroundColor Cyan
& "venv\Scripts\Activate.ps1"
python -m pip install --upgrade pip --quiet
Write-Host "   [OK]" -ForegroundColor Green

# Installer requirements-api.txt
Write-Host ""
Write-Host "3. Installation requirements-api.txt..." -ForegroundColor Cyan
pip install -r requirements-api.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERREUR: Installation des dependances API echouee" -ForegroundColor Red
    exit 1
}
Write-Host "   [OK]" -ForegroundColor Green

# Installer requirements.txt si present
if (Test-Path "requirements.txt") {
    Write-Host ""
    Write-Host "4. Installation requirements.txt..." -ForegroundColor Cyan
    pip install -r requirements.txt --quiet
    Write-Host "   [OK]" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Installation terminee"
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Pour activer l'environnement virtuel :" -ForegroundColor Cyan
Write-Host "  venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "Pour demarrer l'API :" -ForegroundColor Cyan
Write-Host "  python -m nsxai.api.main"
Write-Host ""
