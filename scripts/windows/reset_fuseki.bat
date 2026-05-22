@echo off
REM Script de reinitialisation complete de Fuseki
echo.
echo ========================================
echo   Reinitialisation de Fuseki
echo ========================================
echo.

REM Arreter Fuseki
echo 1. Arret de Fuseki...
taskkill /F /FI "WINDOWTITLE eq Apache Jena Fuseki*" 2>nul
timeout /t 2 /nobreak >nul

REM Supprimer les donnees
echo 2. Suppression des donnees...
set FUSEKI_RUN=C:\Users\david\Documents\Github\NSXAI\triplestore\apache-jena-fuseki-5.1.0\run

if exist "%FUSEKI_RUN%\system" (
    rmdir /s /q "%FUSEKI_RUN%\system"
    echo    - system/ supprime
)

if exist "%FUSEKI_RUN%\databases" (
    rmdir /s /q "%FUSEKI_RUN%\databases"
    echo    - databases/ supprime
)

echo.
echo ========================================
echo   Fuseki reinitialise avec succes
echo ========================================
echo.
echo Vous pouvez maintenant redemarrer Fuseki :
echo   .\scripts\windows\start_fuseki.bat
echo.
pause
