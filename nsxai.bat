@echo off
REM Raccourci Windows pour nsxai_cli.py
REM Utilise le venv si present, sinon le Python systeme

set "SCRIPT_DIR=%~dp0"

if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    "%SCRIPT_DIR%venv\Scripts\python.exe" "%SCRIPT_DIR%nsxai_cli.py" %*
) else (
    echo [WARN] venv non trouve - utilisation du Python systeme
    echo        Lancez d'abord : python scripts\windows\setup_venv.bat
    python "%SCRIPT_DIR%nsxai_cli.py" %*
)
