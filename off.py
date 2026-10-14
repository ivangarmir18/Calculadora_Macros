"""Cliente mínimo de Open Food Facts (base de datos abierta de productos, sin API key)."""
import json
import re
import urllib.parse
import urllib.request

UA = "CalculadoraMacros/1.0 (app personal; github.com/ivangarmir18/Calculadora_Macros)"
FIELDS = "code,product_name,product_name_es,brands,nutriments,image_front_small_url,image_front_url,image_url"


class OffError(Exception):
    pass


def _get_json(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception as e:
        raise OffError("No se pudo conectar con Open Food Facts") from e


def _n(nutr, key):
    v = nutr.get(key)
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def clean_brand(b):
    if isinstance(b, list):
        return b[0].strip() if b else ""
    if isinstance(b, str):
        return b.split(",")[0].strip()
    return ""


def normalize(p):
    """Producto OFF -> alimento de la app (valores por 100 g). None si no tiene datos nutricionales."""
    nu = p.get("nutriments") or {}
    kcal = _n(nu, "energy-kcal_100g")
    if kcal is None:  # algunos productos solo traen kJ
        kj = _n(nu, "energy_100g")
        kcal = round(kj / 4.184, 1) if kj is not None else None
    protein, carbs, fat = _n(nu, "proteins_100g"), _n(nu, "carbohydrates_100g"), _n(nu, "fat_100g")
    name = (p.get("product_name_es") or p.get("product_name") or p.get("generic_name") or "").strip()
    if not name or (kcal is None and protein is None and carbs is None and fat is None):
        return None
    if kcal is None:
        kcal = round((protein or 0) * 4 + (carbs or 0) * 4 + (fat or 0) * 9, 1)

    photo = (
        p.get("image_front_small_url")
        or p.get("image_front_url")
        or p.get("image_url")
        or p.get("image_small_url")
        or ""
    )
    return {
        "name": name,
        "brand": clean_brand(p.get("brands")),
        "kcal": kcal,
        "protein": protein or 0.0,
        "carbs": carbs or 0.0,
        "fat": fat or 0.0,
        "barcode": p.get("code") or "",
        "photo_url": photo,
    }


def search(query, limit=15):
    """Busca en Open Food Facts usando Search-a-licious con fallback a la API clásica."""
    q = (query or "").strip()
    if len(q) < 2:
        return []

    # Expansión de sinónimos de supermercados en España para mejores resultados
    q_lower = q.lower()
    queries = [q]
    if "mercadona" in q_lower and "hacendado" not in q_lower:
        queries.insert(0, q_lower.replace("mercadona", "hacendado"))
    if "lidl" in q_lower and "milbona" not in q_lower:
        queries.append(q_lower.replace("lidl", "milbona"))

    products = []
    # 1. Probar Search-a-licious (Elasticsearch moderno de OFF, sin errores 503)
    for q_try in queries:
        try:
            url = f"https://search.openfoodfacts.org/search?q={urllib.parse.quote(q_try)}&page_size=25"
            data = _get_json(url, timeout=6)
            hits = data.get("hits", [])
            for h in hits:
                norm = normalize(h)
                if norm and not any(p["name"].lower() == norm["name"].lower() and p["brand"].lower() == norm["brand"].lower() for p in products):
                    products.append(norm)
            if len(products) >= limit:
                break
        except Exception:
            continue

    # 2. Fallback si Search-a-licious no dio suficientes resultados
    if not products:
        try:
            qs = urllib.parse.urlencode({
                "search_terms": q, "search_simple": 1, "action": "process", "json": 1,
                "page_size": 25, "fields": FIELDS, "sort_by": "unique_scans_n",
            })
            data = _get_json("https://world.openfoodfacts.org/cgi/search.pl?" + qs, timeout=6)
            for p in data.get("products", []):
                norm = normalize(p)
                if norm and not any(x["barcode"] and x["barcode"] == norm["barcode"] for x in products):
                    products.append(norm)
        except Exception:
            pass

    return products[:limit]


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
