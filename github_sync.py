"""Sincronización automática bidireccional de data/macros.db con GitHub API.

Permite que al desplegar la app en Render (disco efímero) o usarla en varios PCs:
1. Cada cambio en la base de datos (comidas, alimentos, combos, pesos, objetivos)
   se suba automáticamente a `data/macros.db` en el repositorio de GitHub.
2. Al arrancar el servidor (o periódicamente en segundo plano), compruebe si hay
   una versión más reciente de `data/macros.db` en GitHub y la descargue sin perder
   las claves privadas locales (`github_token`, `gemini_api_key`, `pin_hash`).
"""
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import db

DEFAULT_REPO = "ivangarmir18/Calculadora_Macros"
DEFAULT_BRANCH = "main"
REMOTE_DB_PATH = "data/macros.db"
SECRET_KEYS = ("github_token", "gemini_api_key", "pin_hash", "auth_token")

_lock = threading.Lock()
_timer: threading.Timer | None = None
_suppress_sync = False

_state = {
    "last_Known_sha": None,
    "last_push_at": None,
    "last_pull_at": None,
    "last_error": None,
    "dirty": False,
    "syncing": False,
}


def _read_dotenv() -> dict[str, str]:
    env_path = Path(__file__).resolve().parent / ".env"
    out: dict[str, str] = {}
    if env_path.is_file():
        try:
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass
    return out


def get_config() -> dict[str, str]:
    """Obtiene token, repo y branch desde variables de entorno, .env o tabla settings."""
    dotenv = _read_dotenv()
    token = (os.environ.get("GITHUB_TOKEN") or dotenv.get("GITHUB_TOKEN") or "").strip()
    repo = (os.environ.get("GITHUB_REPO") or dotenv.get("GITHUB_REPO") or "").strip()
    branch = (os.environ.get("GITHUB_BRANCH") or dotenv.get("GITHUB_BRANCH") or "").strip()
    source = "env" if token else "none"

    if not token or not repo:
        try:
            if db.DB_PATH.is_file():
                conn = sqlite3.connect(db.DB_PATH)
                try:
                    if not token:
                        r = conn.execute("SELECT value FROM settings WHERE key='github_token'").fetchone()
                        if r and r[0].strip():
                            token = r[0].strip()
                            source = "db"
                    if not repo:
                        r2 = conn.execute("SELECT value FROM settings WHERE key='github_repo'").fetchone()
                        if r2 and r2[0].strip():
                            repo = r2[0].strip()
                finally:
                    conn.close()
        except Exception:
            pass

    return {
        "token": token,
        "source": source,
        "repo": repo or DEFAULT_REPO,
        "branch": branch or DEFAULT_BRANCH,
    }


def mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 10:
        return "••••" + token[-2:]
    return token[:6] + "••••••••" + token[-4:]


def git_blob_sha(data: bytes) -> str:
    """Calcula el SHA-1 de blob de Git exactamente igual que GitHub."""
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def _create_clean_db_bytes() -> bytes:
    """Crea una copia limpia de macros.db sin claves secretas para subir a GitHub de forma segura."""
    with tempfile.TemporaryDirectory() as tmpdir:
        clean_path = Path(tmpdir) / "macros_clean.db"
        src = sqlite3.connect(db.DB_PATH)
        try:
            dst = sqlite3.connect(clean_path)
            try:
                src.backup(dst)
                placeholders = ",".join("?" * len(SECRET_KEYS))
                dst.execute(f"DELETE FROM settings WHERE key IN ({placeholders})", SECRET_KEYS)
                dst.commit()
            finally:
                dst.close()
        finally:
            src.close()

        # Compactar fuera de transacción para limpiar páginas borradas
        vconn = sqlite3.connect(clean_path)
        try:
            vconn.execute("VACUUM")
        finally:
            vconn.close()

        return clean_path.read_bytes()


