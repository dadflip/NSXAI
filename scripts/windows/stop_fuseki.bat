@echo off
REM Arret de Jena Fuseki
echo.
echo ========================================
echo   Arret de Jena Fuseki
echo ========================================
echo.

taskkill /F /FI "WINDOWTITLE eq Apache Jena Fuseki*" 2>nul
if %ERRORLEVEL% EQU 0 (
    echo Fuseki arrete avec succes.
) else (
    echo Aucun processus Fuseki en cours d'execution.
)
echo.
pause
