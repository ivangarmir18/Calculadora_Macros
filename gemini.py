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

# Modelos de Gemini con fallback inteligente (priorizando Gemini 3.8 Flash)
MODELS = [
    "gemini-3.8-flash",
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]


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


def get_gemini_model(conn=None):
    """Obtiene el modelo de Gemini preferido con la siguiente prioridad:
    1. Variable de entorno GEMINI_MODEL (o de .env)
    2. Base de datos SQLite (tabla settings: gemini_model)
    3. 'gemini-3.8-flash' (por defecto)
    """
    model = os.environ.get("GEMINI_MODEL", "").strip()
    if model:
        return model, "env"

    if conn is not None:
        r = conn.execute("SELECT value FROM settings WHERE key='gemini_model'").fetchone()
        if r and r["value"].strip():
            return r["value"].strip(), "db"

    return "gemini-3.8-flash", "default"


def get_models_list(preferred_model=None):
    """Devuelve la lista ordenada de modelos con el preferido al frente."""
    models = list(MODELS)
    if preferred_model and preferred_model.strip():
        m = preferred_model.strip()
        if m in models:
            models.remove(m)
        models.insert(0, m)
    return models


def mask_api_key(key):
    """Devuelve la clave ofuscada para mostrar en la interfaz de forma segura."""
    if not key:
        return ""
    if len(key) <= 8:
        return "••••" + key[-2:]
    return key[:6] + "••••••••" + key[-4:]


class GeminiError(Exception):
    pass


SYSTEM_INSTRUCTION = """Eres un asistente nutricional experto, empático y de máxima precisión.
Tu objetivo es analizar lo que el usuario ha consumido a partir de texto en lenguaje natural, notas de voz grabadas (incluso audios extensos de 1 a 2 minutos) o fotos de platos y etiquetas, desglosando cada ingrediente con sus gramos y macros (kcal, proteínas, carbohidratos, grasas).

DIRECTRICES FUNDAMENTALES:
1. NOTAS DE VOZ EXTENSAS Y DETALLADAS:
   - Escucha e interpreta la TOTALIDAD del audio con paciencia, incluso si el usuario habla de forma coloquial, relajada, con pausas o rectificaciones ("bueno, al final le eché dos latas en vez de una").
   - Transcribe y resume fielmente en el campo "transcription" lo que el usuario dijo o explicó.

2. DESGLOSE DETALLADO DE PLATOS CON MÚLTIPLES INGREDIENTES (Ensaladas, bowls, salteados, guisos, platos combinados):
   - NO agrupes todo en un plato genérico (NUNCA hagas "Ensalada mixta 300 kcal").
   - Identifica y desglosa CADA ingrediente individualmente: base de hojas verdes/lechuga/rúcula/espinacas, tomate, cebolla, pepino, maíz, atún, huevo cocido, pollo, queso (feta, fresco, curado), frutos secos (nueces, pipas), legumbres, fruta, etc.
   - CONDIMENTOS Y ALIÑOS CRÍTICOS: NUNCA olvides incluir el aceite (ej. Aceite de oliva virgen extra / AOVE) si se menciona ("un chorrito", "una cucharada", "le puse aceite", etc.). El aceite tiene un impacto calórico determinante (~9 kcal/g; 1 cucharada o chorrito habitual = 10-15g = 90-135 kcal de grasa pura). Si menciona vinagre balsámico/crema o salsas, inclúyelos con sus calorías correspondientes.

3. ESTIMACIÓN REALISTA DE RACIONES COLOQUIALES (si no se indican gramos exactos):
   - 1 tomate mediano ≈ 130-150g, 1 tomate grande ≈ 180-200g
   - 1/2 cebolla mediana ≈ 50-60g
   - 1 huevo entero ≈ 55-60g
   - 1 lata individual de atún (escurrido) ≈ 60-80g
   - 1 cucharada sopera o chorrito de aceite ≈ 10-15g (90-135 kcal)
   - 1 puñado de nueces / frutos secos ≈ 20-25g
   - 1/2 aguacate ≈ 70-80g
   - 1/2 lata de maíz dulce ≈ 70g
   - 1 ración de lechuga / canónigos / brotes ≈ 60-80g
   - 1 ración de queso feta o fresco ≈ 40-50g
   - 1 manzana o pieza de fruta mediana ≈ 150-180g

4. BASE DE DATOS PERSONAL DEL USUARIO:
   - Si el usuario te proporciona una lista de "ALIMENTOS REGISTRADOS" en su base de datos y alguno coincide claramente (ej. "pechuga de pollo", "atún al natural", "aceite de oliva virgen extra", "huevo"), usa ese alimento, asigna su "matched_food_id" correspondiente y calcula las macros exactas proporcionales a los gramos consumidos.
   - Si no está en su base de datos, estima con rigor nutricional: nombre claro en español, gramos de la porción y macros completas (kcal, protein, carbs, fat).

5. COMIDA DEL DÍA:
   - Deduce la comida más probable ("desayuno", "comida", "merienda", "cena", "otro") según el tipo de alimentos o el contexto.

6. FORMATO DE RESPUESTA:
   Devuelve SIEMPRE y ÚNICAMENTE un objeto JSON válido con esta estructura:
{
  "meal": "desayuno|comida|merienda|cena|otro",
  "summary": "Resumen claro en español de lo consumido (ej. Ensalada completa con atún, huevo y nueces)",
  "transcription": "Resumen textual o transcripción fiel de lo que el usuario explicó en su nota de voz o mensaje",
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
  "notes": "Consejo o aclaración breve opcional sobre las porciones o aliños"
}
"""