def _github_request(method: str, url: str, token: str = "", payload: dict | None = None, timeout: int = 20):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "CalculadoraMacros-Sync/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_remote_meta(cfg: dict | None = None) -> dict | None:
    """Consulta los metadatos (y contenido base64 si <1MB) de data/macros.db en GitHub."""
    cfg = cfg or get_config()
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{REMOTE_DB_PATH}?ref={cfg['branch']}"
    try:
        return _github_request("GET", url, token=cfg["token"], timeout=15)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def pull_from_github(force: bool = False) -> dict:
    """Descarga data/macros.db desde GitHub si el archivo remoto cambió y actualiza la DB local
    preservando las claves privadas locales (`github_token`, `gemini_api_key`, `pin_hash`)."""
    global _suppress_sync
    if _state["dirty"] and not force:
        return {"ok": False, "skipped": "dirty_local_changes"}

    cfg = get_config()
    try:
        meta = fetch_remote_meta(cfg)
        if not meta or "sha" not in meta:
            return {"ok": False, "skipped": "no_remote_file"}

        remote_sha = meta["sha"]
        if not force and _state["last_Known_sha"] == remote_sha:
            return {"ok": True, "up_to_date": True, "sha": remote_sha}

        # Si tenemos DB local y su versión limpia tiene exactamente el mismo blob SHA, no hace falta pisarla
        if not force and db.DB_PATH.is_file():
            try:
                local_clean_sha = git_blob_sha(_create_clean_db_bytes())
                if local_clean_sha == remote_sha:
                    _state["last_Known_sha"] = remote_sha
                    return {"ok": True, "up_to_date": True, "sha": remote_sha}
            except Exception:
                pass

        # Obtener bytes del archivo remoto
        content_b64 = meta.get("content", "")
        if content_b64:
            raw_bytes = base64.b64decode(content_b64)
        elif meta.get("download_url"):
            req = urllib.request.Request(meta["download_url"], headers={"User-Agent": "CalculadoraMacros-Sync/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                raw_bytes = r.read()
        else:
            return {"ok": False, "error": "No se pudo descargar el contenido remoto"}

        if not raw_bytes.startswith(b"SQLite format 3"):
            return {"ok": False, "error": "El archivo remoto no es una base SQLite válida"}

        with _lock:
            _suppress_sync = True
            try:
                # 1. Guardar secretos locales actuales antes de actualizar
                saved_secrets: dict[str, str] = {}
                if db.DB_PATH.is_file():
                    try:
                        lconn = sqlite3.connect(db.DB_PATH)
                        try:
                            placeholders = ",".join("?" * len(SECRET_KEYS))
                            rows = lconn.execute(
                                f"SELECT key, value FROM settings WHERE key IN ({placeholders})",
                                SECRET_KEYS,
                            ).fetchall()
                            for k, v in rows:
                                if v:
                                    saved_secrets[k] = v
                        finally:
                            lconn.close()
                    except Exception:
                        pass

                # 2. Escribir la base descargada y restaurar secretos locales
                db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tf:
                    tf.write(raw_bytes)
                    tmp_path = Path(tf.name)

                try:
                    tconn = sqlite3.connect(tmp_path)
                    try:
                        for k, v in saved_secrets.items():
                            tconn.execute(
                                "INSERT INTO settings(key, value) VALUES (?, ?) "
                                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                (k, v),
                            )
                        tconn.commit()
                    finally:
                        tconn.close()

                    shutil.move(str(tmp_path), str(db.DB_PATH))
                finally:
                    if tmp_path.exists():
                        tmp_path.unlink(missing_ok=True)

                _state["last_Known_sha"] = remote_sha
                _state["last_pull_at"] = datetime.now().isoformat(timespec="seconds")
                _state["last_error"] = None
                return {"ok": True, "pulled": True, "sha": remote_sha}
            finally:
                _suppress_sync = False

    except Exception as e:
        _state["last_error"] = f"Pull error: {e}"
        return {"ok": False, "error": str(e)}


def push_to_github() -> dict:
    """Sube data/macros.db (sin claves privadas) a GitHub mediante la API de Contents."""
    cfg = get_config()
    if not cfg["token"]:
        return {"ok": False, "error": "Falta configurar GITHUB_TOKEN para guardar en GitHub"}

    if not db.DB_PATH.is_file():
        return {"ok": False, "error": "No existe base de datos local"}

    with _lock:
        _state["syncing"] = True
        try:
            clean_bytes = _create_clean_db_bytes()
            new_blob_sha = git_blob_sha(clean_bytes)

            meta = fetch_remote_meta(cfg)
            remote_sha = meta["sha"] if meta and "sha" in meta else None

            if remote_sha == new_blob_sha:
                _state["last_Known_sha"] = remote_sha
                _state["dirty"] = False
                _state["last_error"] = None
                return {"ok": True, "unchanged": True, "sha": remote_sha}

            url = f"https://api.github.com/repos/{cfg['repo']}/contents/{REMOTE_DB_PATH}"
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            payload = {
                "message": f"chore(db): auto-sync macros.db ({now_str}) [skip ci] [skip render]",
                "content": base64.b64encode(clean_bytes).decode("ascii"),
                "branch": cfg["branch"],
            }
            if remote_sha:
                payload["sha"] = remote_sha

            res = _github_request("PUT", url, token=cfg["token"], payload=payload, timeout=25)
            committed_sha = (res.get("content") or {}).get("sha") or new_blob_sha
            _state["last_Known_sha"] = committed_sha
            _state["last_push_at"] = datetime.now().isoformat(timespec="seconds")
            _state["last_error"] = None
            _state["dirty"] = False
            return {"ok": True, "pushed": True, "sha": committed_sha}

        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            msg = f"HTTP {e.code}: {body[:180] or e.reason}"
            _state["last_error"] = msg
            return {"ok": False, "error": msg}
        except Exception as e:
            _state["last_error"] = str(e)
            return {"ok": False, "error": str(e)}
        finally:
            _state["syncing"] = False


def schedule_push(delay: float = 1.5):
    """Programa una subida a GitHub en segundo plano (con debounce para agrupar cambios seguidos)."""
    global _timer
    if _suppress_sync:
        return
    # No ejecutar durante tests unitarios con bases temporales
    if "test.db" in str(db.DB_PATH):
        return

    _state["dirty"] = True
    cfg = get_config()
    if not cfg["token"]:
        return

    if _timer is not None:
        _timer.cancel()

    def _run():
        push_to_github()

    _timer = threading.Timer(delay, _run)
    _timer.daemon = True
    _timer.start()


_last_periodic_check = 0.0


def maybe_periodic_pull(interval_sec: float = 45.0):
    """Comprueba en segundo plano cada X segundos si hubo cambios en GitHub."""
    global _last_periodic_check
    if "test.db" in str(db.DB_PATH) or _state["dirty"] or _state["syncing"]:
        return
    now = time.time()
    if now - _last_periodic_check < interval_sec:
        return
    _last_periodic_check = now

    def _bg():
        try:
            pull_from_github(force=False)
        except Exception:
            pass

    t = threading.Thread(target=_bg, daemon=True)
    t.start()


def get_status() -> dict:
    cfg = get_config()
    return {
        "configured": bool(cfg["token"]),
        "source": cfg["source"],
        "masked": mask_token(cfg["token"]),
        "repo": cfg["repo"],
        "branch": cfg["branch"],
        "last_push_at": _state["last_push_at"],
        "last_pull_at": _state["last_pull_at"],
        "last_error": _state["last_error"],
        "dirty": _state["dirty"],
        "syncing": _state["syncing"],
        "sha": (_state["last_Known_sha"] or "")[:7],
    }

