# Arret de Jena Fuseki
Write-Host ""
Write-Host "========================================" -ForegroundColor Red
Write-Host "  Arret de Jena Fuseki" -ForegroundColor Red
Write-Host "========================================" -ForegroundColor Red
Write-Host ""

$processes = Get-Process -Name "java" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*fuseki*" }

if ($processes) {
    foreach ($proc in $processes) {
        Write-Host "Arret du processus Fuseki (PID: $($proc.Id))..." -ForegroundColor Yellow
        Stop-Process -Id $proc.Id -Force
    }
    Write-Host ""
    Write-Host "Fuseki arrete avec succes." -ForegroundColor Green
} else {
    Write-Host "Aucun processus Fuseki en cours d'execution." -ForegroundColor Yellow
}
Write-Host ""
