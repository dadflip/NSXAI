# Demarrage de l'API Python NSXAI
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Demarrage de l'API NSXAI" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

Set-Location (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent)

# Verifier que le venv existe
if (-not (Test-Path "venv")) {
    Write-Host "ERREUR: Environnement virtuel non trouve" -ForegroundColor Red
    Write-Host "Executez d'abord : .\scripts\windows\setup_venv.bat" -ForegroundColor Yellow
    exit 1
}

# Activer le venv
& "venv\Scripts\Activate.ps1"

# Lancer l'API
Write-Host "Demarrage de l'API sur http://localhost:8000" -ForegroundColor Cyan
Write-Host "Documentation : http://localhost:8000/api/docs" -ForegroundColor Cyan
Write-Host ""
python -m nsxai.api.main
