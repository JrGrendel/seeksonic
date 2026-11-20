from .core import *
from .meilisearch import *
from .navidrome import *
from .sync import *
from .proxy import *

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <!-- Application favicon -->
    <link rel="icon" href="/static/favicon.ico" sizes="any">
    <link rel="icon" type="image/png"
        sizes="32x32" href="/static/favicon-32.png">

    <!-- Mobile / Apple -->
    <link rel="apple-touch-icon"
        sizes="180x180" href="/static/apple-touch-icon.png">
    <meta name="csrf-token" content="{{ csrf_token }}">
    <title>SeekSonic</title>
    <style>
        :root { color-scheme: dark; --bg:#0b1120; --panel:#111c2e; --panel2:#0d1728; --line:#26364d; --muted:#91a2b9; --text:#e6edf7; --accent:#38bdf8; }
        * { box-sizing:border-box; }
        body { font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; background:radial-gradient(ellipse at top,#14243a 0%,var(--bg) 55%); color:var(--text); margin:0; padding:32px 20px 56px; min-height:100vh; }
        .container { max-width:1040px; margin:0 auto; }
        .topbar { display:flex; align-items:center; justify-content:space-between; gap:20px; margin-bottom:26px; }
        h1 { color:#f1f7ff; font-size:clamp(1.5rem,3vw,2rem); letter-spacing:-.04em; margin:0 0 5px; }
        h3 { font-size:1.05rem; margin:0 0 14px; letter-spacing:-.01em; }
        p.subtitle,.section-note { color:var(--muted); margin:0; font-size:.9rem; }
        .account { display:flex; flex-direction:column; align-items:flex-end; gap:3px; background:#111d30; border:1px solid var(--line); border-radius:12px; padding:10px 14px; min-width:130px; }
        .account-label { color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; }
        .account strong { font-size:.9rem; } .account button { margin:6px 0 0; padding:7px 10px; font-size:.78rem; }
        .card { background:linear-gradient(145deg,rgba(20,33,52,.98),rgba(15,26,43,.98)); border:1px solid var(--line); border-radius:14px; padding:22px; margin-bottom:18px; box-shadow:0 12px 28px rgba(0,0,0,.14); }
        .stats-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(145px,1fr)); gap:13px; margin-bottom:18px; }
        .stat-card { background:linear-gradient(145deg,#15243a,#101b2d); border:1px solid var(--line); border-radius:13px; padding:17px; min-width:0; }
        .stat-card span { display:block; color:#b4c2d5; font-size:.82rem; }
        .stat-card strong { display:block; font-size:1.8rem; letter-spacing:-.04em; margin:7px 0 2px; color:#f8fbff; font-variant-numeric:tabular-nums; }
        .stat-card small { color:var(--muted); font-size:.72rem; }
        .section-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:16px; }
        .section-heading h3 { margin:0 0 4px; }
        .pill { border:1px solid #36506b; border-radius:99px; padding:5px 10px; color:#b7c9dd; background:#14253b; font-size:.75rem; white-space:nowrap; }
        .status-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:15px; }
        .status-item { background:var(--panel2); padding:13px 14px; border-radius:9px; border:1px solid var(--line); font-size:.88rem; display:flex; justify-content:space-between; gap:10px; }
        .actions { margin-top:14px; display:flex; gap:9px; flex-wrap:wrap; }
        button { padding:10px 15px; background:#0284c7; color:white; border:1px solid #0ea5e9; border-radius:8px; font-weight:650; cursor:pointer; transition:background .15s,border-color .15s; }
        button:hover { background:#0369a1; } button:disabled { opacity:.55; cursor:not-allowed; } button.secondary { background:#24364e; border-color:#3b506b; } button.secondary:hover { background:#304761; }
        .progress-bar-bg { background:#081321; height:12px; border-radius:99px; overflow:hidden; border:1px solid var(--line); margin-top:12px; }
        .progress-bar-fill { background:linear-gradient(90deg,#0284c7,#38bdf8); height:100%; width:0%; transition:width .3s ease; }
        .sync-metrics { display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; }
        .stat-badge { font-size:.78rem; color:#cbd8e8; background:#0b1728; padding:7px 10px; border-radius:7px; border:1px solid var(--line); }
        .config-row { display:flex; justify-content:space-between; gap:16px; padding:11px 0; border-bottom:1px solid var(--line); color:#b7c5d8; font-size:.88rem; }
        .config-row strong { color:#f1f7ff; text-align:right; } .help-text { color:var(--muted); font-size:.8rem; margin:13px 0 0; }
        input[type="text"] { flex:1; min-width:0; padding:11px 13px; border-radius:8px; border:1px solid #3b506b; background:#091525; color:#fff; font-size:1rem; }
        input:focus { outline:2px solid #0ea5e9; outline-offset:1px; }
        .result-card { background:#0b1728; border:1px solid var(--line); border-radius:9px; padding:14px; margin-top:11px; }
        .result-title { font-weight:700; color:var(--accent); font-size:1rem; } .result-artist { color:#cbd5e1; font-size:.87rem; margin-top:3px; }
        .snippet { margin-top:9px; font-style:italic; color:#aebdd0; background:#14243a; padding:10px; border-radius:7px; font-family:ui-monospace,monospace; white-space:pre-wrap; font-size:.83rem; }
        code { background:#091525; padding:3px 6px; border-radius:5px; color:var(--accent); overflow-wrap:anywhere; }
        @media(max-width:720px) { body{padding:22px 14px 40px}.stats-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.card{padding:17px}.topbar{align-items:flex-start}.status-grid{grid-template-columns:1fr} }
        @media(max-width:420px) { .topbar{flex-direction:column}.account{align-items:flex-start}.stats-grid{gap:8px}.stat-card{padding:12px}.stat-card strong{font-size:1.5rem} }
    </style>
</head>
<body>
    <div class="container">
        <header class="topbar">
            <div>
                <img src="/static/logo.png"
     alt="SeekSonic"
     width="100"
     height="100"
     style="display:block; object-fit:contain;">
                <p class="subtitle">Navidrome integration and index management</p>
            </div>
            <div class="account"><span class="account-label">Signed in as</span><strong>{{ admin_user }}</strong><button class="secondary" id="btn-logout" type="button">Log out</button></div>
        </header>

        <div class="card">
            <h3>Client Setup Instructions</h3>
            <p style="font-size: 0.95rem; color: #cbd5e1;">Configure a compatible Subsonic client to use this proxy URL instead of connecting directly to Navidrome.</p>
            <p><strong>Proxy Server URL:</strong> <code>{{ proxy_url }}</code></p>
            <p class="help-text"><strong>Client compatibility:</strong> Feishin and other compatible Subsonic clients can use lyric search when they send <code>search2</code> or <code>search3</code> requests. Symfonium is not supported for this feature because it performs searches locally instead of sending those requests to the server.</p>
        </div>

        <section class="stats-grid" aria-label="Lyrics database statistics">
            <div class="stat-card"><span>Tracked tracks</span><strong id="db-total">—</strong><small>Records in sync database</small></div>
            <div class="stat-card"><span>Indexed songs</span><strong id="db-indexed">—</strong><small>Tracks with lyrics</small></div>
            <div class="stat-card"><span>No lyrics</span><strong id="db-no-lyrics">—</strong><small>Tracks checked, no lyrics found</small></div>
            <div class="stat-card"><span>Indexing errors</span><strong id="db-errors">—</strong><small>Tracks needing attention</small></div>
            <div class="stat-card"><span>Deleted tracks</span><strong id="db-deleted">—</strong><small>Removed from library</small></div>
            <div class="stat-card"><span>Meilisearch documents</span><strong id="db-documents">—</strong><small>Live search index count</small></div>
        </section>

        <div class="card">
            <div class="section-heading"><div><h3>System Status</h3><p class="section-note">Backend connectivity and synchronization</p></div><span id="sync-state" class="pill">Idle</span></div>
            <div class="status-grid">
                <div class="status-item"><strong>Navidrome:</strong> <span id="nav-status">Checking...</span></div>
                <div class="status-item"><strong>Meilisearch:</strong> <span id="meili-status">Checking...</span></div>
            </div>
            <div class="actions">
                <button class="secondary" id="btn-refresh">Refresh Status</button>
                <button id="btn-sync-all">Sync / Re-Index Now</button>
            </div>
            <p class="help-text">Last successful sync: <strong id="last-sync-time">Never</strong> · {{ sync_note }} · Dashboard refreshed: <strong id="dashboard-updated">—</strong></p>

            <div id="sync-container" style="margin-top: 1rem; display: none;">
                <div style="display: flex; justify-content: space-between; font-size: 0.9rem; color: #94a3b8;">
                    <span id="sync-action">Initializing...</span>
                    <span id="sync-counts">0 / 0</span>
                </div>
                <div class="progress-bar-bg">
                    <div id="progress-fill" class="progress-bar-fill"></div>
                </div>
                <div class="sync-metrics">
                    <span class="stat-badge">Indexed: <strong id="cnt-indexed" style="color: #4ade80;">0</strong></span>
                    <span class="stat-badge">Unchanged: <strong id="cnt-skipped" style="color: #38bdf8;">0</strong></span>
                    <span class="stat-badge">No Lyrics: <strong id="cnt-nolyrics" style="color: #facc15;">0</strong></span>
                    <span class="stat-badge">Deleted Purged: <strong id="cnt-deleted" style="color: #f87171;">0</strong></span>
                </div>
            </div>
            <div id="action-result" style="margin-top: 0.75rem; font-size: 0.9rem; color: #38bdf8;"></div>
        </div>

        <div class="card config-card">
            <div class="section-heading"><div><h3>Proxy Configuration</h3><p class="section-note">Active runtime settings</p></div></div>
            <div class="config-row"><span>Lyric matches injected per search</span><strong id="match-limit">{{ lyric_match_limit }}</strong></div>
            <div class="config-row"><span>Automatic sync</span><strong>{{ sync_note }}</strong></div>
            <p class="help-text">Change these values in your <code>.env</code> file and recreate the proxy container to apply changes.</p>
        </div>

        <div class="card">
            <h3>Manual Lyric Search Test</h3>
            <div style="display: flex;">
                <input type="text" id="query" placeholder="Type lyric phrase..." maxlength="200">
                <button id="btn-search">Search</button>
            </div>
            <div id="results"></div>
        </div>
    </div>

    <script nonce="{{ nonce }}">
        (function () {
            "use strict";
            const $ = (id) => document.getElementById(id);
            const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
            let pollInterval = null;

            function escapeHtml(value) {
                return String(value ?? "")
                    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
            }

            async function testConnection() {
                $('nav-status').innerText = 'Testing...';
                $('meili-status').innerText = 'Testing...';
                try {
                    const res = await fetch('/api/health');
                    if (!res.ok) throw new Error(res.status);
                    const data = await res.json();
                    $('nav-status').innerText = data.navidrome ? 'Connected (OK)' : 'Failed';
                    $('nav-status').style.color = data.navidrome ? '#4ade80' : '#f87171';
                    $('meili-status').innerText = data.meilisearch ? 'Connected (OK)' : 'Failed';
                    $('meili-status').style.color = data.meilisearch ? '#4ade80' : '#f87171';
                } catch (e) {
                    $('nav-status').innerText = 'Error';
                    $('meili-status').innerText = 'Error';
                }
            }

            async function startFullSync() {
                if (!confirm("Run full sync & deletion cleanup?")) return;
                try {
                    const res = await fetch('/api/admin/index-all', { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.error || data.message || res.status);
                    $('action-result').innerText = data.message;
                    startPollingStatus();
                } catch (e) {
                    alert('Failed to start sync: ' + e);
                }
            }

            function startPollingStatus() {
                $('sync-container').style.display = 'block';
                $('btn-sync-all').disabled = true;
                if (pollInterval) clearInterval(pollInterval);
                pollInterval = setInterval(checkStatus, 1000);
            }

            async function checkStatus() {
                try {
                    const res = await fetch('/api/admin/status');
                    if (!res.ok) throw new Error(res.status);
                    const data = await res.json();
                    $('sync-action').innerText = data.current_action;
                    $('sync-counts').innerText = data.processed_tracks + ' / ' + data.total_tracks;
                    const percent = data.total_tracks > 0 ? Math.round((data.processed_tracks / data.total_tracks) * 100) : 0;
                    $('progress-fill').style.width = percent + '%';
                    $('cnt-indexed').innerText = data.indexed_count;
                    $('cnt-skipped').innerText = data.skipped_count;
                    $('cnt-nolyrics').innerText = data.missing_lyrics_count;
                    $('cnt-deleted').innerText = data.deleted_count || 0;
                    $('last-sync-time').innerText = data.last_sync_time || "Never";
                    const db = data.database || {};
                    $('db-total').innerText = db.total ?? '—';
                    $('db-indexed').innerText = db.indexed ?? '—';
                    $('db-deleted').innerText = db.deleted ?? '—';
                    $('db-no-lyrics').innerText = db.no_lyrics ?? '—';
                    $('db-errors').innerText = db.error ?? '—';
                    $('db-documents').innerText = data.meilisearch_documents ?? 'Unavailable';
                    $('match-limit').innerText = data.lyric_match_limit ?? '—';
                    $('sync-state').innerText = data.is_running ? 'Sync running' : (data.last_error ? 'Attention needed' : 'Idle');
                    $('sync-state').style.color = data.is_running ? '#7dd3fc' : (data.last_error ? '#fca5a5' : '#86efac');
                    $('dashboard-updated').innerText = new Date().toLocaleTimeString();

                    if (data.is_running && !pollInterval) {
                        startPollingStatus();
                    } else if (!data.is_running && pollInterval) {
                        clearInterval(pollInterval);
                        pollInterval = null;
                        $('btn-sync-all').disabled = false;
                        $('action-result').innerText = data.last_error
                            ? 'Sync finished with errors: ' + data.last_error
                            : 'Sync cycle finished!';
                    }
                } catch (e) {
                    console.error("Error checking status:", e);
                }
            }

            function getSnippet(text, query) {
                if (!text) return "";
                const idx = text.toLowerCase().indexOf(query.toLowerCase());
                if (idx === -1) return text.substring(0, 120) + "...";
                const start = Math.max(0, idx - 40);
                const end = Math.min(text.length, idx + query.length + 60);
                return (start > 0 ? "..." : "") + text.substring(start, end) + (end < text.length ? "..." : "");
            }

            async function doSearch() {
                const q = $('query').value.trim();
                if (!q) return;
                const resDiv = $('results');
                resDiv.innerHTML = "<p style='color: #94a3b8;'>Searching...</p>";
                try {
                    const res = await fetch('/api/search/lyrics?q=' + encodeURIComponent(q));
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.error || res.status);
                    if (data.hits && data.hits.length > 0) {
                        let html = `<p style="margin-top: 1rem; color: #94a3b8;">Found ${escapeHtml(data.total)} result(s):</p>`;
                        data.hits.forEach(hit => {
                            html += `
                                <div class="result-card">
                                    <div class="result-title">${escapeHtml(hit.title)}</div>
                                    <div class="result-artist">${escapeHtml(hit.artist)} — <em>${escapeHtml(hit.album)}</em></div>
                                    <div class="snippet">"...${escapeHtml(getSnippet(hit.lyrics, q))}..."</div>
                                    <div style="margin-top: 0.5rem; font-size: 0.8rem; color: #64748b;">Navidrome ID: ${escapeHtml(hit.id)}</div>
                                </div>
                            `;
                        });
                        resDiv.innerHTML = html;
                    } else {
                        resDiv.innerHTML = "<p style='margin-top: 1rem; color: #f87171;'>No matching lyrics found.</p>";
                    }
                } catch (e) {
                    resDiv.innerHTML = `<p style='color: #f87171;'>Search error: ${escapeHtml(e.message || e)}</p>`;
                }
            }

            $('btn-logout').addEventListener('click', async () => {
                try {
                    const response = await fetch('/logout', { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } });
                    if (!response.ok) throw new Error('Logout failed');
                    window.location.assign('/login');
                } catch (error) {
                    $('action-result').innerText = error.message || 'Logout failed';
                }
            });
            $('btn-refresh').addEventListener('click', () => { testConnection(); checkStatus(); });
            $('btn-sync-all').addEventListener('click', startFullSync);
            $('btn-search').addEventListener('click', doSearch);
            $('query').addEventListener('keypress', (e) => { if (e.key === 'Enter') doSearch(); });

            window.addEventListener('load', () => { testConnection(); checkStatus(); setInterval(checkStatus, 15000); });
        })();
    </script>
</body>
</html>
"""


@app.route("/")
@admin_required
def index():
    g.csp_nonce = secrets.token_urlsafe(16)
    sync_note = (f"Runs every {SYNC_INTERVAL_MINUTES} min" if SYNC_INTERVAL_MINUTES > 0
                 else "Automatic sync disabled")
    return render_template_string(
        HTML_TEMPLATE, nonce=g.csp_nonce, csrf_token=session.get("csrf_token", ""), sync_note=sync_note,
        proxy_url=request.host_url.rstrip("/"), admin_user=ADMIN_USER,
        lyric_match_limit=LYRIC_MATCH_LIMIT,
    )


@app.route("/healthz")
def healthz():
    """Unauthenticated liveness endpoint; exposes no dependency or secret state."""
    return jsonify({"status": "ok"})


@app.route("/api/health")
@admin_required
def health():
    nav_ok = subsonic_ok(call_subsonic_internal("ping"))
    try:
        meili_ok = http_session().get(f"{MEILISEARCH_URL}/health", timeout=3).status_code == 200
    except requests.RequestException:
        meili_ok = False
    return jsonify({"navidrome": nav_ok, "meilisearch": meili_ok})


@app.route("/api/admin/index-all", methods=["POST"])
@admin_required
def admin_index_all():
    origin = request.headers.get("Origin")
    if origin:
        try:
            if urlsplit(origin).netloc != request.host:
                return jsonify({"error": "Cross-origin request rejected"}), 403
        except ValueError:
            return jsonify({"error": "Invalid Origin header"}), 403
    fetch_site = request.headers.get("Sec-Fetch-Site")
    if fetch_site and fetch_site not in ("same-origin", "none"):
        return jsonify({"error": "Cross-origin request rejected"}), 403
    if not start_sync_in_background():
        return jsonify({"status": "already_running", "message": "Sync is already in progress."})
    return jsonify({"status": "started", "message": "Library sync & reconciliation started."})


@app.route("/api/admin/status")
@admin_required
def admin_status():
    payload = dict(indexing_status)
    payload["database"] = get_database_stats()
    payload["lyric_match_limit"] = LYRIC_MATCH_LIMIT
    payload["sync_interval_minutes"] = SYNC_INTERVAL_MINUTES
    try:
        response = http_session().get(
            f"{MEILISEARCH_URL}/indexes/{INDEX_NAME}/stats",
            headers=get_meili_headers(), timeout=3,
        )
        response.raise_for_status()
        payload["meilisearch_documents"] = response.json().get("numberOfDocuments")
    except (requests.RequestException, ValueError):
        payload["meilisearch_documents"] = None
    return jsonify(payload)


@app.route("/api/search/lyrics")
@admin_required
def search_lyrics():
    q = request.args.get("q", "").strip()[:200]
    if not q:
        return jsonify({"query": "", "total": 0, "hits": []})
    try:
        res = http_session().post(
            f"{MEILISEARCH_URL}/indexes/{INDEX_NAME}/search",
            headers=get_meili_headers(), json={"q": q, "limit": 20}, timeout=10,
        )
        res.raise_for_status()
        hits = res.json().get("hits", [])
        return jsonify({"query": q, "total": len(hits), "hits": hits})
    except Exception as e:
        log.error("Lyric search failed: %s", type(e).__name__)
        return jsonify({"error": "Search backend unavailable"}), 502


__all__ = ['HTML_TEMPLATE', 'index', 'healthz', 'health', 'admin_index_all', 'admin_status', 'search_lyrics']
