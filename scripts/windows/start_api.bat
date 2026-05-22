@echo off
REM Demarrage de l'API Python NSXAI
echo.
echo ========================================
echo   Demarrage de l'API NSXAI
echo ========================================
echo.

cd /d "%~dp0\..\.."

REM Verifier que le venv existe
if not exist "venv\" (
    echo ERREUR: Environnement virtuel non trouve
    echo Executez d'abord : .\scripts\windows\setup_venv.bat
    pause
    exit /b 1
)

REM Activer le venv
call venv\Scripts\activate.bat

REM Lancer l'API
echo Demarrage de l'API sur http://localhost:8000
echo Documentation : http://localhost:8000/api/docs
echo.
python -m nsxai.api.main
