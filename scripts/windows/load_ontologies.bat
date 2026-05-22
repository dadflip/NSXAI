@echo off
REM Charger les ontologies dans Fuseki
echo.
echo ========================================
echo   Chargement des ontologies
echo ========================================
echo.

cd /d "%~dp0\..\.."

REM Activer le venv
call venv\Scripts\activate.bat

REM Lancer le script
python scripts\load_to_fuseki.py

pause
