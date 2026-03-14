# ProfSync

CLI wizard that configures Sonarr and Radarr quality profiles using live TRaSH Guides data. Asks 12 questions about your setup, then pushes custom formats and a quality profile directly via the Sonarr/Radarr API.

## Project Goal

Make quality profile setup effortless. Instead of manually reading TRaSH Guides and creating custom formats by hand, ProfSync asks about your hardware, preferences, and storage — then does everything automatically.

## Scope

- Sonarr v4+ and Radarr v6+ (detects Sonarr v3 and adapts)
- English-language content (movies and TV shows)
- TRaSH Guides tier data as the quality source

## Architecture

Single Python CLI — no database, no background services, no Docker (except for the test stack).

```
wizard.py                    # Entry point
├── src/
│   ├── main.py              # Orchestration — connects to apps, applies profiles
│   ├── questions.py         # Interactive prompts (questionary)
│   ├── arr_client.py        # Sonarr/Radarr v3 API client
│   ├── profile_builder.py   # Custom format + quality profile generation
│   └── trash_fetcher.py     # Fetches TRaSH Guides tier data from GitHub
```

### Data Flow

```
TRaSH Guides (GitHub JSON) → trash_fetcher.py → profile_builder.py → arr_client.py → Sonarr/Radarr API
                                                       ↑
                                              questions.py (UserProfile)
```

### Key Modules

| Module | Purpose |
|--------|---------|
| `questions.py` | 12 interactive prompts → `UserProfile` dataclass |
| `trash_fetcher.py` | Fetches tier JSON from TRaSH GitHub, caches to `~/.cache/profsync/` (24h TTL), returns `dict[str, list[str]]` of tier→groups |
| `profile_builder.py` | Builds custom format JSON (one per tier + codec/audio/HDR conditionals) and quality profile JSON |
| `arr_client.py` | REST client for Sonarr/Radarr v3 API: verify, backup, upsert CFs, create/update profiles, bulk-update library |
| `main.py` | Orchestrates: run wizard → fetch tiers → build CFs → apply to each app → optional bulk update |

## Scoring Model

TRaSH-blended scoring with three strictness levels:

| Tier | Strict | Balanced | Permissive |
|------|--------|----------|------------|
| Tier 01 (best groups) | +1500 | +1500 | +1500 |
| Tier 02 | -2000 | +400 | +200 |
| Tier 03 | -4000 | -100 | +50 |
| LQ (low quality) | -10000 | -10000 | -10000 |

Codec/audio/HDR custom formats add conditional bonuses (e.g., +200 lossless audio, +100 HEVC, +150 Dolby Vision).

## Running

```bash
pip install -e .
python wizard.py                # Interactive
python wizard.py --teststack    # Test mode — uses test/.env credentials
```

## Building

```bash
pip install pyinstaller
./build.sh              # Linux/macOS → ./dist/profsync-wizard
```

## Test Stack

Docker-based Sonarr + Radarr for development validation:

```bash
cd test/
./init-stack.sh                  # Spins up Sonarr + Radarr with 20 series + 20 movies
cd ..
python wizard.py --teststack     # Run wizard against test stack
cd test/
./validate-wizard.sh             # Verify profiles were created correctly
```

## Dependencies

- Python 3.10+
- `questionary >= 2.0`, `requests >= 2.31`

## Git

- Remote: https://gitea.sprooty.com/sprooty/profsync
- User: sprooty, email: gitea@sprooty.com
