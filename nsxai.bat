@echo off
REM NSXAI - Lanceur Windows
REM
REM Usage:
REM   nsxai.bat dev       Demarre Fuseki, API et frontend Vite (superviseur au premier plan)
REM   nsxai.bat start     Demarre Fuseki et l'API (et optionnellement le frontend) en arriere-plan
REM   nsxai.bat stop      Arrete tous les services
REM   nsxai.bat status    Affiche l'etat
REM   nsxai.bat reset     Reinitialise la base de donnees

set "SCRIPT_DIR=%~dp0"

if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    "%SCRIPT_DIR%venv\Scripts\python.exe" "%SCRIPT_DIR%nsxai_cli.py" %*
) else (
    echo [WARN] venv non trouve - utilisation du Python systeme
    python "%SCRIPT_DIR%nsxai_cli.py" %*
)
