"""Calculadora de macros: backend Flask + SQLite.

Ejecutar:  python app.py   ->  http://localhost:5000
"""
import uuid
from datetime import date, datetime
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

from db import get_conn, init_db

BASE = Path(__file__).parent
UPLOADS = BASE / "data" / "uploads"
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MEALS = ["desayuno", "comida", "merienda", "cena", "otro"]

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # fotos de hasta 8 MB


# ---------------------------------------------------------------- utilidades
def num(value, default=0.0):
    """Convierte a float aceptando coma decimal; devuelve default si está vacío."""
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        abort(400, f"Número no válido: {value!r}")


def valid_date(s):
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except (TypeError, ValueError):
        abort(400, "Fecha no válida (usa YYYY-MM-DD)")
    return s


def rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


def scale(food, grams):
    """Macros de `grams` gramos de un alimento (los valores del alimento son por 100 g)."""
    f = grams / 100.0
    return {
        "kcal": round(food["kcal"] * f, 1),
        "protein": round(food["protein"] * f, 1),
        "carbs": round(food["carbs"] * f, 1),
        "fat": round(food["fat"] * f, 1),
    }


def totals(entries):
    t = {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    for e in entries:
        for k in t:
            t[k] += e[k]
    return {k: round(v, 1) for k, v in t.items()}


def get_goals(conn):
    s = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM settings")}
    return {
        "kcal": float(s["goal_kcal"]),
        "protein": float(s["goal_protein"]),
        "carbs": float(s["goal_carbs"]),
        "fat": float(s["goal_fat"]),
    }


def insert_food_entry(conn, day, meal, food_id, grams):
    food = conn.execute("SELECT * FROM foods WHERE id=?", (food_id,)).fetchone()
    if not food:
        abort(404, "Alimento no encontrado")
    m = scale(food, grams)
    name = food["name"] + (f" ({food['brand']})" if food["brand"] else "")
    cur = conn.execute(
        "INSERT INTO entries(date,time,meal,kind,name,grams,kcal,protein,carbs,fat,food_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (day, datetime.now().strftime("%H:%M"), meal, "food", name, grams,
         m["kcal"], m["protein"], m["carbs"], m["fat"], food_id),
    )
    return cur.lastrowid


def clean_meal(m):
    return m if m in MEALS else "otro"


# ------------------------------------------------------------------- páginas
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOADS, filename)


@app.errorhandler(400)
@app.errorhandler(404)
def json_error(e):
    return jsonify(error=e.description), e.code


# --------------------------------------------------------------------- día
@app.get("/api/day/<day>")
def get_day(day):
    valid_date(day)
    with get_conn() as conn:
        entries = rows(conn.execute("SELECT * FROM entries WHERE date=? ORDER BY time, id", (day,)))
        return jsonify(date=day, entries=entries, totals=totals(entries), goals=get_goals(conn))


@app.get("/api/today")
def today():
    return jsonify(date=date.today().isoformat())


# ----------------------------------------------------------------- entradas
@app.post("/api/entries")
def add_entry():
    d = request.get_json(force=True)
    day = valid_date(d.get("date") or date.today().isoformat())
    meal = clean_meal(d.get("meal"))
    with get_conn() as conn:
        if d.get("kind") == "quick":
            # Entrada rápida: solo kcal (y opcionalmente macros). Ej. "cumpleaños ~500 kcal".
            name = (d.get("name") or "").strip() or "Comida sin detallar"
            conn.execute(
                "INSERT INTO entries(date,time,meal,kind,name,kcal,protein,carbs,fat) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (day, datetime.now().strftime("%H:%M"), meal, "quick", name,
                 num(d.get("kcal")), num(d.get("protein")), num(d.get("carbs")), num(d.get("fat"))),
            )
        else:
            grams = num(d.get("grams"))
            if grams <= 0:
                abort(400, "Indica los gramos")
            insert_food_entry(conn, day, meal, d.get("food_id"), grams)
    return jsonify(ok=True), 201


@app.post("/api/entries/preset")
def add_preset_entries():
    """Añade todos los ingredientes de un preset (con gramos ajustados) al día."""
    d = request.get_json(force=True)
    day = valid_date(d.get("date") or date.today().isoformat())
    meal = clean_meal(d.get("meal"))
    with get_conn() as conn:
        for it in d.get("items", []):
            grams = num(it.get("grams"))
            if grams > 0:
                insert_food_entry(conn, day, meal, it["food_id"], grams)
    return jsonify(ok=True), 201


