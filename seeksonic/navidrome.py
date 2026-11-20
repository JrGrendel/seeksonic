from .core import *

def call_subsonic_internal(endpoint, params=None):
    salt = secrets.token_hex(6)
    # MD5 token auth is mandated by the Subsonic API; it is not a design choice here.
    token = hashlib.md5((NAVIDROME_PASSWORD + salt).encode("utf-8")).hexdigest()
    base_params = {
        "u": NAVIDROME_USER, "t": token, "s": salt,
        "v": "1.16.1", "c": "NavidromeLyricsSearch", "f": "json",
    }
    base_params.update(params or {})
    try:
        response = http_session().get(f"{NAVIDROME_URL}/rest/{endpoint}", params=base_params, timeout=(5, 30))
        return response.json().get("subsonic-response", {})
    except Exception as e:
        # Log only the exception type: the message embeds the URL (with t= and s=).
        log.warning("Subsonic API error (%s): %s", endpoint, type(e).__name__)
        return {"status": "failed", "_transport_error": True,
                "error": {"message": type(e).__name__}}


def call_subsonic_for_client(endpoint, params, auth_params, auth_headers=None):
    """Resolve a lyric hit using the requesting client's Navidrome credentials.

    This is deliberately separate from call_subsonic_internal(): using the
    indexer's service account here could reveal tracks hidden from the client.
    """
    allowed_auth = ("u", "t", "s", "p", "apiKey")
    credentials = {key: auth_params[key] for key in allowed_auth if auth_params.get(key)}
    headers = {}
    for key in ("Authorization", "Cookie"):
        if auth_headers and auth_headers.get(key):
            headers[key] = auth_headers[key]
    if not credentials and not headers:
        return {"status": "failed", "_transport_error": True}

    query = {
        **credentials,
        "v": auth_params.get("v", "1.16.1"),
        "c": auth_params.get("c", "NavidromeLyricsSearch"),
        "f": "json",
        **(params or {}),
    }
    try:
        response = http_session().get(
            f"{NAVIDROME_URL}/rest/{endpoint}",
            params=query,
            headers=headers,
            timeout=(5, 30),
        )
        return response.json().get("subsonic-response", {})
    except Exception as exc:
        log.warning("Client-scoped Subsonic lookup failed (%s): %s", endpoint, type(exc).__name__)
        return {"status": "failed", "_transport_error": True}


def subsonic_ok(resp):
    return isinstance(resp, dict) and resp.get("status") == "ok"


def _join_lines(lines):
    out = []
    for item in lines:
        text = (item.get("value") or item.get("line") or item.get("text")) if isinstance(item, dict) else item
        if isinstance(text, str) and text:
            out.append(text)
    return "\n".join(out)


def extract_lyrics_from_response(lyrics_obj):
    """Handles getLyrics ({value}), OpenSubsonic getLyricsBySongId
    ({structuredLyrics: [{line: [{value}]}]}) and older flat shapes."""
    if not isinstance(lyrics_obj, dict) or not lyrics_obj:
        return ""

    value = lyrics_obj.get("value")
    if isinstance(value, str) and value.strip():
        return value.strip()

    structured = lyrics_obj.get("structuredLyrics")
    if isinstance(structured, list):
        for entry in structured:
            if isinstance(entry, dict) and isinstance(entry.get("line"), list):
                text = _join_lines(entry["line"])
                if text.strip():
                    return text
        text = _join_lines(structured)
        if text.strip():
            return text

    synced = lyrics_obj.get("line")
    if isinstance(synced, list):
        return _join_lines(synced)
    return ""


def content_hash(title, artist, album, lyrics):
    """Hash of everything we index, so retagged tracks are refreshed too."""
    payload = "\x1f".join((title, artist, album, lyrics))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fetch_track_lyrics(song):
    """Network-only worker: safe to run in a thread pool (no DB access)."""
    song_id = song.get("id")
    result = {
        "id": song_id,
        "title": song.get("title") or "Unknown Title",
        "artist": song.get("artist") or "Unknown Artist",
        "album": song.get("album") or "Unknown Album",
        "lyrics": "",
        "error": None,
    }

    by_id = call_subsonic_internal("getLyricsBySongId", {"id": song_id})
    lyrics = extract_lyrics_from_response(by_id.get("lyricsList") or by_id.get("lyrics"))
    transport_failed = bool(by_id.get("_transport_error"))

    if not lyrics.strip() and song.get("artist") and song.get("title"):
        legacy = call_subsonic_internal("getLyrics", {"artist": song["artist"], "title": song["title"]})
        lyrics = extract_lyrics_from_response(legacy.get("lyrics"))
        transport_failed = transport_failed or bool(legacy.get("_transport_error"))

    result["lyrics"] = lyrics
    if not lyrics.strip() and transport_failed:
        result["error"] = "Navidrome request failed"
    return result


# ---------------------------------------------------------------------------


__all__ = ['call_subsonic_internal', 'call_subsonic_for_client', 'subsonic_ok', '_join_lines', 'extract_lyrics_from_response', 'content_hash', 'fetch_track_lyrics']
