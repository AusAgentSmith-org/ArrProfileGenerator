# ProfSync

Automated release group quality profiling pipeline. An alternative to TRaSH Guides that derives quality rankings from data (PreDB metadata + NFO file analysis) instead of manual community curation.

## Project Goal

Build a database of release group quality profiles by:
1. Continuously collecting scene releases from PreDB sources
2. Parsing release names to extract metadata (resolution, codec, source, group, audio)
3. Fetching and parsing NFO files for actual encode quality metrics (CRF, bitrate, audio format)
4. Aggregating per-group statistics to compute data-driven quality tiers

Future: a Q&A wizard that configures Sonarr/Radarr for users based on this data.

## Scope

- English-language content only (movies and TV shows)
- No anime, no foreign language content
- Scene and P2P release groups

## Architecture

Docker Compose stack with 4 Python services + Postgres + Redis:

```
api.predb.net → collector → Redis queue → parser → Postgres
                                                      ↓
                                              Redis queue → nfo-fetcher → Postgres
                                                                            ↓
                                                                      analyzer (periodic) → group_profiles
```

### Services

| Service | Purpose | Key Files |
|---------|---------|-----------|
| **collector** | Polls api.predb.net REST API every 30s for new releases + backfills historical data by section | `services/collector/src/websocket_client.py` (poller), `backfill.py` |
| **parser** | Consumes raw releases from Redis, parses with guessit, filters to English movies/TV, writes to Postgres | `services/parser/src/processor.py`, `filters.py` |
| **nfo-fetcher** | Fetches NFO files from xREL API, parses quality metrics (CRF, bitrate, audio) via regex | `services/nfo-fetcher/src/fetcher.py`, `nfo_parser.py` |
| **analyzer** | Periodic (hourly) aggregation — computes per-group quality profiles and auto-assigns tiers | `services/analyzer/src/profiler.py` |
| **migrate** | One-shot: creates all DB tables from SQLAlchemy models, exits | `services/migrate/migrate.py` |

### Shared Package

`shared/profsync/` is installed into every service container:
- `config.py` — Pydantic settings from env vars
- `models.py` — SQLAlchemy models (releases, parsed_releases, nukes, release_quality, group_profiles)
- `db.py` — Session factory
- `queue.py` — Redis queue helpers (QUEUE_RAW_RELEASES, QUEUE_NFO_NEEDED)
- `logging.py` — Structured logging setup

### Database Tables

- **releases** — Raw release data from PreDB (name, team, category, pre timestamp)
- **nukes** — Nuke/unnuke status per release
- **parsed_releases** — Parsed metadata from release names (title, resolution, codec, group, audio, source)
- **release_quality** — Quality metrics extracted from NFO files (CRF, bitrate, audio format, encode ratio)
- **group_profiles** — Aggregated per-group stats by resolution and media type, with computed quality tiers

## Data Source

Originally built for predb.ovh (WebSocket + REST API). Switched to **api.predb.net** REST API after predb.ovh went down.

Key differences from the original design:
- Collector now polls every 30s instead of using WebSocket
- API field names differ: `release` (not `name`), `group` (not `team`), `section` (not `cat`), `pretime` (unix timestamp, not ISO)
- Backfill iterates per-section (e.g., X264, TV-WEB-HD-X265, BLURAY, UHD) with 100 pages each
- Rate limit: 60 requests per 60 seconds
- Nuke status indicated by `status` field (0=ok, 1=nuked) rather than a nested nuke object

## Running

```bash
cp .env.example .env   # configure XREL_API_KEY etc.
docker compose up -d
docker compose logs -f
```

All services use `dns: [127.0.0.11, 1.1.1.1, 1.0.0.1]` for reliable resolution in WSL2/Docker environments.

## Key Design Decisions

- **Database is the product** — we don't output TRaSH-compatible JSON. The rich data model (per-release quality metrics, per-group profiles by resolution) would lose too much fidelity compressed into TRaSH's regex-match-and-static-score format.
- **Services are decoupled via Redis queues** — each service manages its own rate limits and can restart independently.
- **NFO parsing is best-effort** — `parse_confidence` (0.0-1.0) tracks how many fields were extracted. Groups with low NFO coverage get lower tier confidence.
- **Quality tiers are composite scores** — weighted combination of nuke rate, CRF values, audio format distribution, consistency, and data volume. Tiers: A+, A, B+, B, C+, C, D, F.

## Git

- Remote: https://gitea.sprooty.com/sprooty/profsync
- User: sprooty, email: gitea@sprooty.com
