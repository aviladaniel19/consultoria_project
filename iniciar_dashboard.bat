@echo off
title VIGIA API - Servidor
echo ============================================
echo   VIGIA API - Red de Monitoreo
echo ============================================
echo.

cd /d "%~dp0backend"

set "VENV_DIR=%~dp0backend\.venv"
set "PY=%VENV_DIR%\Scripts\python.exe"

rem --- Crear entorno virtual si no existe ---
if not exist "%PY%" (
    echo Creando entorno virtual en backend\.venv ...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual. Verifica que Python este instalado.
        pause
        exit /b 1
    )
)

rem --- Instalar dependencias si faltan ---
"%PY%" -c "import fastapi, uvicorn, jose, passlib, sqlalchemy" >nul 2>&1
if errorlevel 1 (
    echo Instalando dependencias ^(solo la primera vez^)...
    "%PY%" -m pip install --upgrade pip
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Fallo la instalacion de dependencias.
        pause
        exit /b 1
    )
)

echo.
echo  El tablero se abrira en: http://localhost:8000
echo  Documentacion API:       http://localhost:8000/docs
echo  Presiona Ctrl+C para detener el servidor.
echo.

rem --- Abrir navegador tras unos segundos (en segundo plano) ---
start "" /b cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:8000"

rem --- Iniciar servidor (usa el python del venv, nunca uno global) ---
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

pause
