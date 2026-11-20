from .core import *

_meili_ready = False


def _wait_meili_task(response, operation):
    """Wait for an asynchronous Meilisearch mutation to finish before updating local state."""
    if response.status_code not in (200, 202):
        response.raise_for_status()
        return False, f"{operation} returned HTTP {response.status_code}"

    try:
        payload = response.json()
    except ValueError:
        return (response.status_code == 200), None

    task_uid = payload.get("taskUid", payload.get("uid"))
    if task_uid is None:
        # Some successful responses may be synchronous and have no task identifier.
        return (response.status_code == 200), (
            None if response.status_code == 200 else f"{operation} returned no task identifier"
        )

    deadline = time.monotonic() + MEILI_TASK_TIMEOUT
    while time.monotonic() < deadline:
        try:
            task_response = http_session().get(
                f"{MEILISEARCH_URL}/tasks/{task_uid}",
                headers=get_meili_headers(),
                timeout=5,
            )
            task_response.raise_for_status()
            task = task_response.json()
        except (requests.RequestException, ValueError) as exc:
            return False, f"{operation} task {task_uid} could not be checked ({type(exc).__name__})"

        status = task.get("status")
        if status == "succeeded":
            return True, None
        if status in ("failed", "canceled"):
            error = task.get("error") or {}
            return False, f"{operation} task {task_uid} {status}: {error.get('message', 'unknown error')}"
        time.sleep(0.5)

    return False, f"{operation} task {task_uid} did not finish within {MEILI_TASK_TIMEOUT}s"


def get_meili_headers():
    if not MEILI_MASTER_KEY:
        raise RuntimeError("MEILI_MASTER_KEY is required")
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MEILI_MASTER_KEY}",
    }


def init_meilisearch():
    """Create the index and apply settings. Returns True on success."""
    global _meili_ready
    try:
        res = http_session().get(f"{MEILISEARCH_URL}/indexes/{INDEX_NAME}", headers=get_meili_headers(), timeout=10)
        if res.status_code == 404:
            created = http_session().post(
                f"{MEILISEARCH_URL}/indexes", headers=get_meili_headers(), timeout=10,
                json={"uid": INDEX_NAME, "primaryKey": "id"},
            )
            ok, error = _wait_meili_task(created, "Create index")
            if not ok:
                raise RuntimeError(error or "Meilisearch index creation failed")
        else:
            res.raise_for_status()

        settings = http_session().patch(
            f"{MEILISEARCH_URL}/indexes/{INDEX_NAME}/settings",
            headers=get_meili_headers(), timeout=10,
            json={
                "searchableAttributes": ["lyrics", "title", "artist", "album"],
                "displayedAttributes": ["id", "title", "artist", "album", "lyrics"],
                "rankingRules": ["words", "typo", "proximity", "attribute", "exactness"],
                "typoTolerance": {
                    "enabled": True,
                    "minWordSizeForTypos": {"oneTypo": 5, "twoTypos": 9},
                },
                "pagination": {"maxTotalHits": 500},
            },
        )
        ok, error = _wait_meili_task(settings, "Update index settings")
        if not ok:
            raise RuntimeError(error or "Meilisearch settings update failed")
        _meili_ready = True
        return True
    except Exception as e:
        log.error("Error initializing Meilisearch settings: %s", redact(f"{type(e).__name__}: {e}"))
        return False


def ensure_meilisearch():
    return _meili_ready or init_meilisearch()


def _meili_add(docs):
    """Returns (ok, error_message)."""
    try:
        r = http_session().post(
            f"{MEILISEARCH_URL}/indexes/{INDEX_NAME}/documents",
            headers=get_meili_headers(), json=docs, timeout=60,
        )
        ok, error = _wait_meili_task(r, "Document indexing")
        return ok, error
    except requests.RequestException as e:
        return False, redact(f"{type(e).__name__}: {e}")[:500]


def _meili_delete(ids):
    try:
        r = http_session().post(
            f"{MEILISEARCH_URL}/indexes/{INDEX_NAME}/documents/delete-batch",
            headers=get_meili_headers(), json=list(ids), timeout=60,
        )
        ok, error = _wait_meili_task(r, "Document deletion")
        if not ok:
            log.error("Meilisearch delete failed: %s", error)
        return ok
    except requests.RequestException as e:
        log.error("Meilisearch delete failed: %s", redact(f"{type(e).__name__}: {e}"))
        return False


# ---------------------------------------------------------------------------


__all__ = ['_meili_ready', '_wait_meili_task', 'get_meili_headers', 'init_meilisearch', 'ensure_meilisearch', '_meili_add', '_meili_delete']
