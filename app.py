"""Calculadora de macros: backend Flask + SQLite.

Ejecutar:  python app.py            (accesible desde el móvil en la misma wifi)
           python app.py --local    (solo este PC)
Ver `python app.py --help`.
"""
import argparse
import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import socket
import threading
import time
import uuid
import webbrowser
from datetime import date, datetime
from pathlib import Path

from flask import Flask, Response, abort, jsonify, make_response, request, send_from_directory

import db
import gemini
import off
import pdf_report
from db import get_conn, init_db

try:  # opcional: solo para el código QR de "conectar el móvil"
    import qrcode
    import qrcode.image.svg
except ImportError:  # pragma: no cover
    qrcode = None

BASE = Path(__file__).resolve().parent
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MEALS = ["desayuno", "comida", "merienda", "cena", "otro"]
PROFILE_KEYS = ("sex", "age", "height", "weight", "activity", "goal", "tdee", "lbm")
EXPORT_TABLES = ["foods", "presets", "preset_items", "entries", "weights"]

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # copias de seguridad con fotos
app.json.ensure_ascii = False


def uploads_dir():
    return db.DB_PATH.parent / "uploads"


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


def get_setting(conn, key, default=""):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(conn, key, value):
    conn.execute("INSERT INTO settings(key,value) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def get_goals(conn):
    return {k: float(get_setting(conn, f"goal_{k}", "0")) for k in ("kcal", "protein", "carbs", "fat")}


def clean_meal(m):
    return m if m in MEALS else "otro"


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


def copy_entry_row(conn, e, day, meal=None):
    conn.execute(
        "INSERT INTO entries(date,time,meal,kind,name,grams,kcal,protein,carbs,fat,food_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (day, datetime.now().strftime("%H:%M"), meal or e["meal"], e["kind"], e["name"], e["grams"],
         e["kcal"], e["protein"], e["carbs"], e["fat"], e["food_id"]))


# ------------------------------------------------------------------ acceso (PIN opcional)
def hash_pin(pin, salt=None):
    salt = salt or secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 120_000)
    return salt.hex() + "$" + h.hex()


def check_pin(stored, pin):
    try:
        salt_hex, _ = stored.split("$")
        return hmac.compare_digest(hash_pin(pin, bytes.fromhex(salt_hex)), stored)
    except ValueError:
        return False


def is_authed(conn):
    if not get_setting(conn, "pin_hash"):
        return True
    tok = get_setting(conn, "auth_token")
    return bool(tok) and hmac.compare_digest(request.cookies.get("auth", ""), tok)


def set_auth_cookie(resp, token):
    resp.set_cookie("auth", token, max_age=60 * 60 * 24 * 365, httponly=True, samesite="Lax")
    return resp


OPEN_PATHS = ("/", "/manifest.webmanifest", "/sw.js", "/report")


@app.before_request
def guard():
    p = request.path
    if p in OPEN_PATHS or p.startswith("/static/") or p.startswith("/api/auth/"):
        return None
    with get_conn() as conn:
        if is_authed(conn):
            return None
    return jsonify(error="Acceso protegido"), 401


@app.get("/api/auth/status")
def auth_status():
    with get_conn() as conn:
        return jsonify(pin_set=bool(get_setting(conn, "pin_hash")), authed=is_authed(conn))


@app.post("/api/auth/login")
def auth_login():
    pin = str((request.get_json(force=True) or {}).get("pin", ""))
    with get_conn() as conn:
        stored = get_setting(conn, "pin_hash")
        if stored and not check_pin(stored, pin):
            time.sleep(1)  # frena la fuerza bruta
            abort(401, "PIN incorrecto")
        resp = make_response(jsonify(ok=True))
        return set_auth_cookie(resp, get_setting(conn, "auth_token")) if stored else resp


