@echo off
rem Inicia plataforma-datos: Docker Desktop, PostgreSQL y la API.
rem Uso: doble clic, o "iniciar.bat" desde una terminal en cualquier carpeta.
rem Las pausas usan ping y no timeout: timeout falla si la entrada esta redirigida (tareas programadas).
setlocal
cd /d "%~dp0"
title plataforma-datos

echo.
echo  === plataforma-datos ===
echo.

rem --- 1. Configuracion --------------------------------------------------------
if not exist ".env" (
    echo  No existe .env: se crea a partir de .env.example
    copy /y ".env.example" ".env" >nul
)
findstr /r /c:"^PLATAFORMA_API_KEYS=..*" ".env" >nul
if errorlevel 1 (
    echo  AVISO: PLATAFORMA_API_KEYS esta vacio en .env, la API quedara abierta.
    echo         Usalo solo en tu equipo. Ver README, seccion API.
    echo.
)

rem --- 2. Docker Desktop -------------------------------------------------------
docker info >nul 2>&1
if not errorlevel 1 goto docker_listo

if not exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    echo  ERROR: no se encontro Docker Desktop. Instalalo desde https://www.docker.com/
    goto fallo
)
echo  Iniciando Docker Desktop...
start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set /a intentos=0
:esperar_docker
ping -n 6 127.0.0.1 >nul
docker info >nul 2>&1
if not errorlevel 1 goto docker_listo
set /a intentos+=1
if %intentos% lss 36 goto esperar_docker
echo  ERROR: Docker Desktop no respondio en 3 minutos. Abrelo a mano y vuelve a ejecutar este archivo.
goto fallo

:docker_listo
echo  Docker listo.

rem --- 3. Base de datos y API --------------------------------------------------
echo  Levantando PostgreSQL y la API (si el codigo cambio, primero actualiza la imagen)...
rem --build reconstruye la imagen solo si el codigo cambio (con cache tarda segundos)
docker compose up -d --build db api
if errorlevel 1 (
    echo  ERROR: docker compose no pudo levantar los servicios. Revisa el mensaje de arriba.
    goto fallo
)

rem --- 4. Esperar a que la API responda ---------------------------------------
echo  Esperando a la API...
set /a intentos=0
:esperar_api
curl -sf http://localhost:8000/health >nul 2>&1
if not errorlevel 1 goto api_lista
set /a intentos+=1
if %intentos% geq 30 (
    echo  ERROR: la API no respondio en 60 segundos. Ultimas lineas del registro:
    docker compose logs --tail 20 api
    goto fallo
)
ping -n 3 127.0.0.1 >nul
goto esperar_api

:api_lista
echo.
echo  Servicio en marcha:
echo    Plataforma web ..... http://localhost:8000
echo    API y documentacion  http://localhost:8000/docs
echo    PostgreSQL ......... localhost:5432  (base: plataforma)
echo.
echo  Comandos utiles:
echo    Cargar datos ....... docker compose run --rm cli ingest --all
echo    Reconstruir capas .. docker compose run --rm cli dbt-sources ^&^& docker compose run --rm dbt build
echo    Ver registros ...... docker compose logs -f api
echo    Detener ............ docker compose down
echo.
pause
endlocal
exit /b 0

:fallo
echo.
pause
endlocal
exit /b 1
