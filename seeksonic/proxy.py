from .core import *
from .meilisearch import get_meili_headers
from .navidrome import *

_HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailers", "transfer-encoding", "upgrade"}
_SKIP_REQUEST_HEADERS = _HOP_BY_HOP | {"host", "content-length"}


def _forward_headers(strip_encoding=False):
    headers = {k: v for k, v in request.headers if k.lower() not in _SKIP_REQUEST_HEADERS}
    if strip_encoding:
        # We parse these responses ourselves; let `requests` negotiate encodings it can decode.
        headers = {k: v for k, v in headers.items() if k.lower() != "accept-encoding"}
    # Do not trust a client-supplied X-Forwarded-For value. If deployed behind
    # a reverse proxy, configure trusted-proxy handling at that boundary.
    headers["X-Forwarded-For"] = request.remote_addr or ""
    return headers


def _forward_to_navidrome(subpath, *, stream, timeout, strip_encoding=False):
    kwargs = {
        # multi=True keeps repeated params (e.g. songId=1&songId=2) intact.
        "params": list(request.args.items(multi=True)),
        "headers": _forward_headers(strip_encoding),
        "stream": stream,
        "timeout": timeout,
    }
    url = f"{NAVIDROME_URL}/rest/{subpath}"
    if request.method == "POST":
        return http_session().post(url, data=request.get_data(), **kwargs)
    return http_session().get(url, **kwargs)


def _subsonic_error(fmt, message, http_status=502, code=0):
    if fmt == "json":
        return jsonify({"subsonic-response": {
            "status": "failed", "version": "1.16.1", "type": "Navidrome", "openSubsonic": True,
            "error": {"code": code, "message": message},
        }}), http_status
    body = (f'<?xml version="1.0" encoding="UTF-8"?>\n<subsonic-response xmlns="{SUBSONIC_NS}" '
            f'status="failed" version="1.16.1"><error code="{code}" message={quoteattr(message)}/>'
            "</subsonic-response>")
    return Response(body, http_status, mimetype="application/xml")


def _iter_upstream(resp):
    """Stream the upstream body without decoding (headers are forwarded as-is)."""
    try:
        for chunk in resp.raw.stream(64 * 1024, decode_content=False):
            if chunk:
                yield chunk
    finally:
        resp.close()


@app.route("/rest/<path:subpath>", methods=["GET", "POST"])
def subsonic_proxy_interceptor(subpath):
    if ".." in subpath.split("/") or "\\" in subpath:
        return _subsonic_error("json", "Invalid path", 400)

    clean_endpoint = subpath.split(".")[0]
    if clean_endpoint in ("search3", "search2"):
        return handle_intercepted_search(subpath, clean_endpoint)

    fmt = request.args.get("f", "xml").lower()
    try:
        resp = _forward_to_navidrome(subpath, stream=True, timeout=(5, 120))
    except Exception as e:
        log.error("Proxy pass-through error (%s): %s", subpath, type(e).__name__)
        return _subsonic_error(fmt, "Upstream Navidrome request failed")

    headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in _HOP_BY_HOP]
    return Response(_iter_upstream(resp), resp.status_code, headers)


def _to_int(value, default):
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def find_lyric_matches(query, limit, client_auth_params, client_auth_headers=None):
    """Search the shared lyric index, then resolve IDs as the requesting client."""
    try:
        r = http_session().post(
            f"{MEILISEARCH_URL}/indexes/{INDEX_NAME}/search",
            headers=get_meili_headers(), timeout=5,
            json={"q": query[:200], "limit": limit, "attributesToRetrieve": ["id"]},
        )
        r.raise_for_status()
        ids = [h["id"] for h in r.json().get("hits", []) if h.get("id")]
    except Exception as e:
        log.warning("[SEARCH PROXY] Meilisearch query failed: %s", type(e).__name__)
        return []

    results = list(_lookup_pool.map(
        lambda sid: call_subsonic_for_client(
            "getSong", {"id": sid}, client_auth_params, client_auth_headers
        ),
        ids,
    ))
    return [r["song"] for r in results if subsonic_ok(r) and isinstance(r.get("song"), dict)]


def _merge_json(nav_raw, search_key, lyric_songs, song_count):
    data = nav_raw.json()
    sub = data.get("subsonic-response", {})
    if sub.get("status") != "ok":
        return None
    result = sub.get(search_key) or {}
    lyric_ids = {s.get("id") for s in lyric_songs}
    nav_songs = [s for s in result.get("song", []) if isinstance(s, dict) and s.get("id") not in lyric_ids]
    result["song"] = (lyric_songs + nav_songs)[:song_count]
    sub[search_key] = result
    data["subsonic-response"] = sub
    return data