@app.post("/api/auth/pin")
def auth_set_pin():
    """Pone, cambia o quita (pin vacío) el PIN. Si ya hay uno hay que dar el actual."""
    d = request.get_json(force=True) or {}
    new = str(d.get("pin", "")).strip()
    with get_conn() as conn:
        stored = get_setting(conn, "pin_hash")
        if stored and not check_pin(stored, str(d.get("current", ""))):
            time.sleep(1)
            abort(401, "PIN actual incorrecto")
        if not new:
            set_setting(conn, "pin_hash", "")
            set_setting(conn, "auth_token", "")
            return jsonify(ok=True, pin_set=False)
        if len(new) < 4:
            abort(400, "El PIN debe tener al menos 4 caracteres")
        token = secrets.token_urlsafe(32)
        set_setting(conn, "pin_hash", hash_pin(new))
        set_setting(conn, "auth_token", token)
        return set_auth_cookie(make_response(jsonify(ok=True, pin_set=True)), token)


# ------------------------------------------------------------------- páginas
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/manifest.webmanifest")
def manifest():
    return send_from_directory(app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")


@app.get("/sw.js")
def service_worker():  # en la raíz para que su alcance sea toda la app
    r = send_from_directory(app.static_folder, "sw.js", mimetype="text/javascript")
    r.headers["Cache-Control"] = "no-cache"
    return r


@app.get("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(uploads_dir(), filename)


@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(404)
@app.errorhandler(502)
def json_error(e):
    return jsonify(error=e.description), e.code


@app.errorhandler(413)
def too_big(e):
    return jsonify(error="Archivo demasiado grande"), 413


# --------------------------------------------------------------------- día
@app.get("/api/day/<day>")
def get_day(day):
    valid_date(day)
    with get_conn() as conn:
        entries = rows(conn.execute("SELECT * FROM entries WHERE date=? ORDER BY time, id", (day,)))
        return jsonify(date=day, entries=entries, totals=totals(entries), goals=get_goals(conn))


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
    """Añade los ingredientes de un preset al día: o bien desglosados (cada ingrediente por separado), o agrupados en 1 sola línea."""
    d = request.get_json(force=True)
    day = valid_date(d.get("date") or date.today().isoformat())
    meal = clean_meal(d.get("meal"))
    grouped = bool(d.get("grouped"))
    name = (d.get("name") or "Combo").strip()
    items = d.get("items", [])

    with get_conn() as conn:
        if grouped:
            t = {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
            total_grams = 0.0
            for it in items:
                g = num(it.get("grams"))
                if g > 0:
                    f = conn.execute("SELECT * FROM foods WHERE id=?", (it["food_id"],)).fetchone()
                    if f:
                        m = scale(f, g)
                        for k in t:
                            t[k] += m[k]
                        total_grams += g
            conn.execute(
                "INSERT INTO entries(date,time,meal,kind,name,grams,kcal,protein,carbs,fat) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (day, datetime.now().strftime("%H:%M"), meal, "combo", name, total_grams or None,
                 round(t["kcal"], 1), round(t["protein"], 1), round(t["carbs"], 1), round(t["fat"], 1)),
            )
        else:
            for it in items:
                grams = num(it.get("grams"))
                if grams > 0:
                    insert_food_entry(conn, day, meal, it["food_id"], grams)
    return jsonify(ok=True), 201


@app.post("/api/entries/copy")
def copy_entries():
    """Copia entradas de un día a otro (opcionalmente solo una comida): 'repetir ayer'."""
    d = request.get_json(force=True)
    src, dst = valid_date(d.get("from_date")), valid_date(d.get("to_date"))
    sql, params = "SELECT * FROM entries WHERE date=?", [src]
    if d.get("meal"):
        sql += " AND meal=?"
        params.append(d["meal"])
    with get_conn() as conn:
        found = conn.execute(sql + " ORDER BY time, id", params).fetchall()
        for e in found:
            copy_entry_row(conn, e, dst)
    return jsonify(copied=len(found)), 201


@app.post("/api/entries/<int:eid>/copy")
def copy_one_entry(eid):
    d = request.get_json(force=True)
    with get_conn() as conn:
        e = conn.execute("SELECT * FROM entries WHERE id=?", (eid,)).fetchone()
        if not e:
            abort(404, "Entrada no encontrada")
        copy_entry_row(conn, e, valid_date(d.get("date")), clean_meal(d.get("meal") or e["meal"]))
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
    try:
        days = max(1, min(int(request.args.get("days", 30)), 365))
    except ValueError:
        abort(400, "days no válido")
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


# --------------------------------------------------------------------- peso
@app.get("/api/weights")
def list_weights():
    with get_conn() as conn:
        return jsonify(rows(conn.execute("SELECT * FROM weights ORDER BY date")))


@app.post("/api/weights")
def put_weight():
    d = request.get_json(force=True)
    kg = num(d.get("kg"))
    if not 20 <= kg <= 400:
        abort(400, "Peso no válido")
    day = valid_date(d.get("date") or date.today().isoformat())
    with get_conn() as conn:
        conn.execute("INSERT INTO weights(date,kg) VALUES (?,?) ON CONFLICT(date) DO UPDATE SET kg=excluded.kg",
                     (day, kg))
    return jsonify(ok=True), 201


@app.delete("/api/weights/<day>")
def delete_weight(day):
    with get_conn() as conn:
        conn.execute("DELETE FROM weights WHERE date=?", (valid_date(day),))
    return jsonify(ok=True)


# ---------------------------------------------------------------- alimentos
def save_photo_bytes(data, ext):
    uploads_dir().mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (uploads_dir() / name).write_bytes(data)
    return name


def food_payload(d):
    name = (d.get("name") or "").strip()
    if not name:
        abort(400, "El nombre es obligatorio")
    category = (d.get("category") or "otros").strip()
    return (name, (d.get("brand") or "").strip(), num(d.get("kcal")), num(d.get("protein")),
            num(d.get("carbs")), num(d.get("fat")), num(d.get("unit_g"), None),
            (d.get("unit_name") or "").strip(), re.sub(r"\D", "", str(d.get("barcode") or "")),
            category)


FOOD_COLS = "name,brand,kcal,protein,carbs,fat,unit_g,unit_name,barcode,category"


@app.get("/api/foods")
def list_foods():
    q = (request.args.get("q") or "").strip()
    cat = (request.args.get("category") or "").strip().lower()
    sql = "SELECT f.*, (SELECT COUNT(*) FROM entries e WHERE e.food_id=f.id) uses FROM foods f WHERE 1=1 "
    params = []
    if q:
        sql += "AND (f.name LIKE ? OR f.brand LIKE ?) "
        params += [f"%{q}%", f"%{q}%"]
    if cat and cat not in ("todos", "all", ""):
        sql += "AND f.category=? "
        params.append(cat)
    sql += "ORDER BY uses DESC, f.name COLLATE NOCASE"   # los más usados primero = más rápido
    with get_conn() as conn:
        return jsonify(rows(conn.execute(sql, params)))


@app.post("/api/foods")
def create_food():
    d = request.get_json(force=True)
    payload = food_payload(d)
    photo = ""
    if d.get("photo_url"):  # alimentos importados de Open Food Facts traen foto
        img = off.download_image(d["photo_url"])
        if img:
            photo = save_photo_bytes(*img)
    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT INTO foods({FOOD_COLS},photo) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (*payload, photo))
        return jsonify(id=cur.lastrowid, photo=photo), 201


@app.put("/api/foods/<int:fid>")
def update_food(fid):
    with get_conn() as conn:
        conn.execute(
            "UPDATE foods SET name=?,brand=?,kcal=?,protein=?,carbs=?,fat=?,unit_g=?,unit_name=?,barcode=?,category=? WHERE id=?",
            (*food_payload(request.get_json(force=True)), fid))
    return jsonify(ok=True)


@app.delete("/api/foods/<int:fid>")
def delete_food(fid):
    with get_conn() as conn:
        used = conn.execute("SELECT COUNT(*) FROM preset_items WHERE food_id=?", (fid,)).fetchone()[0]
        if used:
            abort(400, "Este alimento está en algún preset; quítalo de ahí primero")
        old = conn.execute("SELECT photo FROM foods WHERE id=?", (fid,)).fetchone()
        conn.execute("DELETE FROM foods WHERE id=?", (fid,))
        if old and old["photo"]:
            (uploads_dir() / old["photo"]).unlink(missing_ok=True)
    return jsonify(ok=True)


@app.post("/api/foods/<int:fid>/photo")
def upload_photo(fid):
    f = request.files.get("photo")
    if not f or not f.filename:
        abort(400, "No hay archivo")
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        abort(400, "Formato no permitido (jpg, png, webp, gif)")
    data = f.read()
    if len(data) > 8 * 1024 * 1024:
        abort(400, "La foto pesa más de 8 MB")
    with get_conn() as conn:
        old = conn.execute("SELECT photo FROM foods WHERE id=?", (fid,)).fetchone()
        if not old:
            abort(404, "Alimento no encontrado")
        name = save_photo_bytes(data, ext)
        if old["photo"]:
            (uploads_dir() / old["photo"]).unlink(missing_ok=True)
        conn.execute("UPDATE foods SET photo=? WHERE id=?", (name, fid))
    return jsonify(photo=name)


# ------------------------------------------------------- Open Food Facts
@app.get("/api/off/search")
def off_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        abort(400, "Escribe al menos 2 letras")
    try:
        return jsonify(off.search(q))
    except off.OffError as e:
        abort(502, str(e))


@app.get("/api/off/barcode/<code>")
def off_barcode(code):
    """Busca primero en tus alimentos y, si no está, en Open Food Facts."""
    code = re.sub(r"\D", "", code)
    with get_conn() as conn:
        mine = conn.execute("SELECT * FROM foods WHERE barcode=? AND barcode!=''", (code,)).fetchone()
    if mine:
        return jsonify(local=dict(mine), online=None)
    try:
        online = off.by_barcode(code)
    except off.OffError as e:
        abort(502, str(e))
    if not online:
        abort(404, "Producto no encontrado. Puedes crearlo a mano en Alimentos.")
    return jsonify(local=None, online=online)


# ------------------------------------------------------------------ presets
def load_presets(conn, category=None):
    sql = "SELECT * FROM presets "
    params = []
    if category and category not in ("todos", "all", ""):
        sql += "WHERE category=? "
        params.append(category)
    sql += "ORDER BY name COLLATE NOCASE"
    presets = rows(conn.execute(sql, params))
    for p in presets:
        p["items"] = rows(conn.execute(
            "SELECT pi.food_id, pi.grams, f.name, f.brand, f.kcal, f.protein, f.carbs, f.fat, f.photo "
            "FROM preset_items pi JOIN foods f ON f.id=pi.food_id WHERE pi.preset_id=? ORDER BY pi.id",
            (p["id"],)))
        p["totals"] = totals([scale(i, i["grams"]) for i in p["items"]])
    return presets


def save_preset_items(conn, pid, items):
    conn.execute("DELETE FROM preset_items WHERE preset_id=?", (pid,))
    for it in items:
        g = num(it.get("grams"))
        if g > 0:
            conn.execute("INSERT INTO preset_items(preset_id,food_id,grams) VALUES (?,?,?)",
                         (pid, it["food_id"], g))


def preset_name(d):
    name = (d.get("name") or "").strip()
    if not name:
        abort(400, "El nombre es obligatorio")
    return name


@app.get("/api/presets")
def list_presets():
    cat = (request.args.get("category") or "").strip()
    with get_conn() as conn:
        return jsonify(load_presets(conn, category=cat))


@app.post("/api/presets")
def create_preset():
    d = request.get_json(force=True)
    cat = (d.get("category") or "combos").strip()
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO presets(name, meal, category) VALUES (?,?,?)",
                           (preset_name(d), clean_meal(d.get("meal")), cat))
        save_preset_items(conn, cur.lastrowid, d.get("items", []))
        return jsonify(id=cur.lastrowid), 201


