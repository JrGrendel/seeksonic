<p align="center">
  <img src="assets/logo.png" alt="SeekSonic Logo" width="220">
</p>

# SeekSonic

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)
![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)
![Navidrome](https://img.shields.io/badge/Navidrome-Subsonic%20API-8A2BE2)
![Meilisearch](https://img.shields.io/badge/Meilisearch-v1.56.2-ff5caa?logo=meilisearch&logoColor=white)

**Search your Navidrome music library by the words in a song's lyrics.**

SeekSonic is a Subsonic-compatible proxy that adds lyric-based matches to Navidrome's `search2` and `search3` API responses. It uses Meilisearch to search an index of your lyrics, then asks Navidrome to resolve each matching track using the credentials of the user who made the search. Other Subsonic API requests are passed through to Navidrome.

SeekSonic is designed for Subsonic clients that send server-side `search2` or `search3` requests.

> **Client compatibility:** Feishin and other clients that use the Subsonic `search2`/`search3` endpoints can use lyric search. Symfonium currently performs its search locally rather than sending these requests to the server, so SeekSonic's lyric-search feature does **not** work with Symfonium. Symfonium can still connect to Navidrome.

## ⚠️ Disclaimer: 100% Organic AI Slop™

I had a problem. I needed a solution. So I spent an entire week fighting, bleeding, crying, and occasionally begging ChatGPT to make this damn thing work.

There were bugs, hallucinations, broken promises, questionable code, and approximately 500 variations of "You're absolutely right, let's fix that."

Somehow, after a week of suffering, this project was born.

Is it elegant? Probably not. Is it optimized? Don't ask. Does it work? Surprisingly, yes.

This project is a beautiful collaboration between human desperation and artificial intelligence with an overconfidence problem.

🛠️ Do Whatever You Want With It

Use it, fork it, modify it, redistribute it, break it, fix it, or build something better. No permission needed. Credit is appreciated but not required.

❤️ Credits
- Me: For the idea, suffering, and questionable life choices.
- ChatGPT: For the code, the hallucinations, and the emotional rollercoaster.
- Coffee: The real MVP.

If this saves you even an hour of suffering, my week wasn't entirely wasted.

Imagined by a human. Written with AI. Debugged through tears.

## Contents

- [Features](#features)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Accessing SeekSonic from other devices](#accessing-seeksonic-from-other-devices)
- [Configure your Subsonic client](#configure-your-subsonic-client)
- [Configuration reference](#configuration-reference)
- [Dashboard and synchronization](#dashboard-and-synchronization)
- [Security and privacy](#security-and-privacy)
- [Troubleshooting](#troubleshooting)
- [Data, backups, and upgrades](#data-backups-and-upgrades)
- [Contributing and support](#contributing-and-support)
- [License](#license)

## Features

- **Lyric search:** adds lyric matches to Subsonic `search2` and `search3` responses.
- **Permission-aware results:** every lyric hit is resolved through Navidrome using the requesting listener's own credentials. A user cannot discover a track they are not allowed to access in Navidrome.
- **Normal search is preserved:** Navidrome's regular results are retained, with duplicate tracks removed.
- **Configurable result limit:** control how many lyric matches are injected per search with `LYRIC_MATCH_LIMIT`.
- **Automatic indexing:** a background sync indexes lyrics and reconciles changed or deleted tracks.
- **Management dashboard:** view synchronization and database statistics, trigger a full sync, and test lyric queries.
- **Container hardening:** the supplied Compose configuration runs the proxy as a non-root user with a read-only root filesystem, dropped Linux capabilities, and resource limits.
- **Telemetry opt-out:** Meilisearch anonymous telemetry is disabled by default.

## How It Works

SeekSonic acts as a bridge between compatible Subsonic clients, Navidrome, and Meilisearch.

```text
                 ┌──────────────────────┐
                 │   Subsonic Client    │
                 │       Feishin        │
                 └──────────┬───────────┘
                            │
                     Search request
                            │
                            ▼
                 ┌──────────────────────┐
                 │      SeekSonic       │
                 │    Search Proxy      │
                 └──────────┬───────────┘
                            │
                  Search lyrics index
                            │
                            ▼
                 ┌──────────────────────┐
                 │     Meilisearch      │
                 │    Lyrics Index      │
                 └──────────┬───────────┘
                            │
                    Matching track IDs
                            │
                            ▼
                 ┌──────────────────────┐
                 │      SeekSonic       │
                 │  Access Verification │
                 └──────────┬───────────┘
                            │
                 Verify using listener's
                    Navidrome credentials
                            │
                            ▼
                 ┌──────────────────────┐
                 │      Navidrome       │
                 │  Library Permissions │
                 └──────────┬───────────┘
                            │
                     Authorized tracks
                            │
                            ▼
                 ┌──────────────────────┐
                 │   Subsonic Client    │
                 │   Search Results     │
                 └──────────────────────┘
```

### Search process

1. The client sends a compatible Subsonic `search2` or `search3` request to SeekSonic.
2. SeekSonic searches the Meilisearch lyrics index for matching tracks.
3. Matching track IDs are checked against Navidrome using the requesting listener's credentials.
4. Only tracks the listener is authorized to access are returned.
5. SeekSonic adds the authorized lyric matches to the normal Navidrome search response.

This approach allows lyric-based discovery without bypassing Navidrome's library permissions.


For a lyric search:

1. The client sends a `search2` or `search3` request to SeekSonic.
2. SeekSonic forwards the request to Navidrome. Navidrome authenticates the listener and returns its normal search response.
3. SeekSonic searches the Meilisearch lyric index.
4. Each matching track ID is checked with Navidrome using the original listener's credentials.
5. SeekSonic adds accessible lyric matches to the response, removes duplicates, and returns the combined result.

The shared lyric index is **not** an authorization source. Navidrome remains responsible for deciding which tracks each listener can access.

Lyric matches are added on the first results page (`songOffset=0`). Requests for later pages are passed through unchanged.

## Requirements

- Docker Engine
- Docker Compose v2 (`docker compose`)
- A reachable Navidrome server
- A dedicated Navidrome account for indexing, with read access to the libraries and lyrics you want indexed
- A Subsonic-compatible client that sends server-side `search2` or `search3` requests to use lyric search

The Navidrome URL must be reachable **from inside the SeekSonic container**. `localhost` inside the container refers to the container itself, not the host or another container.

## Quick start

### Accessing SeekSonic from other devices

By default, SeekSonic binds to `127.0.0.1` on the Docker host for security. This means the proxy is only accessible from the host itself or through a reverse proxy running on the same machine.

If you want to access SeekSonic directly from other devices on your local network (for example, from Feishin on another computer), edit your `.env` file:

```env
PROXY_BIND=0.0.0.0
PROXY_PORT=8788
```

Redeploy the stack, then access the proxy using the Docker host's LAN IP address:

```text
http://YOUR_SERVER_IP:8788
```

For example:

```text
http://192.168.1.100:8788
```

**Security note:** Binding to `0.0.0.0` exposes the proxy on all host network interfaces. Restrict access using your firewall and avoid exposing the port directly to the public internet. For remote access, use a properly configured reverse proxy or VPN.

### 1. Get the project files

Clone this repository or download and extract its source archive. Run the following commands from the directory containing `docker-compose.yml`:

```sh
cp .env.example .env
```

### 2. Configure `.env`

Set these values in `.env`:

- `NAVIDROME_URL`: Navidrome's base URL as reachable from the SeekSonic container.
- `NAVIDROME_USER` and `NAVIDROME_PASSWORD`: credentials for the dedicated indexing account.
- `MEILI_MASTER_KEY`: a strong secret used by both SeekSonic and its internal Meilisearch service.
- `ADMIN_PASSWORD`: the password for the SeekSonic dashboard.
- `ADMIN_SESSION_SECRET`: a separate secret used to sign dashboard sessions.

Generate secrets with:

```sh
openssl rand -hex 32
```

Run this command separately for `MEILI_MASTER_KEY`, `ADMIN_PASSWORD`, and `ADMIN_SESSION_SECRET`, then put each generated value in the corresponding `.env` variable. Do not reuse your Navidrome password for the dashboard.

`ADMIN_PASSWORD` must contain at least 8 characters. `ADMIN_SESSION_SECRET` must contain at least 32 characters. `MEILI_MASTER_KEY` must contain at least 8 characters.

Example `.env` values:

```dotenv
NAVIDROME_URL=http://navidrome:4533
NAVIDROME_USER=lyrics-indexer
NAVIDROME_PASSWORD=replace-this

MEILI_MASTER_KEY=replace-with-a-long-random-secret

ADMIN_USER=admin
ADMIN_PASSWORD=replace-with-a-long-random-password
ADMIN_SESSION_SECRET=replace-with-a-separate-random-secret

PROXY_BIND=127.0.0.1
PROXY_PORT=8788

SYNC_INTERVAL_MINUTES=30
LYRIC_MATCH_LIMIT=5

# Optional: Meilisearch telemetry is disabled by default.
MEILI_NO_ANALYTICS=true
```

The example Navidrome hostname works only if your Compose network can resolve and reach a service named `navidrome`. If Navidrome runs elsewhere, replace it with the appropriate host name or IP address.

### 3. Pull and start SeekSonic

Pull and start the services with:

```sh
docker compose pull
docker compose up -d
```

The supplied Compose file uses `ghcr.io/jrgrendel/seeksonic:main`. If you fork the repository, update the `image` value in `docker-compose.yml` to your own GHCR image name.

To build the proxy image locally instead of pulling it, use:

```sh
docker compose build seeksonic
docker compose up -d
```

Check container status and logs:

```sh
docker compose ps
docker compose logs -f seeksonic
```

The supplied Compose file uses `ghcr.io/jrgrendel/seeksonic:main` and publishes the proxy on `127.0.0.1:8788` by default. The container listens internally on port `8080`.

If you are running from source, build the exact image tag referenced by Compose first:

```sh
docker build -t ghcr.io/jrgrendel/seeksonic:main .
docker compose up -d
```

### 4. Open the dashboard

Open `http://127.0.0.1:8788/` and sign in with `ADMIN_USER` and `ADMIN_PASSWORD`. The dashboard is served at `/`; `/admin` is not a dashboard route. The first scheduled synchronization starts when the application starts, unless automatic synchronization is disabled.

### 5. Point your client to SeekSonic

In your Subsonic client, change the server address from Navidrome to the SeekSonic proxy address. Keep the listener's **own Navidrome username and password**; do not use the indexing account for normal listening.

With the default settings, the proxy URL is `http://127.0.0.1:8788`. If the client is on another device, configure a suitable bind address and network access as described in [Security and privacy](#security-and-privacy).

## Configure your Subsonic client

Use the SeekSonic proxy as the Subsonic server URL. SeekSonic forwards normal Subsonic API calls to Navidrome and intercepts `search2` and `search3` to add lyric matches.

- Use each listener's regular Navidrome credentials.
- Use the indexing account only for background library synchronization.
- Make sure the indexing account can read the music libraries and lyrics that should appear in lyric search.
- If your client offers a choice of search behavior, it must send searches to the server using `search2` or `search3`.

## Configuration reference

All variables are supplied through `.env` and passed to the containers by `docker-compose.yml`.

| Variable | Required | Default | Description |
|---|:---:|---|---|
| `NAVIDROME_URL` | Yes | `http://navidrome:4533` | Navidrome base URL, reachable from the proxy container |
| `NAVIDROME_USER` | Yes | — | Dedicated Navidrome indexing username |
| `NAVIDROME_PASSWORD` | Yes | — | Indexing account password |
| `MEILI_MASTER_KEY` | Yes | — | Shared master key for the internal Meilisearch service |
| `ADMIN_USER` | Yes | `admin` | Dashboard username |
| `ADMIN_PASSWORD` | Yes | — | Dashboard password; minimum 8 characters |
| `ADMIN_SESSION_SECRET` | Yes | — | Session signing secret; minimum 32 characters |
| `SESSION_COOKIE_SECURE` | No | `false` | Set to `true` when the dashboard is accessed over HTTPS |
| `PROXY_BIND` | No | `127.0.0.1` | Host interface to which the proxy port is published |
| `PROXY_PORT` | No | `8788` | Host port published for the proxy; container port remains `8080` |
| `SYNC_INTERVAL_MINUTES` | No | `30` | Minutes between automatic syncs; `0` disables scheduled sync |
| `SYNC_WORKERS` | No | `4` | Parallel workers for library synchronization |
| `LYRIC_MATCH_LIMIT` | No | `5` | Maximum lyric matches injected per search; range 1–50 |
| `WAITRESS_THREADS` | No | `8` | Web server worker threads |
| `MEILI_TASK_TIMEOUT` | No | `120` | Maximum wait, in seconds, for Meilisearch tasks |
| `LOG_LEVEL` | No | `INFO` | Python logging level |
| `MEILI_NO_ANALYTICS` | No | `true` | Disable Meilisearch anonymous telemetry; set `false` to opt in |

The Compose file sets `MEILISEARCH_URL` internally to `http://seeksonic-meili:7700`. Meilisearch is not published to the host.

## Dashboard and synchronization

The dashboard at `/` provides:

- Current synchronization status and progress
- SQLite database statistics and Meilisearch document count
- Last synchronization information
- A control to start a full library synchronization
- A lyric-search test field

The dashboard requires login. Browser sessions expire after 12 hours. Logging out invalidates the current session.

Automatic synchronization starts when SeekSonic starts and then repeats according to `SYNC_INTERVAL_MINUTES`. Set it to `0` to disable scheduled synchronization; you can still trigger a manual synchronization from the dashboard.

`LYRIC_MATCH_LIMIT` controls the maximum number of lyric matches added to each first-page search. It does not set the total number of results returned by Navidrome. The client-requested `songCount` and the regular Navidrome results also affect the final response.

## Security and privacy

- **Use a dedicated indexing account.** Give it read access only to the Navidrome libraries you intend to index. Listener permissions are still enforced separately for every lyric hit.
- **Keep the proxy private by default.** The default host binding is `127.0.0.1`, suitable for a reverse proxy running on the same host. To make it reachable on your LAN, set `PROXY_BIND=0.0.0.0` and restrict access with your firewall.
- **Use HTTPS for remote access.** Put the proxy behind a trusted HTTPS reverse proxy when accessing it over an untrusted network. When HTTPS is enabled, set `SESSION_COOKIE_SECURE=true`.
- **Do not expose Meilisearch.** The supplied Compose configuration exposes port `7700` only to the internal Docker network. Do not publish it directly to the internet.
- **Container restrictions:** the proxy container runs as a non-root user, uses a read-only root filesystem, drops Linux capabilities, enables `no-new-privileges`, and has memory, process, and temporary-filesystem limits configured in Compose.

Meilisearch anonymous telemetry is disabled by default with `MEILI_NO_ANALYTICS=true`. To opt in, set `MEILI_NO_ANALYTICS=false` in `.env` and recreate the Meilisearch container:

```sh
docker compose up -d --force-recreate seeksonic-meili
```

## Troubleshooting

### The proxy cannot connect to Navidrome

Check that `NAVIDROME_URL` is reachable from inside the SeekSonic container. Do not use `localhost` unless Navidrome is running in the same container.

### The dashboard does not open

- Use the root URL, for example `http://127.0.0.1:8788/`.
- Check `docker compose ps` and `docker compose logs seeksonic`.
- Confirm that `ADMIN_USER`, `ADMIN_PASSWORD`, and `ADMIN_SESSION_SECRET` are set. The application will not start if required credentials are missing or too short.

### Lyric search returns no matches

- Confirm that the initial synchronization has completed.
- Check the dashboard's database and Meilisearch statistics.
- Confirm that the indexing account can access the relevant library and its lyrics.
- Test a distinctive lyric phrase in the dashboard.
- Confirm that your client sends server-side `search2` or `search3` requests to SeekSonic.

### Normal search works but lyric search does not

Check that the client is pointed at SeekSonic rather than directly at Navidrome and that it uses `search2` or `search3`. Clients that perform local-only searches, including Symfonium's current search behavior, cannot use this lyric-search integration.

### Check the health endpoint

The unauthenticated liveness endpoint is `http://127.0.0.1:8788/healthz`. It confirms that the proxy process is responding. The dashboard also checks its Navidrome and Meilisearch connections.

## Data, backups, and upgrades

The Compose file creates two named volumes:

- `proxy_data`: SQLite synchronization state
- `meili_data`: Meilisearch lyric index

Back up both volumes before upgrades or maintenance. The Meilisearch index is persistent data; when changing Meilisearch versions, follow the official [Meilisearch update and migration guidance](https://www.meilisearch.com/docs/learn/update_and_migration/updating), including its dump/import procedure where required.

Do not run `docker compose down -v` unless you intentionally want to delete the persistent volumes and rebuild the index from scratch.

## Contributing and support

Bug reports, feature requests, and contributions are welcome. When reporting an issue, include relevant SeekSonic logs and configuration details, but **remove passwords, API keys, tokens, private URLs, and other sensitive information** first.

The project's AI-assisted development background and credits are described in [DISCLAIMER.md](DISCLAIMER.md).

## License

SeekSonic is released under the [MIT License](LICENSE).
