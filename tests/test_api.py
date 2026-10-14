"""Tests del backend. Ejecutar:  python -m unittest discover -s tests -v

Usan una base de datos temporal; no tocan tu data/ real. Funcionan igual en Windows, macOS y Linux.
"""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402

_tmp = tempfile.TemporaryDirectory()
db.DB_PATH = Path(_tmp.name) / "test.db"
import app as A  # noqa: E402

DAY = "2026-10-14"


def tearDownModule():
    _tmp.cleanup()


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.c = A.app.test_client()
        # base limpia en cada test (init_db vuelve a sembrar alimentos si un test los borró)
        db.init_db()
        with db.get_conn() as conn:
            for t in ["entries", "preset_items", "presets", "weights"]:
                conn.execute(f"DELETE FROM {t}")
            conn.execute("DELETE FROM settings WHERE key IN ('pin_hash','auth_token')")
        self.foods = {f["name"]: f for f in self.c.get("/api/foods").get_json()}
        self.milk = self.foods.get("Leche desnatada") or self.foods["Leche Desnatada / Sin Lactosa Light"]
        self.whey = self.foods.get("Proteína whey (polvo)") or self.foods["Proteína Whey Chocolate"]

    def add(self, grams=200, meal="desayuno", food=None, day=DAY):
        r = self.c.post("/api/entries", json={"date": day, "meal": meal, "food_id": (food or self.milk)["id"], "grams": grams})
        self.assertEqual(r.status_code, 201)

    def day(self, day=DAY):
        return self.c.get(f"/api/day/{day}").get_json()

    # --- núcleo
    def test_entry_macros_and_decimal_comma(self):
        self.add("300,5")
        e = self.day()["entries"][0]
        self.assertAlmostEqual(e["kcal"], 35 * 3.005, places=1)

    def test_quick_entry_and_totals(self):
        self.add(200)
        self.c.post("/api/entries", json={"kind": "quick", "date": DAY, "name": "cumple", "kcal": 500})
        d = self.day()
        self.assertEqual(len(d["entries"]), 2)
        self.assertAlmostEqual(d["totals"]["kcal"], 570, places=1)

    def test_history_not_rewritten_when_food_changes(self):
        self.add(100)
        f = dict(self.milk, kcal=999)
        self.c.put(f"/api/foods/{self.milk['id']}", json=f)
        self.assertEqual(self.day()["entries"][0]["kcal"], 35)
        self.c.put(f"/api/foods/{self.milk['id']}", json=self.milk)

    def test_edit_and_delete_entry(self):
        self.add(100)
        eid = self.day()["entries"][0]["id"]
        self.c.put(f"/api/entries/{eid}", json={"grams": 200})
        self.assertEqual(self.day()["entries"][0]["kcal"], 70)
        self.c.delete(f"/api/entries/{eid}")
        self.assertEqual(self.day()["entries"], [])

    def test_validation(self):
        self.assertEqual(self.c.get("/api/day/xx").status_code, 400)
        r = self.c.post("/api/entries", json={"date": DAY, "food_id": self.milk["id"], "grams": 0})
        self.assertEqual(r.status_code, 400)

    # --- presets
    def test_preset_roundtrip_and_from_entries(self):
        self.add(300)
        self.add(30, food=self.whey)
        ids = [e["id"] for e in self.day()["entries"]]
        r = self.c.post("/api/presets/from-entries", json={"name": "Batido", "entry_ids": ids, "meal": "desayuno"})
        self.assertEqual(r.status_code, 201)
        p = self.c.get("/api/presets").get_json()[0]
        self.assertEqual(len(p["items"]), 2)
        self.assertGreater(p["totals"]["protein"], 30)
        r = self.c.post("/api/entries/preset", json={"date": "2026-10-15", "meal": "desayuno",
                        "items": [{"food_id": i["food_id"], "grams": i["grams"] * 2} for i in p["items"]]})
        self.assertEqual(len(self.day("2026-10-15")["entries"]), 2)
        self.assertEqual(self.c.delete(f"/api/foods/{self.milk['id']}").status_code, 400)  # en uso por preset

    def test_preset_from_quick_only_fails(self):
        self.c.post("/api/entries", json={"kind": "quick", "date": DAY, "kcal": 100})
        eid = self.day()["entries"][0]["id"]
        r = self.c.post("/api/presets/from-entries", json={"name": "x", "entry_ids": [eid]})
        self.assertEqual(r.status_code, 400)

    # --- copiar
    def test_copy_day_and_entry(self):
        self.add(100)
        self.add(50, meal="cena")
        r = self.c.post("/api/entries/copy", json={"from_date": DAY, "to_date": "2026-10-15"})
        self.assertEqual(r.get_json()["copied"], 2)
        eid = self.day()["entries"][0]["id"]
        self.c.post(f"/api/entries/{eid}/copy", json={"date": "2026-10-16", "meal": "cena"})
        self.assertEqual(self.day("2026-10-16")["entries"][0]["meal"], "cena")

    # --- peso
    def test_weights_upsert(self):
        self.c.post("/api/weights", json={"date": DAY, "kg": "80,5"})
        self.c.post("/api/weights", json={"date": DAY, "kg": 80.0})
        w = self.c.get("/api/weights").get_json()
        self.assertEqual(w, [{"date": DAY, "kg": 80.0}])
        self.assertEqual(self.c.post("/api/weights", json={"date": DAY, "kg": 5}).status_code, 400)
        self.c.delete(f"/api/weights/{DAY}")
        self.assertEqual(self.c.get("/api/weights").get_json(), [])

    # --- ajustes y PIN
    def test_settings(self):
        self.c.put("/api/settings", json={"goals": {"kcal": 2500}, "profile": {"age": "30", "evil": "x"}})
        s = self.c.get("/api/settings").get_json()
        self.assertEqual(s["goals"]["kcal"], 2500)
        self.assertEqual(s["profile"]["age"], "30")
        self.c.put("/api/settings", json={"goals": {"kcal": 2200}})

    def test_pin_protects_api(self):
        self.assertEqual(self.c.get("/api/foods").status_code, 200)
        r = self.c.post("/api/auth/pin", json={"pin": "1234"})
        self.assertTrue(r.get_json()["pin_set"])
        other = A.app.test_client()  # otro dispositivo sin cookie
        self.assertEqual(other.get("/api/foods").status_code, 401)
        resp = other.get("/")
        self.assertEqual(resp.status_code, 200)  # la pantalla de login sí carga
        resp.close()
        self.assertEqual(other.post("/api/auth/login", json={"pin": "0000"}).status_code, 401)
        self.assertEqual(other.post("/api/auth/login", json={"pin": "1234"}).status_code, 200)
        self.assertEqual(other.get("/api/foods").status_code, 200)
        self.assertEqual(self.c.post("/api/auth/pin", json={"pin": "", "current": "bad"}).status_code, 401)
        self.assertFalse(self.c.post("/api/auth/pin", json={"pin": "", "current": "1234"}).get_json()["pin_set"])

    # --- copia de seguridad
    def test_export_import_roundtrip_with_photo(self):
        self.add(100)
        self.c.post("/api/weights", json={"date": DAY, "kg": 75})
        photo = A.save_photo_bytes(b"\x89PNGfake", ".png")
        self.c.put(f"/api/foods/{self.milk['id']}", json=self.milk)
        with db.get_conn() as conn:
            conn.execute("UPDATE foods SET photo=? WHERE id=?", (photo, self.milk["id"]))
        backup = self.c.get("/api/export").data
        (A.uploads_dir() / photo).unlink()
        self.c.delete(f"/api/entries/{self.day()['entries'][0]['id']}")
        r = self.c.post("/api/import", data={"file": (io.BytesIO(backup), "b.json")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.day()["entries"]), 1)
        self.assertTrue((A.uploads_dir() / photo).is_file())
        self.assertEqual(self.c.get("/api/weights").get_json()[0]["kg"], 75)

    def test_import_rejects_garbage_and_path_traversal(self):
        r = self.c.post("/api/import", data={"file": (io.BytesIO(b"nope"), "b.json")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        evil = json.dumps({"app": "calculadora-macros", "photos": {"../../evil.png": "AAAA"}}).encode()
        self.c.post("/api/import", data={"file": (io.BytesIO(evil), "b.json")}, content_type="multipart/form-data")
        self.assertFalse((A.uploads_dir().parent.parent / "evil.png").exists())
        self.assertTrue((A.uploads_dir() / "evil.png").exists())  # se guarda solo el nombre, dentro de uploads

    def test_csv_export(self):
        self.add(100)
        r = self.c.get("/api/export.csv")
        self.assertIn(self.milk["name"], r.data.decode("utf-8-sig"))

    def test_pdf_export(self):
        self.add(100)
        r7 = self.c.get(f"/api/export/pdf?date={DAY}&days=7")
        self.assertEqual(r7.status_code, 200)
        self.assertEqual(r7.mimetype, "application/pdf")
        self.assertTrue(r7.data.startswith(b"%PDF"))

        r30 = self.c.get(f"/api/export/pdf?date={DAY}&days=30")
        self.assertEqual(r30.status_code, 200)
        self.assertEqual(r30.mimetype, "application/pdf")
        self.assertTrue(r30.data.startswith(b"%PDF"))
        self.assertIn("informe_proceso_30dias", r30.headers.get("Content-Disposition", ""))

    # --- móvil / QR / OFF
    def test_connect_info(self):
        d = self.c.get("/api/connect").get_json()
        self.assertIn("urls", d)
        if A.qrcode and d["urls"]:
            self.assertTrue(d["qr"].startswith("<svg"))

    def test_off_normalize(self):
        import off
        p = off.normalize({"product_name": "Galleta", "brands": "Marca, Otra", "code": "123",
                           "nutriments": {"energy_100g": 2000, "proteins_100g": 6, "carbohydrates_100g": 70, "fat_100g": 15}})
        self.assertEqual(p["brand"], "Marca")
        self.assertAlmostEqual(p["kcal"], 478, delta=1)
        self.assertIsNone(off.normalize({"product_name": "Vacío", "nutriments": {}}))
        self.assertIsNone(off.download_image("http://evil.example.com/a.jpg"))

    def test_barcode_local_lookup(self):
        self.c.put(f"/api/foods/{self.whey['id']}", json=dict(self.whey, barcode="8412345678905"))
        d = self.c.get("/api/off/barcode/8412345678905").get_json()
        self.assertEqual(d["local"]["name"], self.whey["name"])
        self.c.put(f"/api/foods/{self.whey['id']}", json=dict(self.whey, barcode=""))

    def test_history_average_only_logged_days(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM entries")
        from datetime import date as D
        self.add(100, day=D.today().isoformat())
        h = self.c.get("/api/history?days=30").get_json()
        self.assertEqual(h["logged_days"], 1)
        self.assertEqual(h["average"]["kcal"], 35)

    # --- Gemini IA
    def test_gemini_key_management_and_masking(self):
        import gemini
        self.assertEqual(gemini.mask_api_key("AIzaSyB1234567890XYZ"), "AIzaSy••••••••0XYZ")
        self.assertEqual(gemini.mask_api_key("short"), "••••rt")

        # Estado inicial (sin clave, modelo por defecto gemini-3.8-flash)
        st = self.c.get("/api/ai/status").get_json()
        self.assertIn("configured", st)
        self.assertEqual(st["model"], "gemini-3.8-flash")
        self.assertIn("gemini-3.8-flash", st["available_models"])

        # Guardar clave por API
        r = self.c.post("/api/ai/key", json={"key": "AIzaSyTestKey123456"}).get_json()
        self.assertTrue(r["ok"])
        self.assertTrue(r["configured"])
        self.assertTrue(r["masked"].startswith("AIzaSy"))

        st2 = self.c.get("/api/ai/status").get_json()
        self.assertTrue(st2["configured"])
        self.assertEqual(st2["source"], "db")

        # Cambiar modelo por API
        rm = self.c.post("/api/ai/model", json={"model": "gemini-3.8-flash"}).get_json()
        self.assertTrue(rm["ok"])
        self.assertEqual(rm["model"], "gemini-3.8-flash")

        # Eliminar clave
        r_del = self.c.post("/api/ai/key", json={"key": ""}).get_json()
        self.assertFalse(r_del["configured"])

    def test_gemini_parse_missing_key(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM settings WHERE key='gemini_api_key'")
        import os
        old_env = os.environ.pop("GEMINI_API_KEY", None)
        try:
            r = self.c.post("/api/ai/parse", json={"text": "2 huevos"})
            self.assertEqual(r.status_code, 400)
            self.assertIn("Configura tu clave", r.get_json()["error"])
        finally:
            if old_env:
                os.environ["GEMINI_API_KEY"] = old_env

    def test_gemini_apply_entries(self):
        # 1 item con match en base de datos + 1 item con estimación libre
        payload = {
            "date": DAY,
            "meal": "comida",
            "items": [
                {
                    "name": self.milk["name"],
                    "grams": 250,
                    "matched_food_id": self.milk["id"]
                },
                {
                    "name": "Arroz con verduras",
                    "grams": 200,
                    "kcal": 310.5,
                    "protein": 6.2,
                    "carbs": 58.0,
                    "fat": 5.1,
                    "matched_food_id": None
                }
            ]
        }
        r = self.c.post("/api/ai/apply", json=payload)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["added"], 2)

        d = self.day()
        self.assertEqual(len(d["entries"]), 2)
        milk_entry = next(e for e in d["entries"] if "Leche" in e["name"])
        self.assertEqual(milk_entry["grams"], 250)
        self.assertAlmostEqual(milk_entry["kcal"], 35 * 2.5, places=1)

        custom_entry = next(e for e in d["entries"] if "Arroz" in e["name"])
        self.assertEqual(custom_entry["kcal"], 310.5)
        self.assertEqual(custom_entry["protein"], 6.2)

    def test_gemini_parse_voice_audio(self):
        """Simula una nota de voz explicando una ensalada con muchos ingredientes."""
        import base64
        from unittest.mock import patch

        # Configurar clave simulada
        self.c.post("/api/ai/key", json={"key": "AIzaSyFakeKeyForTest12345"})

        fake_salad_response = {
            "meal": "comida",
            "summary": "Ensalada completa con atún, huevo, tomate y aliño",
            "transcription": "Me he preparado una ensalada con canónigos, un tomate grande, una lata de atún, un huevo cocido, unas nueces y un chorro de aceite de oliva virgen extra.",
            "items": [
                {"name": "Canónigos y hojas verdes", "grams": 70, "kcal": 15.0, "protein": 1.5, "carbs": 1.0, "fat": 0.3, "matched_food_id": None},
                {"name": "Tomate", "grams": 160, "kcal": 28.8, "protein": 1.4, "carbs": 6.2, "fat": 0.3, "matched_food_id": None},
                {"name": "Atún al natural", "grams": 80, "kcal": 88.0, "protein": 20.0, "carbs": 0.0, "fat": 0.8, "matched_food_id": None},
                {"name": "Huevo cocido", "grams": 60, "kcal": 93.0, "protein": 7.8, "carbs": 0.7, "fat": 6.5, "matched_food_id": None},
                {"name": "Nueces", "grams": 20, "kcal": 130.8, "protein": 3.0, "carbs": 2.7, "fat": 13.0, "matched_food_id": None},
                {"name": "Aceite de oliva virgen extra", "grams": 12, "kcal": 106.1, "protein": 0.0, "carbs": 0.0, "fat": 11.9, "matched_food_id": None},
            ],
            "total_kcal": 461.7,
            "total_protein": 33.7,
            "total_carbs": 10.6,
            "total_fat": 32.8,
            "notes": "Excelente distribución de macros. El aceite aporta la mayor parte de las grasas saludables."
        }

        fake_audio_bytes = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00fake_opus_audio_data_stream"
        audio_b64 = base64.b64encode(fake_audio_bytes).decode("ascii")

        with patch("gemini.parse_with_gemini", return_value=fake_salad_response) as mock_gemini:
            r = self.c.post("/api/ai/parse", json={
                "audio_b64": audio_b64,
                "audio_mime": "audio/webm;codecs=opus",
                "text": ""
            })
            self.assertEqual(r.status_code, 200)
            data = r.get_json()
            self.assertEqual(data["meal"], "comida")
            self.assertIn("transcription", data)
            self.assertIn("canónigos", data["transcription"])
            self.assertEqual(len(data["items"]), 6)
            self.assertAlmostEqual(data["total_kcal"], 461.7, places=1)

            # Verificar que mock_gemini fue llamado con los bytes y el mime
            mock_gemini.assert_called_once()
            args, kwargs = mock_gemini.call_args
            self.assertEqual(kwargs["audio_bytes"], fake_audio_bytes)
            self.assertEqual(kwargs["audio_mime"], "audio/webm;codecs=opus")


if __name__ == "__main__":
    unittest.main()

