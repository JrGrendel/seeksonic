from .core import *
from .meilisearch import *
from .navidrome import *

_sync_lock = threading.Lock()


def enumerate_library():
    """Returns (tracks, complete). `complete` is False if any album failed to
    load, in which case the deletion phase must not run."""
    status = indexing_status
    albums, offset, size = [], 0, 500
    while True:
        resp = call_subsonic_internal(
            "getAlbumList2", {"type": "alphabeticalByArtist", "size": size, "offset": offset}
        )
        if not subsonic_ok(resp):
            raise RuntimeError("Navidrome failed or refused the album listing request")
        page = resp.get("albumList2", {}).get("album", [])
        if not page:
            break
        albums.extend(page)
        if len(page) < size:
            break
        offset += size

    status["current_action"] = f"Reading {len(albums)} albums..."

    def load_album(album):
        if not album.get("id"):
            return None
        resp = call_subsonic_internal("getAlbum", {"id": album["id"]})
        if not subsonic_ok(resp):
            return None
        return resp.get("album", {}).get("song", []) or []

    tracks, complete = {}, True
    with ThreadPoolExecutor(max_workers=SYNC_WORKERS) as pool:
        for songs in pool.map(load_album, albums):
            if songs is None:
                complete = False
                continue
            for song in songs:
                if isinstance(song, dict) and song.get("id"):
                    tracks[song["id"]] = song
    return list(tracks.values()), complete


def _commit_chunk(pending, rows, removals, now):
    status = indexing_status

    if removals and not _meili_delete(removals):
        # Keep the 'indexed' DB state so the removal is retried next sync.
        failed = set(removals)
        rows = [r for r in rows if r[0] not in failed]

    if pending:
        ok, err = _meili_add([doc for doc, _ in pending])
        for doc, digest in pending:
            base = (doc["id"], doc["title"], doc["artist"], doc["album"])
            if ok:
                rows.append(base + (digest, now, "indexed", None))
                status["indexed_count"] += 1
            else:
                rows.append(base + (None, now, "error", err))
                status["error_count"] += 1
        if not ok:
            status["last_error"] = err

    if rows:
        with get_db() as conn:
            conn.executemany(UPSERT_SQL, rows)


def sync_tracks(tracks):
    status = indexing_status
    with get_db() as conn:
        existing = {
            r["song_id"]: (r["status"], r["lyrics_hash"])
            for r in conn.execute("SELECT song_id, status, lyrics_hash FROM track_state")
        }

    with ThreadPoolExecutor(max_workers=SYNC_WORKERS) as pool:
        for start in range(0, len(tracks), CHUNK_SIZE):
            chunk = tracks[start:start + CHUNK_SIZE]
            now = int(time.time())
            pending, rows, removals = [], [], []

            for item in pool.map(fetch_track_lyrics, chunk):
                sid = item["id"]
                status["current_action"] = f"Syncing: {item['artist']} - {item['title']}"
                status["processed_tracks"] += 1
                prev_status, prev_hash = existing.get(sid, (None, None))

                if not item["lyrics"].strip():
                    if item["error"]:
                        status["error_count"] += 1
                        status["last_error"] = item["error"]
                        continue
                    status["missing_lyrics_count"] += 1
                    if prev_status == "indexed":
                        removals.append(sid)  # lyrics disappeared: drop stale doc
                    if prev_status != "no_lyrics":
                        rows.append((sid, item["title"], item["artist"], item["album"],
                                     None, now, "no_lyrics", "No lyrics returned by API"))
                    continue

                digest = content_hash(item["title"], item["artist"], item["album"], item["lyrics"])
                # Only skip if actually indexed. A previously purged ('deleted')
                # track that reappears must be re-indexed.
                if prev_status == "indexed" and prev_hash == digest:
                    status["skipped_count"] += 1
                    continue

                pending.append(({
                    "id": sid, "title": item["title"], "artist": item["artist"],
                    "album": item["album"], "lyrics": item["lyrics"],
                }, digest))

            _commit_chunk(pending, rows, removals, now)


def reconcile_deleted(active_ids, complete):
    status = indexing_status
    status["current_action"] = "Reconciling deleted tracks..."
    if not complete:
        log.warning("Library enumeration was incomplete; skipping deletion cleanup.")
        return

    with get_db() as conn:
        db_ids = {r["song_id"] for r in conn.execute(
            "SELECT song_id FROM track_state WHERE status != 'deleted'")}
    stale = sorted(db_ids - active_ids)
    if not stale:
        return
    if not active_ids:
        # Safety net: an empty library is far more likely an outage than reality.
        log.warning("Navidrome returned zero tracks; refusing to purge %d indexed tracks.", len(stale))
        return

    for i in range(0, len(stale), 1000):
        batch = stale[i:i + 1000]
        if _meili_delete(batch):
            with get_db() as conn:
                conn.executemany("UPDATE track_state SET status = 'deleted' WHERE song_id = ?",
                                 [(sid,) for sid in batch])
            status["deleted_count"] += len(batch)
        else:
            log.error("Failed to purge %d tracks from Meilisearch; will retry next sync.", len(batch))


def _run_sync():
    status = indexing_status
    status.update(
        total_tracks=0, processed_tracks=0, indexed_count=0, skipped_count=0,
        missing_lyrics_count=0, error_count=0, deleted_count=0, last_error=None,
        current_action="Preparing...",
    )
    try:
        if not ensure_meilisearch():
            raise RuntimeError("Meilisearch is unreachable or rejected its configuration")

        status["current_action"] = "Enumerating library..."
        tracks, complete = enumerate_library()
        status["total_tracks"] = len(tracks)

        sync_tracks(tracks)
        reconcile_deleted({t["id"] for t in tracks}, complete)

        status["last_sync_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        status["current_action"] = (
            "Sync completed." if complete
            else "Sync completed with warnings (some albums unreadable; deletion cleanup skipped)."
        )
    except Exception as e:
        msg = redact(f"{type(e).__name__}: {e}")
        log.error("Sync failed: %s", msg)
        status["last_error"] = msg
        status["current_action"] = f"Failed: {msg}"


def run_sync_blocking():
    """Run a sync in the current thread. Returns False if one is already running."""
    if not _sync_lock.acquire(blocking=False):
        return False
    indexing_status["is_running"] = True
    try:
        _run_sync()
    finally:
        indexing_status["is_running"] = False
        _sync_lock.release()
    return True


def start_sync_in_background():
    """Start a sync thread. Returns False if one is already running."""
    if not _sync_lock.acquire(blocking=False):
        return False
    indexing_status["is_running"] = True

    def _target():
        try:
            _run_sync()
        finally:
            indexing_status["is_running"] = False
            _sync_lock.release()

    threading.Thread(target=_target, daemon=True, name="sync").start()
    return True


def background_scheduler_thread():
    while True:
        try:
            log.info("[SCHEDULER] Running periodic background sync...")
            if not run_sync_blocking():
                log.info("[SCHEDULER] A sync is already running; skipping this cycle.")
        except Exception as e:
            log.error("[SCHEDULER] Error during sync: %s", redact(e))
        time.sleep(SYNC_INTERVAL_MINUTES * 60)


# ===========================================================================


__all__ = ['_sync_lock', 'enumerate_library', '_commit_chunk', 'sync_tracks', 'reconcile_deleted', '_run_sync', 'run_sync_blocking', 'start_sync_in_background', 'background_scheduler_thread']