@app.post("/api/presets/from-entries")
def preset_from_entries():
    """Convierte entradas ya apuntadas (alimentos, no 'solo kcal') en un preset."""
    d = request.get_json(force=True)
    ids = [int(i) for i in d.get("entry_ids", [])]
    name = preset_name(d)
    cat = (d.get("category") or "combos").strip()
    with get_conn() as conn:
        items = []
        for i in ids:
            e = conn.execute("SELECT * FROM entries WHERE id=? AND kind='food' AND food_id IS NOT NULL", (i,)).fetchone()
            if e:
                items.append({"food_id": e["food_id"], "grams": e["grams"]})
        if not items:
            abort(400, "Solo se pueden guardar como preset entradas con alimento")
        cur = conn.execute("INSERT INTO presets(name, meal, category) VALUES (?,?,?)",
                           (name, clean_meal(d.get("meal")), cat))
        save_preset_items(conn, cur.lastrowid, items)
        return jsonify(id=cur.lastrowid), 201


@app.put("/api/presets/<int:pid>")
def update_preset(pid):
    d = request.get_json(force=True)
    cat = (d.get("category") or "combos").strip()
    with get_conn() as conn:
        conn.execute("UPDATE presets SET name=?, meal=?, category=? WHERE id=?",
                     (preset_name(d), clean_meal(d.get("meal")), cat, pid))
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
        return jsonify(goals=get_goals(conn),
                       profile={k: get_setting(conn, f"profile_{k}") for k in PROFILE_KEYS})


