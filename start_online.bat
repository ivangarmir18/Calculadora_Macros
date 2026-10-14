@echo off
rem Arranca la Calculadora de Macros con acceso remoto seguro (HTTPS)
rem Permite usarla desde el móvil con datos móviles (4G/5G) o fuera de casa.
cd /d "%~dp0"
set PYTHONUTF8=1

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo No encuentro Python. Instala Python 3.9 o superior desde https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Preparando entorno por primera vez...
  %PY% -m venv .venv || ( echo Error creando entorno virtual & pause & exit /b 1 )
)

".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || ( echo Error instalando dependencias & pause & exit /b 1 )

rem Descargar cloudflared si no existe
if not exist "cloudflared.exe" (
  echo Descargando tunel seguro de Cloudflare (solo la primera vez)...
  curl -sLo cloudflared.exe https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
  if not exist "cloudflared.exe" (
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe'"
  )
)

echo.
echo =====================================================================
echo   Iniciando Calculadora de Macros con acceso fuera de casa (HTTPS)
echo =====================================================================
echo.

rem Arranca la app en segundo plano
start /B "" ".venv\Scripts\python.exe" app.py --no-browser

timeout /t 2 /nobreak >nul

if exist "cloudflared.exe" (
  echo Generando tu enlace seguro para el movil...
  echo Abre el enlace 'https://xxxx.trycloudflare.com' que aparecera abajo
  echo en tu movil desde cualquier lugar (incluso con datos 4G/5G).
  echo.
  cloudflared.exe tunnel --url http://localhost:5000
) else (
  echo No se pudo descargar cloudflared.exe. Usa start.bat para la red local.
  pause
)