@app.put("/api/entries/<int:eid>")
def update_entry(eid):
    d = request.get_json(force=True)
    with get_conn() as conn:
        e = conn.execute("SELECT * FROM entries WHERE id=?", (eid,)).fetchone()
        if not e:
            abort(404, "Entrada no encontrada")
        meal = clean_meal(d.get("meal", e["meal"]))
        if e["kind"] == "food" and e["food_id"] and "grams" in d:
            food = conn.execute("SELECT * FROM foods WHERE id=?", (e["food_id"],)).fetchone()
            if food:
                grams = num(d["grams"])
                m = scale(food, grams)
                conn.execute("UPDATE entries SET grams=?, kcal=?, protein=?, carbs=?, fat=?, meal=? WHERE id=?",
                             (grams, m["kcal"], m["protein"], m["carbs"], m["fat"], meal, eid))
                return jsonify(ok=True)
        conn.execute(
            "UPDATE entries SET name=?, kcal=?, protein=?, carbs=?, fat=?, meal=? WHERE id=?",
            ((d.get("name") or e["name"]).strip(), num(d.get("kcal"), e["kcal"]),
             num(d.get("protein"), e["protein"]), num(d.get("carbs"), e["carbs"]),
             num(d.get("fat"), e["fat"]), meal, eid),
        )
    return jsonify(ok=True)


@app.delete("/api/entries/<int:eid>")
def delete_entry(eid):
    with get_conn() as conn:
        conn.execute("DELETE FROM entries WHERE id=?", (eid,))
    return jsonify(ok=True)


# ----------------------------------------------------------------- histórico
@app.get("/api/history")
def history():
    days = min(int(request.args.get("days", 30)), 365)
    with get_conn() as conn:
        data = rows(conn.execute(
            "SELECT date, ROUND(SUM(kcal),1) kcal, ROUND(SUM(protein),1) protein, "
            "ROUND(SUM(carbs),1) carbs, ROUND(SUM(fat),1) fat, COUNT(*) n "
            "FROM entries WHERE date >= date('now','localtime', ?) "
            "GROUP BY date ORDER BY date DESC", (f"-{days - 1} days",)))
        # El promedio solo cuenta los días con registros (un día sin apuntar no es un día de 0 kcal).
        avg = {k: round(sum(r[k] for r in data) / len(data), 1) if data else 0
               for k in ("kcal", "protein", "carbs", "fat")}
        return jsonify(days=data, average=avg, logged_days=len(data), goals=get_goals(conn))


# ---------------------------------------------------------------- alimentos
def food_payload(d):
    name = (d.get("name") or "").strip()
    if not name:
        abort(400, "El nombre es obligatorio")
    unit_g = num(d.get("unit_g"), None)
    return (name, (d.get("brand") or "").strip(), num(d.get("kcal")), num(d.get("protein")),
            num(d.get("carbs")), num(d.get("fat")), unit_g, (d.get("unit_name") or "").strip())


@app.get("/api/foods")
def list_foods():
    q = (request.args.get("q") or "").strip()
    sql = ("SELECT f.*, (SELECT COUNT(*) FROM entries e WHERE e.food_id=f.id) uses FROM foods f ")
    params = []
    if q:
        sql += "WHERE f.name LIKE ? OR f.brand LIKE ? "
        params = [f"%{q}%", f"%{q}%"]
    sql += "ORDER BY uses DESC, f.name COLLATE NOCASE"   # los más usados primero = más rápido
    with get_conn() as conn:
        return jsonify(rows(conn.execute(sql, params)))


@app.post("/api/foods")
def create_food():
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO foods(name,brand,kcal,protein,carbs,fat,unit_g,unit_name) VALUES (?,?,?,?,?,?,?,?)",
            food_payload(request.get_json(force=True)))
        return jsonify(id=cur.lastrowid), 201


@app.put("/api/foods/<int:fid>")
def update_food(fid):
    with get_conn() as conn:
        conn.execute(
            "UPDATE foods SET name=?,brand=?,kcal=?,protein=?,carbs=?,fat=?,unit_g=?,unit_name=? WHERE id=?",
            (*food_payload(request.get_json(force=True)), fid))
    return jsonify(ok=True)


