@echo off
REM Creation et configuration de l'environnement virtuel Python
echo.
echo ========================================
echo   Configuration environnement Python
echo ========================================
echo.

cd /d "%~dp0\..\.."

REM Verifier la version Python
python --version 2>&1 | findstr /R "3\.[0-9]" >nul
if %ERRORLEVEL% NEQ 0 (
    echo ERREUR: Python non trouve dans le PATH
    pause
    exit /b 1
)

echo Version Python detectee :
python --version

REM Supprimer l'ancien venv si present
if exist "venv\" (
    echo.
    echo Suppression de l'ancien environnement virtuel...
    rmdir /s /q venv
    echo    OK
)

REM Creer le venv
echo.
echo 1. Creation de l'environnement virtuel...
python -m venv venv
if %ERRORLEVEL% NEQ 0 (
    echo ERREUR: Impossible de creer le venv
    pause
    exit /b 1
)
echo    OK

REM Activer et installer les dependances
echo.
echo 2. Mise a jour de pip...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
echo    OK

echo.
echo 3. Installation requirements-api.txt...
pip install -r requirements-api.txt
if %ERRORLEVEL% NEQ 0 (
    echo ERREUR: Installation des dependances API echouee
    pause
    exit /b 1
)
echo    OK

REM Installer requirements.txt si present
if exist "requirements.txt" (
    echo.
    echo 4. Installation requirements.txt...
    pip install -r requirements.txt --quiet
    echo    OK
)

echo.
echo ========================================
echo   Installation terminee
echo ========================================
echo.
echo Pour activer l'environnement virtuel :
echo   venv\Scripts\activate.bat
echo.
echo Pour demarrer l'API :
echo   python -m nsxai.api.main
echo.
pause