@app.put("/api/settings")
def put_settings():
    d = request.get_json(force=True)
    with get_conn() as conn:
        for k, v in (d.get("goals") or {}).items():
            if k in ("kcal", "protein", "carbs", "fat"):
                set_setting(conn, f"goal_{k}", num(v))
        for k, v in (d.get("profile") or {}).items():
            if k in PROFILE_KEYS:
                set_setting(conn, f"profile_{k}", str(v)[:20])
    return jsonify(ok=True)


# ------------------------------------------------------------- Asistente Gemini (IA)
@app.get("/api/ai/status")
def ai_status():
    with get_conn() as conn:
        key, source = gemini.get_gemini_api_key(conn)
        model, m_source = gemini.get_gemini_model(conn)
        return jsonify(
            configured=bool(key),
            masked=gemini.mask_api_key(key),
            source=source,
            model=model,
            model_source=m_source,
            available_models=gemini.MODELS,
        )


@app.post("/api/ai/key")
def ai_set_key():
    d = request.get_json(force=True) or {}
    key = str(d.get("key", "")).strip()
    with get_conn() as conn:
        if not key:
            conn.execute("DELETE FROM settings WHERE key='gemini_api_key'")
        else:
            set_setting(conn, "gemini_api_key", key)
        k, source = gemini.get_gemini_api_key(conn)
        model, m_source = gemini.get_gemini_model(conn)
        return jsonify(
            ok=True,
            configured=bool(k),
            masked=gemini.mask_api_key(k),
            source=source,
            model=model,
            model_source=m_source,
        )


