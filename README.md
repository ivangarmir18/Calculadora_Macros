# Calculadora de Macros

App personal para apuntar lo que comes cada día y ver calorías y macros. Python (Flask) + HTML/JS + SQLite.

## Arrancar

```powershell
pip install -r requirements.txt
python app.py
```

Abre <http://localhost:5000>. Desde el móvil (misma wifi): `http://<IP-de-tu-PC>:5000`.
La base de datos se crea sola en `data/macros.db` (no se sube a git, es tuya).

## Qué hace

- **Hoy**: resumen de kcal y macros frente a tus objetivos, comidas agrupadas, navegación por días. La fecha se detecta sola.
- **Añadir alimento**: buscador (los más usados salen primero), gramos o unidades, vista previa de macros.
- **Presets**: combinaciones repetidas (batido = leche + proteína + cereales). Al añadir puedes cambiar gramos o multiplicar todo.
- **Solo kcal**: para cumpleaños y similares, escribes "~500 kcal" y ya, sin detallar.
- **Alimentos**: tu base de datos con macros por 100 g, unidad opcional (huevo, scoop) y foto.
- **Histórico**: kcal y macros por día, promedio de 7/30/90 días y edición de objetivos.

Ver [STATUS.md](STATUS.md) para lo hecho y lo pendiente.

## Estructura

```
app.py          API Flask
db.py           esquema SQLite + alimentos iniciales
static/         index.html, style.css, app.js
data/           macros.db y fotos (ignorado por git)
```
