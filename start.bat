@echo off
rem Arranca la calculadora de macros en Windows. Doble clic para usarla.
rem Crea un entorno aislado (.venv) la primera vez e instala lo necesario.
rem Argumentos opcionales: --local (solo este PC) --port 5001 --no-browser
cd /d "%~dp0"
set PYTHONUTF8=1

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo No encuentro Python. Instala Python 3.9 o superior desde https://www.python.org/downloads/
  echo y marca la casilla "Add python.exe to PATH". Despues vuelve a abrir este archivo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Preparando por primera vez, un momento...
  %PY% -m venv .venv || ( echo No se pudo crear el entorno virtual. & pause & exit /b 1 )
)
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || ( echo Error instalando dependencias. Hay internet? & pause & exit /b 1 )
".venv\Scripts\python.exe" app.py %*
pause