@app.post("/api/ai/model")
def ai_set_model():
    d = request.get_json(force=True) or {}
    model = str(d.get("model", "")).strip()
    with get_conn() as conn:
        if not model:
            conn.execute("DELETE FROM settings WHERE key='gemini_model'")
        else:
            set_setting(conn, "gemini_model", model)
        m, source = gemini.get_gemini_model(conn)
        return jsonify(ok=True, model=m, source=source)


@app.post("/api/ai/parse")
def ai_parse():
    with get_conn() as conn:
        key, _ = gemini.get_gemini_api_key(conn)
        if not key:
            abort(400, "Configura tu clave de API de Gemini en Ajustes o en el archivo .env")

        model, _ = gemini.get_gemini_model(conn)

        # Catálogo de alimentos para que Gemini pueda emparejar
        foods = rows(conn.execute("SELECT id, name, brand, kcal, protein, carbs, fat, unit_g, unit_name FROM foods ORDER BY name"))

    text = ""
    audio_bytes, audio_mime = None, "audio/webm"
    image_bytes, image_mime = None, "image/jpeg"

    # Soporte para JSON o multipart/form-data
    if request.is_json:
        d = request.get_json() or {}
        text = str(d.get("text", "")).strip()
        if d.get("audio_b64"):
            try:
                audio_bytes = base64.b64decode(d["audio_b64"])
                audio_mime = d.get("audio_mime", "audio/webm")
            except Exception:
                abort(400, "Audio en base64 no válido")
        if d.get("image_b64"):
            try:
                image_bytes = base64.b64decode(d["image_b64"])
                image_mime = d.get("image_mime", "image/jpeg")
            except Exception:
                abort(400, "Imagen en base64 no válida")
    else:
        text = request.form.get("text", "").strip()
        f_audio = request.files.get("audio")
        if f_audio and f_audio.filename:
            audio_bytes = f_audio.read()
            audio_mime = f_audio.mimetype or "audio/webm"
        f_img = request.files.get("image")
        if f_img and f_img.filename:
            image_bytes = f_img.read()
            image_mime = f_img.mimetype or "image/jpeg"

    if not text and not audio_bytes and not image_bytes:
        abort(400, "Indica qué has comido por texto, nota de voz o foto")

    try:
        result = gemini.parse_with_gemini(
            api_key=key,
            text=text,
            audio_bytes=audio_bytes,
            audio_mime=audio_mime,
            image_bytes=image_bytes,
            image_mime=image_mime,
            foods_catalog=foods,
            preferred_model=model,
        )
        return jsonify(result)
    except gemini.GeminiError as e:
        abort(502, str(e))