def parse_with_gemini(api_key, text="", audio_bytes=None, audio_mime="audio/webm",
                      image_bytes=None, image_mime="image/jpeg", foods_catalog=None,
                      preferred_model=None):
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
            for f in foods_catalog[:80]  # catálogo relevante para prompt
        ]
        catalog_text = "ALIMENTOS REGISTRADOS EN MI BASE DE DATOS:\n" + "\n".join(catalog_lines) + "\n\n"

    user_prompt = catalog_text
    if text:
        user_prompt += f"LO QUE HE COMIDO O DETALLES:\n{text.strip()}\n"
    else:
        user_prompt += "Analiza con detenimiento el contenido multimedia adjunto (audio de voz y/o foto) e indica todos los alimentos, cantidades y macros consumidos.\n"

    parts.append({"text": user_prompt})

    # Normalizar y adjuntar imagen
    if image_bytes:
        clean_img_mime = (image_mime or "image/jpeg").split(";")[0].strip().lower()
        parts.append({
            "inlineData": {
                "mimeType": clean_img_mime,
                "data": base64.b64encode(image_bytes).decode("ascii"),
            }
        })

    # Normalizar y adjuntar audio (compatible con Safari iOS, Chrome Android, WebM, MP4, AAC, WAV, OGG)
    if audio_bytes:
        clean_audio_mime = (audio_mime or "audio/webm").split(";")[0].strip().lower()
        if clean_audio_mime in ("audio/m4a", "audio/x-m4a"):
            clean_audio_mime = "audio/mp4"
        parts.append({
            "inlineData": {
                "mimeType": clean_audio_mime,
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
    models_to_try = get_models_list(preferred_model)
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={urllib.parse.quote(api_key)}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            # Timeout ampliado a 90 segundos para permitir audios de hasta 2 minutos con inferencia completa
            with urllib.request.urlopen(req, timeout=90) as resp:
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
            # Si es un error 404 (modelo no disponible) o 429 (rate limit), probamos con el siguiente modelo del fallback
            if e.code in (404, 429):
                continue
            raise GeminiError(last_error)
        except Exception as e:
            last_error = str(e)
            continue

    raise GeminiError(last_error or "No se pudo conectar con Gemini.")


REPORT_ANALYSIS_INSTRUCTION = """Eres un dietista-nutricionista deportivo y fisiólogo de élite.
Tu misión es redactar un análisis clínico y motivador sobre la evolución de un usuario, correlacionando sus comidas/calorías registradas con sus variaciones de peso corporal a lo largo de los días.

PAUTAS CRÍTICAS:
1. Análisis de correlación: Explica si el déficit calórico real coincide con la variación de peso corporal o si intervienen factores como retención de líquidos, glucógeno, variaciones de sodio o digestiones pesadas.
2. Evalúa si el proceso tiene sentido: Da una conclusión clara y profesional (ej. "El proceso tiene total sentido metabólico", "Ritmo óptimo de pérdida grasa", etc.).
3. Consejos accionables: Aporta 2-3 recomendaciones concisas y personalizadas (ej. reparto de proteína, hidratación, consistencia en días sin registro).
4. Tono: Riguroso, motivador, empático y directo. En español.
5. Formato: Devuelve ÚNICAMENTE un objeto JSON válido con los campos "verdict", "analysis", "tips".
"""


def analyze_process_with_gemini(api_key, context_data, preferred_model=None):
    """Genera un análisis nutricional y de correlación peso-comidas usando Gemini."""
    if not api_key:
        raise GeminiError("No se ha configurado la clave de la API de Gemini.")

    prompt = f"""Analiza la siguiente evolución del usuario durante los últimos {context_data.get('days_range')} días:

DATOS BIOMÉTRICOS DEL USUARIO:
- TDEE (Gasto Energético Total): {context_data.get('tdee')} kcal/día
- Objetivo calórico diario: {context_data.get('goal_kcal')} kcal/día (Déficit planificado: -{context_data.get('planned_deficit')} kcal)
- Proteína objetivo: {context_data.get('goal_p')}g | Carbs: {context_data.get('goal_c')}g | Grasa: {context_data.get('goal_f')}g
- Peso inicial registrado: {context_data.get('weight_start')} kg
- Peso final registrado: {context_data.get('weight_end')} kg
- Variación total de peso: {context_data.get('weight_diff_str')}

REGISTRO Y ADHERENCIA:
- Días con comida registrada: {context_data.get('n_logged')} de {context_data.get('days_range')} días ({context_data.get('adherence_pct')}%)
- Calorías promedio diarias reales: {context_data.get('avg_kcal')} kcal (vs objetivo {context_data.get('goal_kcal')} kcal)
- Déficit promedio diario real vs TDEE: -{context_data.get('avg_deficit')} kcal/día
- Déficit acumulado total del periodo: -{context_data.get('total_deficit')} kcal
- Pérdida estimada teórica de grasa pura (base 7700 kcal/kg): ~ {context_data.get('fat_loss_est_kg')} kg

DETALLE DE DÍAS CLAVE CON COMIDAS Y PESO:
{context_data.get('days_summary')}

Devuelve un JSON con:
{{
  "verdict": "Titular o conclusión breve (1 frase)",
  "analysis": "Párrafo conciso (4-6 líneas) analizando la correlación entre las calorías/macros ingeridas y las variaciones de peso (explicando posibles fluctuaciones de agua/glucógeno vs grasa).",
  "tips": [
    "Consejo práctico 1",
    "Consejo práctico 2",
    "Consejo práctico 3"
  ]
}}
"""

    payload = {
        "systemInstruction": {
            "parts": [{"text": REPORT_ANALYSIS_INSTRUCTION}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.3,
        }
    }

    last_error = None
    models_to_try = get_models_list(preferred_model)
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={urllib.parse.quote(api_key)}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.load(resp)
                candidates = data.get("candidates", [])
                if not candidates:
                    raise GeminiError("Gemini no devolvió respuesta.")
                content_parts = candidates[0].get("content", {}).get("parts", [])
                if not content_parts:
                    raise GeminiError("Respuesta vacía de Gemini.")
                raw_json = content_parts[0].get("text", "")
                raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json.strip())
                raw_json = re.sub(r"\s*```$", "", raw_json.strip())
                return json.loads(raw_json)
        except urllib.error.HTTPError as e:
            if e.code in (404, 429):
                continue
            err_body = e.read().decode("utf-8", errors="ignore")
            try:
                err_json = json.loads(err_body)
                msg = err_json.get("error", {}).get("message", e.reason)
            except Exception:
                msg = e.reason
            last_error = f"Error en {model_name}: {msg}"
            continue
        except Exception as e:
            last_error = str(e)
            continue

    raise GeminiError(last_error or "No se pudo conectar con Gemini para el informe.")



