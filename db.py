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
    category  TEXT DEFAULT 'otros',       -- desayuno/lacteos/carnes_pescados/hidratos_panes/otros
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS presets (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    meal     TEXT DEFAULT '',
    category TEXT DEFAULT 'combos'
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
    kind    TEXT DEFAULT 'food',         -- food | quick | combo
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

# Objetivos base y datos biométricos por defecto
DEFAULT_SETTINGS = {
    "goal_kcal": "2150",
    "goal_protein": "185",
    "goal_carbs": "200",
    "goal_fat": "65",
    "profile_tdee": "3350",
    "profile_weight": "119",
    "profile_lbm": "85.5",
}

# 21 Alimentos individuales base con macros exactas (por 100g / 100ml o por unidad)
# Formato: (name, brand, kcal, protein, carbs, fat, unit_g, unit_name, category)
SEED_FOODS = [
    # Desayuno y Cereales
    ("Cereales Chocolate (9g fibra / 12g azúcar)", "", 385.0, 11.0, 73.0, 3.5, None, "", "desayuno"),
    ("Cornflakes / Cereales Integrales Normales", "", 375.0, 8.0, 80.0, 1.5, None, "", "desayuno"),
    ("Proteína Whey Chocolate", "", 382.9, 77.1, 5.7, 5.7, 35.0, "cacito", "desayuno"),  # 1 cacito = 35g (134 kcal | 27P | 2C | 2G)
    ("Leche Semidesnatada", "", 47.0, 3.2, 4.8, 1.6, None, "", "desayuno"),
    ("Leche Desnatada / Sin Lactosa Light", "", 35.0, 3.3, 4.8, 0.3, None, "", "desayuno"),
    ("Café Instantáneo", "", 0.0, 0.0, 0.0, 0.0, 2.0, "cucharadita", "desayuno"),        # 1 cdta = 2g (0 kcal | 60mg cafeína)

    # Lácteos Alta Saciedad y Fruta
    ("Yogur Griego Light", "", 58.0, 6.0, 4.5, 1.8, None, "", "lacteos"),
    ("Queso Fresco Batido 0%", "", 52.0, 8.5, 4.0, 0.2, None, "", "lacteos"),
    ("Yogur Proteico / Skyr", "", 57.6, 10.0, 4.0, 0.16, 125.0, "envase", "lacteos"),    # 1 envase = 125g (72 kcal | 12.5P | 5C | 0.2G)
    ("Arándanos / Frutos Rojos", "", 57.0, 0.7, 14.0, 0.3, None, "", "lacteos"),
    ("Fruta Media (Manzana / Plátano / Pera)", "", 56.7, 0.53, 13.33, 0.2, 150.0, "unidad", "lacteos"), # 1 unidad = 150g (85 kcal | 0.8P | 20C | 0.3G)

    # Platos Principales, Proteínas y Panes
    ("Gyozas Pollo/Verdura", "", 162.0, 11.0, 21.5, 3.5, None, "", "carnes_pescados"),
    ("Pechuga de Pollo / Pavo", "", 106.0, 23.0, 0.0, 1.5, None, "", "carnes_pescados"),
    ("Merluza / Pescado Blanco", "", 82.0, 17.0, 0.0, 1.5, None, "", "carnes_pescados"),
    ("Salmón / Pescado Azul", "", 208.0, 20.0, 0.0, 13.0, None, "", "carnes_pescados"),
    ("Lomo Embuchado / Jamón Serrano Magro", "", 200.0, 34.0, 1.0, 6.5, None, "", "carnes_pescados"),
    ("Huevo Entero L", "", 143.3, 12.5, 0.83, 10.0, 60.0, "huevo L", "carnes_pescados"),  # 1 ud = 60g (86 kcal | 7.5P | 0.5C | 6G)
    ("Claras de Huevo Líquidas", "", 49.0, 11.0, 0.7, 0.2, None, "", "carnes_pescados"),
    ("Tortitas de Centeno (tipo Wasa)", "", 340.0, 10.0, 65.0, 2.0, 10.0, "tortita", "hidratos_panes"), # 1 ud = 10g (34 kcal | 1P | 6.5C | 0.2G)
    ("Verduras Fibrosas / Ensalada / Brócoli", "", 28.0, 2.0, 4.5, 0.3, None, "", "carnes_pescados"),
    ("Aceite de Oliva Virgen Extra (Spray / Cucharadita)", "", 900.0, 0.0, 0.0, 100.0, 5.0, "cucharadita", "otros"), # 1 cdta/spray = 5g (45 kcal | 5G)
]

# 6 Platos rápidos y combos repetidos (1-Click Meals)
SEED_COMBOS = [
    {
        "name": "Combo Desayuno 1: Batido Moca + Bol Cereales Choco (700 kcal)",
        "meal": "desayuno",
        "category": "combos",
        "items": [
            ("Proteína Whey Chocolate", 35.0),
            ("Café Instantáneo", 2.0),
            ("Leche Semidesnatada", 300.0),
            ("Cereales Chocolate (9g fibra / 12g azúcar)", 100.0),
        ],
    },
    {
        "name": "Combo Desayuno 2: Batido Moca + Mix Cornflakes e Integrales",
        "meal": "desayuno",
        "category": "combos",
        "items": [
            ("Proteína Whey Chocolate", 35.0),
            ("Café Instantáneo", 2.0),
            ("Leche Semidesnatada", 300.0),
            ("Cornflakes / Cereales Integrales Normales", 50.0),
            ("Cereales Chocolate (9g fibra / 12g azúcar)", 50.0),
        ],
    },
    {
        "name": "Combo Postre / Cena Saciedad: Mega Bol Queso Fresco Batido + Griego Light",
        "meal": "cena",
        "category": "combos",
        "items": [
            ("Queso Fresco Batido 0%", 250.0),
            ("Yogur Griego Light", 150.0),
            ("Arándanos / Frutos Rojos", 80.0),
            ("Cereales Chocolate (9g fibra / 12g azúcar)", 20.0),
        ],
    },
    {
        "name": "Combo Comida Rápida: Plato de Gyozas + Pechuga de Pollo",
        "meal": "comida",
        "category": "combos",
        "items": [
            ("Gyozas Pollo/Verdura", 200.0),
            ("Pechuga de Pollo / Pavo", 200.0),
            ("Aceite de Oliva Virgen Extra (Spray / Cucharadita)", 5.0),
        ],
    },
    {
        "name": "Combo Cena Ligera: Merluza con Tortas de Centeno y Verdura",
        "meal": "cena",
        "category": "combos",
        "items": [
            ("Merluza / Pescado Blanco", 300.0),
            ("Tortitas de Centeno (tipo Wasa)", 40.0),
            ("Verduras Fibrosas / Ensalada / Brócoli", 200.0),
            ("Aceite de Oliva Virgen Extra (Spray / Cucharadita)", 5.0),
        ],
    },
    {
        "name": "Combo Cena Huevos: Revuelto Proteico + Centeno",
        "meal": "cena",
        "category": "combos",
        "items": [
            ("Huevo Entero L", 120.0),
            ("Claras de Huevo Líquidas", 150.0),
            ("Lomo Embuchado / Jamón Serrano Magro", 50.0),
            ("Tortitas de Centeno (tipo Wasa)", 40.0),
        ],
    },
]


_in_init = False


@contextmanager
def get_conn():
    """Abre una conexión, hace commit al salir y SIEMPRE la cierra
    (en Windows una conexión abierta bloquea el fichero .db)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    before = conn.total_changes
    changed = False
    try:
        yield conn
        conn.commit()
        changed = conn.total_changes > before
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    if changed and not _in_init and "test.db" not in str(DB_PATH):
        try:
            import github_sync
            github_sync.schedule_push()
        except Exception:
            pass


def table_columns(conn, table):
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def seed_combos(conn):
    """Siembra los 6 combos predefinidos si no existen en presets."""
    for combo in SEED_COMBOS:
        exist = conn.execute("SELECT id FROM presets WHERE name=?", (combo["name"],)).fetchone()
        if not exist:
            cur = conn.execute(
                "INSERT INTO presets(name, meal, category) VALUES (?, ?, ?)",
                (combo["name"], combo["meal"], combo.get("category", "combos")),
            )
            pid = cur.lastrowid
            for food_name, grams in combo["items"]:
                f = conn.execute("SELECT id FROM foods WHERE name=?", (food_name,)).fetchone()
                if f:
                    conn.execute(
                        "INSERT INTO preset_items(preset_id, food_id, grams) VALUES (?, ?, ?)",
                        (pid, f["id"], grams),
                    )


def init_db():
    global _in_init
    _in_init = True
    try:
        # Al arrancar (ej. en Render tras despertar o en PC), traer la última DB de GitHub si existe
        if "test.db" not in str(DB_PATH):
            try:
                import github_sync
                github_sync.pull_from_github(force=False)
            except Exception:
                pass

        with get_conn() as conn:
            conn.executescript(SCHEMA)

            # Migraciones para bases ya existentes
            food_cols = table_columns(conn, "foods")
            if "barcode" not in food_cols:
                conn.execute("ALTER TABLE foods ADD COLUMN barcode TEXT DEFAULT ''")
            if "category" not in food_cols:
                conn.execute("ALTER TABLE foods ADD COLUMN category TEXT DEFAULT 'otros'")

            preset_cols = table_columns(conn, "presets")
            if "category" not in preset_cols:
                conn.execute("ALTER TABLE presets ADD COLUMN category TEXT DEFAULT 'combos'")

            # Actualiza o crea ajustes por defecto
            for k, v in DEFAULT_SETTINGS.items():
                conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))

            # Sembrar alimentos base solo si no se han sembrado antes (o si la tabla está vacía)
            foods_count = conn.execute("SELECT COUNT(*) FROM foods").fetchone()[0]
            already_seeded_foods = conn.execute("SELECT value FROM settings WHERE key='seeded_foods_v1'").fetchone()
            if foods_count == 0 or not already_seeded_foods:
                for f in SEED_FOODS:
                    row = conn.execute("SELECT id FROM foods WHERE name=?", (f[0],)).fetchone()
                    if not row:
                        conn.execute(
                            "INSERT INTO foods(name, brand, kcal, protein, carbs, fat, unit_g, unit_name, category) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            f,
                        )
                conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('seeded_foods_v1', '1')")

            # Sembrar combos predefinidos solo la primera vez para permitir editarlos o borrarlos libremente
            already_seeded_combos = conn.execute("SELECT value FROM settings WHERE key='seeded_combos_v1'").fetchone()
            if not already_seeded_combos:
                seed_combos(conn)
                conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('seeded_combos_v1', '1')")
    finally:
        _in_init = False
