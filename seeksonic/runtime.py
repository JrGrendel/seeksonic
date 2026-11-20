from .core import *
from .meilisearch import *
from .sync import *

def validate_runtime_config():
    """Fail closed when required credentials or upstream URLs are missing."""
    required = {
        "NAVIDROME_USER": NAVIDROME_USER,
        "NAVIDROME_PASSWORD": NAVIDROME_PASSWORD,
        "ADMIN_USER": ADMIN_USER,
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
        "ADMIN_SESSION_SECRET": ADMIN_SESSION_SECRET,
        "MEILI_MASTER_KEY": MEILI_MASTER_KEY,
    }
    missing = [name for name, value in required.items() if not value or not value.strip()]
    if missing:
        raise RuntimeError("Required environment variables are missing: " + ", ".join(missing))
    if len(ADMIN_PASSWORD) < 8:
        raise RuntimeError("ADMIN_PASSWORD must contain at least 8 characters")
    if len(ADMIN_SESSION_SECRET) < 32:
        raise RuntimeError("ADMIN_SESSION_SECRET must contain at least 32 characters")
    if len(MEILI_MASTER_KEY) < 8:
        raise RuntimeError("MEILI_MASTER_KEY must contain at least 8 characters")

    for name, value in (("NAVIDROME_URL", NAVIDROME_URL), ("MEILISEARCH_URL", MEILISEARCH_URL)):
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise RuntimeError(f"{name} must be an absolute http:// or https:// URL")
        if parsed.username or parsed.password:
            raise RuntimeError(f"{name} must not contain embedded credentials")


def serve():
    try:
        from waitress import serve as waitress_serve  # optional production server
    except ImportError:
        log.warning("waitress not installed; using Flask's built-in server "
                    "(pip install waitress for production use).")
        app.run(host=HOST, port=PORT, threaded=True)
    else:
        waitress_serve(app, host=HOST, port=PORT, threads=WAITRESS_THREADS)

def main():
    validate_runtime_config()
    init_db()
    init_meilisearch()

    if SYNC_INTERVAL_MINUTES > 0:
        threading.Thread(
            target=background_scheduler_thread,
            daemon=True,
            name="scheduler",
        ).start()
    else:
        log.info("SYNC_INTERVAL_MINUTES=0: automatic background sync disabled.")

    serve()


__all__ = ['validate_runtime_config', 'serve', 'main']
