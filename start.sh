#!/usr/bin/env sh
# Arranca la calculadora de macros en macOS/Linux:  ./start.sh   (admite --local, --port N, --no-browser)
# Crea un entorno aislado (.venv) la primera vez e instala lo necesario.
cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1

PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
  echo "No encuentro Python 3. Instálalo (https://www.python.org/downloads/ o con tu gestor de paquetes)." >&2
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Preparando por primera vez, un momento..."
  "$PY" -m venv .venv || { echo "Falta el módulo venv. En Debian/Ubuntu: sudo apt install python3-venv" >&2; exit 1; }
fi
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt || { echo "Error instalando dependencias. ¿Hay internet?" >&2; exit 1; }
exec .venv/bin/python app.py "$@"