@app.delete("/api/foods/<int:fid>")
def delete_food(fid):
    with get_conn() as conn:
        used = conn.execute("SELECT COUNT(*) FROM preset_items WHERE food_id=?", (fid,)).fetchone()[0]
        if used:
            abort(400, "Este alimento está en algún preset; quítalo de ahí primero")
        conn.execute("DELETE FROM foods WHERE id=?", (fid,))
    return jsonify(ok=True)


@app.post("/api/foods/<int:fid>/photo")
def upload_photo(fid):
    f = request.files.get("photo")
    if not f or not f.filename:
        abort(400, "No hay archivo")
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        abort(400, "Formato no permitido (jpg, png, webp, gif)")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    f.save(UPLOADS / name)
    with get_conn() as conn:
        old = conn.execute("SELECT photo FROM foods WHERE id=?", (fid,)).fetchone()
        if not old:
            (UPLOADS / name).unlink(missing_ok=True)
            abort(404, "Alimento no encontrado")
        if old["photo"]:
            (UPLOADS / old["photo"]).unlink(missing_ok=True)
        conn.execute("UPDATE foods SET photo=? WHERE id=?", (name, fid))
    return jsonify(photo=name)


# ------------------------------------------------------------------ presets
def load_presets(conn, pid=None):
    presets = rows(conn.execute(
        "SELECT * FROM presets" + (" WHERE id=?" if pid else "") + " ORDER BY name COLLATE NOCASE",
        (pid,) if pid else ()))
    for p in presets:
        p["items"] = rows(conn.execute(
            "SELECT pi.food_id, pi.grams, f.name, f.brand, f.kcal, f.protein, f.carbs, f.fat, f.photo "
            "FROM preset_items pi JOIN foods f ON f.id=pi.food_id WHERE pi.preset_id=? ORDER BY pi.id",
            (p["id"],)))
        p["totals"] = totals([{**scale(i, i["grams"])} for i in p["items"]])
    return presets


def save_preset_items(conn, pid, items):
    conn.execute("DELETE FROM preset_items WHERE preset_id=?", (pid,))
    for it in items:
        g = num(it.get("grams"))
        if g > 0:
            conn.execute("INSERT INTO preset_items(preset_id,food_id,grams) VALUES (?,?,?)",
                         (pid, it["food_id"], g))


@app.get("/api/presets")
def list_presets():
    with get_conn() as conn:
        return jsonify(load_presets(conn))


@app.post("/api/presets")
def create_preset():
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip()
    if not name:
        abort(400, "El nombre es obligatorio")
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO presets(name, meal) VALUES (?,?)", (name, clean_meal(d.get("meal"))))
        save_preset_items(conn, cur.lastrowid, d.get("items", []))
        return jsonify(id=cur.lastrowid), 201


@app.put("/api/presets/<int:pid>")
def update_preset(pid):
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip()
    if not name:
        abort(400, "El nombre es obligatorio")
    with get_conn() as conn:
        conn.execute("UPDATE presets SET name=?, meal=? WHERE id=?", (name, clean_meal(d.get("meal")), pid))
        save_preset_items(conn, pid, d.get("items", []))
    return jsonify(ok=True)


@app.delete("/api/presets/<int:pid>")
def delete_preset(pid):
    with get_conn() as conn:
        conn.execute("DELETE FROM presets WHERE id=?", (pid,))
    return jsonify(ok=True)


# ------------------------------------------------------------------ ajustes
@app.get("/api/settings")
def get_settings():
    with get_conn() as conn:
        return jsonify(get_goals(conn))


@app.put("/api/settings")
def put_settings():
    d = request.get_json(force=True)
    with get_conn() as conn:
        for k in ("kcal", "protein", "carbs", "fat"):
            if k in d:
                conn.execute("UPDATE settings SET value=? WHERE key=?", (str(num(d[k])), f"goal_{k}"))
    return jsonify(ok=True)


init_db()

if __name__ == "__main__":
    # host 0.0.0.0 para poder abrirlo desde el móvil en la misma wifi: http://<ip-del-pc>:5000
    app.run(host="0.0.0.0", port=5000, debug=False)
