"""Cliente mínimo de Open Food Facts (base de datos abierta de productos, sin API key)."""
import json
import re
import urllib.parse
import urllib.request

UA = "CalculadoraMacros/1.0 (app personal; github.com/ivangarmir18/Calculadora_Macros)"
FIELDS = "code,product_name,product_name_es,brands,nutriments,image_front_small_url,image_front_url"


class OffError(Exception):
    pass


def _get_json(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception as e:  # sin internet, timeout, JSON roto...
        raise OffError("No se pudo conectar con Open Food Facts") from e


def _n(nutr, key):
    v = nutr.get(key)
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def normalize(p):
    """Producto OFF -> alimento de la app (valores por 100 g). None si no tiene datos nutricionales."""
    nu = p.get("nutriments") or {}
    kcal = _n(nu, "energy-kcal_100g")
    if kcal is None:  # algunos productos solo traen kJ
        kj = _n(nu, "energy_100g")
        kcal = round(kj / 4.184, 1) if kj is not None else None
    protein, carbs, fat = _n(nu, "proteins_100g"), _n(nu, "carbohydrates_100g"), _n(nu, "fat_100g")
    name = (p.get("product_name_es") or p.get("product_name") or "").strip()
    if not name or (kcal is None and protein is None and carbs is None and fat is None):
        return None
    if kcal is None:
        kcal = round((protein or 0) * 4 + (carbs or 0) * 4 + (fat or 0) * 9, 1)
    return {
        "name": name,
        "brand": (p.get("brands") or "").split(",")[0].strip(),
        "kcal": kcal, "protein": protein or 0, "carbs": carbs or 0, "fat": fat or 0,
        "barcode": p.get("code") or "",
        "photo_url": p.get("image_front_small_url") or p.get("image_front_url") or "",
    }


def search(query, limit=15):
    qs = urllib.parse.urlencode({
        "search_terms": query, "search_simple": 1, "action": "process", "json": 1,
        "page_size": 25, "fields": FIELDS, "sort_by": "unique_scans_n",
    })
    data = _get_json("https://es.openfoodfacts.org/cgi/search.pl?" + qs)
    out = [x for x in (normalize(p) for p in data.get("products", [])) if x]
    return out[:limit]


def by_barcode(code):
    if not re.fullmatch(r"\d{6,14}", code or ""):
        raise OffError("Código de barras no válido")
    data = _get_json(f"https://world.openfoodfacts.org/api/v2/product/{code}.json?fields={FIELDS}")
    if data.get("status") != 1:
        return None
    return normalize({**data["product"], "code": code})


def download_image(url, max_bytes=2_000_000):
    """Descarga una foto de producto (solo desde dominios de Open Food Facts). Devuelve (bytes, extensión) o None."""
    u = urllib.parse.urlparse(url or "")
    if u.scheme != "https" or not (u.hostname or "").endswith(("openfoodfacts.org", "openfoodfacts.net")):
        return None
    ext = "." + u.path.rsplit(".", 1)[-1].lower() if "." in u.path else ""
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = r.read(max_bytes + 1)
        return (data, ext) if len(data) <= max_bytes else None
    except Exception:
        return None