@app.post("/api/ai/apply")
def ai_apply():
    """Añade los alimentos detectados por Gemini al día especificado."""
    d = request.get_json(force=True) or {}
    day = valid_date(d.get("date") or date.today().isoformat())
    meal = clean_meal(d.get("meal"))
    items = d.get("items", [])
    if not items:
        abort(400, "No hay alimentos para añadir")

    added = 0
    with get_conn() as conn:
        for it in items:
            name = (it.get("name") or "").strip() or "Alimento"
            grams = num(it.get("grams"), None)
            matched_id = it.get("matched_food_id")

            # Si coincide con un alimento existente y tiene gramos, insertamos vinculado
            if matched_id:
                food = conn.execute("SELECT * FROM foods WHERE id=?", (matched_id,)).fetchone()
                if food and grams and grams > 0:
                    insert_food_entry(conn, day, meal, matched_id, grams)
                    added += 1
                    continue

            # Inserción con macros calculadas por Gemini
            conn.execute(
                "INSERT INTO entries(date,time,meal,kind,name,grams,kcal,protein,carbs,fat,food_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (day, datetime.now().strftime("%H:%M"), meal, "food", name, grams,
                 num(it.get("kcal")), num(it.get("protein")), num(it.get("carbs")), num(it.get("fat")), None),
            )
            added += 1

    return jsonify(ok=True, added=added), 201



# ------------------------------------------------------ conectar el móvil
def lan_ips():
    """IPs de este PC en la red local; la de la ruta principal va primero."""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no envía nada, solo elige interfaz
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        ips += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    seen = []
    for ip in ips:
        if ip not in seen and not ip.startswith(("127.", "169.254.")):
            seen.append(ip)
    return seen


def qr_svg(text):
    if qrcode is None:
        return ""
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    buf = io.BytesIO()
    img.save(buf)
    return re.sub(r"^<\?xml[^>]*\?>\s*", "", buf.getvalue().decode())


@app.get("/api/connect")
def connect_info():
    port = request.host.rsplit(":", 1)[-1] if ":" in request.host else "80"
    local_only = os.environ.get("MACROS_LOCAL_ONLY") == "1"
    urls = [] if local_only else [f"http://{ip}:{port}" for ip in lan_ips()]
    with get_conn() as conn:
        pin_set = bool(get_setting(conn, "pin_hash"))
    return jsonify(urls=urls, local_only=local_only, pin_set=pin_set,
                   qr=qr_svg(urls[0]) if urls else "")


# --------------------------------------------------------- copia de seguridad
@app.get("/api/export")
def export_all():
    """Copia completa en JSON (datos + fotos en base64). Sirve para mover la app a otro PC."""
    with get_conn() as conn:
        out = {"app": "calculadora-macros", "version": 1, "exported_at": datetime.now().isoformat(timespec="seconds")}
        for t in EXPORT_TABLES:
            out[t] = rows(conn.execute(f"SELECT * FROM {t}"))
        out["settings"] = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM settings")
                           if r["key"].startswith(("goal_", "profile_"))}
    out["photos"] = {}
    for f in out["foods"]:
        p = uploads_dir() / f["photo"] if f["photo"] else None
        if p and p.is_file():
            out["photos"][f["photo"]] = base64.b64encode(p.read_bytes()).decode()
    resp = Response(json.dumps(out, ensure_ascii=False), mimetype="application/json")
    resp.headers["Content-Disposition"] = f'attachment; filename="macros-backup-{date.today().isoformat()}.json"'
    return resp


