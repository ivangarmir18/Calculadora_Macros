"""Módulo de integración con Google Gemini API.

Permite procesar texto, notas de voz o fotos de comida para extraer alimentos, gramos y macros.
No requiere librerías externas pesadas (usa urllib estándar).
"""
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Modelos recomendados de Gemini con fallback
MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]


def load_env_file():
    """Carga variables desde .env en BASE_DIR si existe."""
    env_path = BASE_DIR / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("\"'")
            if k and k not in os.environ:
                os.environ[k] = v


# Cargar variables de .env al importar
load_env_file()


def get_gemini_api_key(conn=None):
    """Obtiene la clave de Gemini con la siguiente prioridad:
    1. Variable de entorno GEMINI_API_KEY (o de .env)
    2. Base de datos SQLite (tabla settings: gemini_api_key)
    """
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key, "env"

    if conn is not None:
        r = conn.execute("SELECT value FROM settings WHERE key='gemini_api_key'").fetchone()
        if r and r["value"].strip():
            return r["value"].strip(), "db"

    return "", "none"


def mask_api_key(key):
    """Devuelve la clave ofuscada para mostrar en la interfaz de forma segura."""
    if not key:
        return ""
    if len(key) <= 8:
        return "••••" + key[-2:]
    return key[:6] + "••••••••" + key[-4:]


class GeminiError(Exception):
    pass


SYSTEM_INSTRUCTION = """Eres un asistente nutricional experto y preciso.
Tu objetivo es analizar lo que el usuario ha comido a partir de texto en lenguaje natural, audio de voz o fotos de platos/etiquetas, y desglosarlo en alimentos con sus macros y calorías estimadas.

Reglas:
1. Identifica cada alimento o componente por separado.
2. Si el usuario te proporciona una lista de "alimentos registrados" en su base de datos y alguno de los alimentos consumidos coincide claramente (ej. "leche desnatada", "pechuga de pollo", "arroz"), utiliza ese alimento, asigna su "matched_food_id" correspondiente y calcula las macros proporcionales a los gramos o unidades consumidos.
3. Si un alimento NO está en su base de datos, estima de forma realista: nombre, gramos aproximados de la ración y sus macros (kcal, protein, carbs, fat por esa ración).
4. Si el usuario solo menciona algo genérico como "fui a un cumple y comí algo de picoteo", desglósalo en los componentes aproximados o en un ítem representativo con calorías realistas.
5. Intenta sugerir la comida del día más probable ("desayuno", "comida", "merienda", "cena", "otro") según el contexto o alimentos.
6. Devuelve SIEMPRE y ÚNICAMENTE un objeto JSON válido con este formato:
{
  "meal": "desayuno|comida|merienda|cena|otro",
  "summary": "Breve resumen en español de lo detectado",
  "items": [
    {
      "name": "Nombre claro del alimento",
      "grams": 150,
      "kcal": 210.0,
      "protein": 22.0,
      "carbs": 5.0,
      "fat": 11.0,
      "matched_food_id": 5 // o null si no está en la base de datos
    }
  ],
  "total_kcal": 210.0,
  "total_protein": 22.0,
  "total_carbs": 5.0,
  "total_fat": 11.0,
  "notes": "Consejo o aclaración breve opcional"
}
"""


def parse_with_gemini(api_key, text="", audio_bytes=None, audio_mime="audio/webm",
                      image_bytes=None, image_mime="image/jpeg", foods_catalog=None):
    """Llama a la API de Gemini con texto, audio y/o imagen, y devuelve la estructura de alimentos."""
    if not api_key:
        raise GeminiError("No se ha configurado la clave de la API de Gemini.")

    parts = []

    # Añadir contexto de alimentos si existe
    catalog_text = ""
    if foods_catalog:
        catalog_lines = [
            f"- ID {f['id']}: {f['name']} ({f.get('brand') or ''}) -> 100g = {f['kcal']}kcal, P:{f['protein']}g, C:{f['carbs']}g, F:{f['fat']}g"
            + (f" [1 {f['unit_name']} = {f['unit_g']}g]" if f.get('unit_g') else "")
            for f in foods_catalog[:60]  # límite razonable para prompt
        ]
        catalog_text = "ALIMENTOS REGISTRADOS EN MI BASE DE DATOS:\n" + "\n".join(catalog_lines) + "\n\n"

    user_prompt = catalog_text
    if text:
        user_prompt += f"LO QUE HE COMIDO:\n{text.strip()}\n"
    else:
        user_prompt += "Analiza el contenido multimedia adjunto (audio o foto) e indica los alimentos y macros consumidos.\n"

    parts.append({"text": user_prompt})

    # Imagen adjunta
    if image_bytes:
        parts.append({
            "inlineData": {
                "mimeType": image_mime,
                "data": base64.b64encode(image_bytes).decode("ascii"),
            }
        })

    # Audio adjunto
    if audio_bytes:
        parts.append({
            "inlineData": {
                "mimeType": audio_mime,
                "data": base64.b64encode(audio_bytes).decode("ascii"),
            }
        })

    payload = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_INSTRUCTION}]
        },
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        }
    }

    last_error = None
    for model_name in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={urllib.parse.quote(api_key)}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
                candidates = data.get("candidates", [])
                if not candidates:
                    raise GeminiError("Gemini no devolvió ninguna respuesta.")
                content_parts = candidates[0].get("content", {}).get("parts", [])
                if not content_parts:
                    raise GeminiError("Respuesta vacía de Gemini.")
                raw_json = content_parts[0].get("text", "")
                # Limpiar posibles bloques ```json ```
                raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json.strip())
                raw_json = re.sub(r"\s*```$", "", raw_json.strip())
                result = json.loads(raw_json)
                return result
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            try:
                err_json = json.loads(err_body)
                msg = err_json.get("error", {}).get("message", e.reason)
            except Exception:
                msg = e.reason
            last_error = f"Error en {model_name}: {msg}"
            # Si es un error 404 (modelo no disponible), probamos con el siguiente modelo del fallback
            if e.code == 404:
                continue
            raise GeminiError(last_error)
        except Exception as e:
            last_error = str(e)
            continue

    raise GeminiError(last_error or "No se pudo conectar con Gemini.")