def _song_to_xml_attrs(song):
    attrs = {}
    for key, value in song.items():
        if isinstance(value, bool):
            attrs[key] = "true" if value else "false"
        elif isinstance(value, (str, int, float)):
            attrs[key] = str(value)
        # nested lists/objects (genres, artists, ...) are child elements in XML; skipped
    attrs.setdefault("isDir", "false")
    attrs.setdefault("isVideo", "false")
    attrs.setdefault("type", "music")
    return attrs


def _merge_xml(nav_raw, search_key, lyric_songs, song_count):
    root = ET.fromstring(nav_raw.content)
    if root.attrib.get("status") != "ok":
        return None
    ns = root.tag[1:].split("}")[0] if root.tag.startswith("{") else ""
    song_tag = f"{{{ns}}}song" if ns else "song"

    search_elem = next((e for e in root.iter() if e.tag.endswith(search_key)), None)
    if search_elem is None:
        return None

    existing = [c for c in list(search_elem) if c.tag.endswith("song")]
    for child in existing:
        search_elem.remove(child)

    lyric_ids = set()
    for song in lyric_songs:
        sid = str(song.get("id", ""))
        if sid:
            lyric_ids.add(sid)
            ET.SubElement(search_elem, song_tag, _song_to_xml_attrs(song))

    added = len(lyric_ids)
    for elem in existing:
        if added >= song_count:
            break
        if elem.attrib.get("id") not in lyric_ids:
            search_elem.append(elem)
            added += 1

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8", method="xml")


def handle_intercepted_search(subpath, clean_endpoint):
    request.get_data()  # cache the body before form parsing
    params = request.values.to_dict()
    if request.is_json:
        body = request.get_json(silent=True)
        if isinstance(body, dict):
            params.update(body)

    query = str(params.get("query") or params.get("q") or "").strip()
    fmt = str(params.get("f", "xml")).lower()
    song_count = _to_int(params.get("songCount"), 20)
    song_offset = _to_int(params.get("songOffset"), 0)

    # 1. Forward the request to Navidrome (it performs the real authentication)
    try:
        nav_raw = _forward_to_navidrome(subpath, stream=False, timeout=15, strip_encoding=True)
    except Exception as e:
        log.error("[SEARCH PROXY] Error querying Navidrome: %s", type(e).__name__)
        return _subsonic_error(fmt, "Upstream Navidrome request failed")

    content_type = nav_raw.headers.get("Content-Type")

    def passthrough():
        return Response(nav_raw.content, nav_raw.status_code, content_type=content_type)

    # Nothing to inject: error, empty query, client wants no songs, or a later page.
    if nav_raw.status_code != 200 or not query or song_count <= 0 or song_offset > 0:
        return passthrough()

    # 2. Lyric matches (only reached for authenticated, successful responses; see _merge_*)
    is_json = fmt == "json" or "application/json" in (content_type or "")
    search_key = "searchResult3" if clean_endpoint == "search3" else "searchResult2"

    try:
        # Validate Navidrome accepted the client's credentials BEFORE spending
        # (or leaking) anything from the lyric index.
        if is_json:
            sub = nav_raw.json().get("subsonic-response", {})
            if sub.get("status") != "ok":
                return passthrough()
        else:
            if ET.fromstring(nav_raw.content).attrib.get("status") != "ok":
                return passthrough()

        client_auth_params = {
            key: params[key] for key in ("u", "t", "s", "p", "apiKey", "v", "c")
            if params.get(key)
        }
        client_auth_headers = {
            key: request.headers[key] for key in ("Authorization", "Cookie")
            if request.headers.get(key)
        }
        lyric_songs = find_lyric_matches(
            query,
            min(LYRIC_MATCH_LIMIT, song_count),
            client_auth_params,
            client_auth_headers,
        )

        # 3. Merge
        if is_json:
            merged = _merge_json(nav_raw, search_key, lyric_songs, song_count)
            return jsonify(merged) if merged is not None else passthrough()
        merged = _merge_xml(nav_raw, search_key, lyric_songs, song_count)
        return Response(merged, mimetype="application/xml") if merged is not None else passthrough()
    except Exception:
        log.exception("[SEARCH PROXY] Failed to merge lyric results; returning Navidrome's response")
        return passthrough()


# ===========================================================================


__all__ = ['_HOP_BY_HOP', '_SKIP_REQUEST_HEADERS', '_forward_headers', '_forward_to_navidrome', '_subsonic_error', '_iter_upstream', 'subsonic_proxy_interceptor', '_to_int', 'find_lyric_matches', '_merge_json', '_song_to_xml_attrs', '_merge_xml', 'handle_intercepted_search']