@app.get("/api/export.csv")
def export_csv():
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")  # ';' para que Excel en español lo separe bien
    w.writerow(["fecha", "hora", "comida", "nombre", "gramos", "kcal", "proteina", "hidratos", "grasa"])
    with get_conn() as conn:
        for e in conn.execute("SELECT * FROM entries ORDER BY date, time, id"):
            w.writerow([e["date"], e["time"], e["meal"], e["name"], e["grams"] or "",
                        str(e["kcal"]).replace(".", ","), str(e["protein"]).replace(".", ","),
                        str(e["carbs"]).replace(".", ","), str(e["fat"]).replace(".", ",")])
    resp = Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="macros-{date.today().isoformat()}.csv"'
    return resp


@app.get("/api/export/pdf")
def export_pdf():
    """Genera y descarga un informe nutricional completo en PDF con fpdf2."""
    target_date = request.args.get("date") or date.today().isoformat()
    valid_date(target_date)
    try:
        days = max(1, min(int(request.args.get("days", 7)), 365))
    except ValueError:
        days = 7
    with get_conn() as conn:
        pdf_bytes = pdf_report.generate_macro_pdf(conn, target_date=target_date, days_range=days)
    resp = Response(pdf_bytes, mimetype="application/pdf")
    resp.headers["Content-Disposition"] = f'attachment; filename="macros-informe-{target_date}.pdf"'
    return resp


@app.get("/report")
def report_page():
    """Página de informe imprimible con opción directa de guardar como PDF."""
    return send_from_directory(app.static_folder, "report.html")


@app.post("/api/import")
def import_all():
    """Restaura una copia: REEMPLAZA todos los datos actuales."""
    f = request.files.get("file")
    try:
        data = json.load(f.stream) if f else request.get_json(force=True)
    except (ValueError, UnicodeDecodeError):
        abort(400, "El archivo no es una copia válida")
    if not isinstance(data, dict) or data.get("app") != "calculadora-macros":
        abort(400, "El archivo no es una copia de Calculadora de Macros")
    with get_conn() as conn:
        for t in reversed(EXPORT_TABLES):
            conn.execute(f"DELETE FROM {t}")
        for t in EXPORT_TABLES:
            cols = db.table_columns(conn, t)  # lista blanca de columnas
            for r in data.get(t, []):
                use = [c for c in cols if c in r]
                conn.execute(f"INSERT INTO {t}({','.join(use)}) VALUES ({','.join('?' * len(use))})",
                             [r[c] for c in use])
        for k, v in (data.get("settings") or {}).items():
            if k.startswith(("goal_", "profile_")):
                set_setting(conn, k, v)
    uploads_dir().mkdir(parents=True, exist_ok=True)
    for name, b64 in (data.get("photos") or {}).items():
        safe = Path(name).name  # evita rutas tipo ../../
        if Path(safe).suffix.lower() in ALLOWED_EXT:
            (uploads_dir() / safe).write_bytes(base64.b64decode(b64))
    return jsonify(ok=True)


init_db()


# ------------------------------------------------------------------ arranque
def main():
    ap = argparse.ArgumentParser(description="Calculadora de macros")
    ap.add_argument("--port", type=int, default=int(os.environ.get("MACROS_PORT", 5000)))
    ap.add_argument("--local", action="store_true", help="solo accesible desde este PC (no desde el móvil)")
    ap.add_argument("--no-browser", action="store_true", help="no abrir el navegador al arrancar")
    args = ap.parse_args()

    host = "127.0.0.1" if args.local else "0.0.0.0"
    if args.local:
        os.environ["MACROS_LOCAL_ONLY"] = "1"
    url = f"http://localhost:{args.port}"
    print(f"\n  Calculadora de macros\n  En este PC:  {url}")
    if not args.local:
        for ip in lan_ips():
            print(f"  En el móvil: http://{ip}:{args.port}   (misma wifi)")
    print(f"  Datos en:    {db.DB_PATH.parent}\n  Ctrl+C para parar\n")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        app.run(host=host, port=args.port, threaded=True, debug=False)
    except OSError as e:
        raise SystemExit(f"No se pudo abrir el puerto {args.port} ({e}). Prueba: python app.py --port 5001")


if __name__ == "__main__":
    main()
