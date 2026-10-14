"""Capa de base de datos SQLite (sin ORM, sin dependencias extra)."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# Carpeta de datos configurable (MACROS_DATA_DIR) para poder moverla, p. ej. a un disco compartido.
DATA_DIR = Path(os.environ.get("MACROS_DATA_DIR") or Path(__file__).resolve().parent / "data")
DB_PATH = DATA_DIR / "macros.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS foods (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    brand     TEXT DEFAULT '',
    kcal      REAL NOT NULL DEFAULT 0,   -- por 100 g/ml
    protein   REAL NOT NULL DEFAULT 0,
    carbs     REAL NOT NULL DEFAULT 0,
    fat       REAL NOT NULL DEFAULT 0,
    unit_g    REAL,                       -- peso de 1 unidad (ej. huevo = 60 g), opcional
    unit_name TEXT DEFAULT '',            -- "huevo", "scoop"...
    photo     TEXT DEFAULT '',            -- nombre de fichero en data/uploads
    barcode   TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS presets (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    meal TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS preset_items (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    preset_id INTEGER NOT NULL REFERENCES presets(id) ON DELETE CASCADE,
    food_id   INTEGER NOT NULL REFERENCES foods(id) ON DELETE CASCADE,
    grams     REAL NOT NULL
);

-- Cada entrada guarda una "foto" de las macros en el momento de comerla,
-- así editar un alimento después no cambia el histórico.
CREATE TABLE IF NOT EXISTS entries (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    date    TEXT NOT NULL,               -- YYYY-MM-DD
    time    TEXT DEFAULT '',             -- HH:MM
    meal    TEXT DEFAULT 'otro',         -- desayuno/comida/merienda/cena/otro
    kind    TEXT DEFAULT 'food',         -- food | quick
    name    TEXT NOT NULL,
    grams   REAL,
    kcal    REAL NOT NULL DEFAULT 0,
    protein REAL NOT NULL DEFAULT 0,
    carbs   REAL NOT NULL DEFAULT 0,
    fat     REAL NOT NULL DEFAULT 0,
    food_id INTEGER REFERENCES foods(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(date);

CREATE TABLE IF NOT EXISTS weights (
    date TEXT PRIMARY KEY,               -- YYYY-MM-DD
    kg   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {"goal_kcal": "2200", "goal_protein": "150", "goal_carbs": "230", "goal_fat": "70"}

# Valores aproximados por 100 g, solo como punto de partida. Edítalos con tus etiquetas reales.
SEED_FOODS = [
    # name, brand, kcal, protein, carbs, fat, unit_g, unit_name
    ("Leche desnatada", "", 35, 3.5, 4.8, 0.1, None, ""),
    ("Leche semidesnatada", "", 46, 3.4, 4.8, 1.6, None, ""),
    ("Proteína whey (polvo)", "", 380, 78, 6, 6, 30, "scoop"),
    ("Cereales de desayuno", "", 375, 8, 78, 2, None, ""),
    ("Avena en copos", "", 370, 13, 60, 7, None, ""),
    ("Huevo", "", 143, 12.5, 0.7, 10, 60, "huevo"),
    ("Pechuga de pollo", "", 110, 23, 0, 1.5, None, ""),
    ("Arroz blanco (crudo)", "", 355, 7, 78, 0.8, None, ""),
    ("Pasta (cruda)", "", 360, 12.5, 72, 1.5, None, ""),
    ("Pan integral", "", 245, 9, 42, 3.5, 30, "rebanada"),
    ("Plátano", "", 90, 1, 21, 0.3, 120, "plátano"),
    ("Manzana", "", 52, 0.3, 12, 0.2, 180, "manzana"),
    ("Yogur natural", "", 60, 4, 5, 3, 125, "yogur"),
    ("Aceite de oliva", "", 884, 0, 0, 100, 10, "cucharada"),
    ("Queso fresco batido 0%", "", 46, 8, 3.5, 0.2, None, ""),
]


@contextmanager
def get_conn():
    """Abre una conexión, hace commit al salir y SIEMPRE la cierra
    (en Windows una conexión abierta bloquea el fichero .db)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def table_columns(conn, table):
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Migración para bases creadas con la primera versión
        if "barcode" not in table_columns(conn, "foods"):
            conn.execute("ALTER TABLE foods ADD COLUMN barcode TEXT DEFAULT ''")
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
        if conn.execute("SELECT COUNT(*) FROM foods").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO foods(name, brand, kcal, protein, carbs, fat, unit_g, unit_name) "
                "VALUES (?,?,?,?,?,?,?,?)",
                SEED_FOODS,
            )
