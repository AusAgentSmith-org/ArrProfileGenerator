# ProfSync

**Stop manually copying quality profiles.** ProfSync is a CLI wizard that configures Sonarr and Radarr quality profiles for you, using real data from TRaSH Guides — in under a minute.

## The Problem

Setting up quality profiles in Sonarr and Radarr is tedious and error-prone. You're expected to:

- Read through TRaSH Guides (which are excellent, but dense)
- Manually create a dozen custom formats with regex patterns
- Assign scores to each one based on your setup
- Configure quality cutoffs that match your resolution and storage
- Repeat the whole thing for Radarr
- Redo it when TRaSH updates their tier lists

Most people either copy someone else's config blindly or give up and use defaults. Neither gets you the best quality your setup can actually handle.

## What ProfSync Does

ProfSync asks 12 questions about your setup — what resolution you want, what devices you use, whether you care about lossless audio or HDR — and builds a complete, optimized configuration:

- **Custom formats** for TRaSH release group tiers (Tier 01/02/03/LQ) with proper scoring
- **Codec/audio/HDR preferences** tuned to your hardware (HEVC boost for modern devices, x264 preference for legacy)
- **Quality profiles** with the right qualities enabled, correct cutoffs, and format scores wired up
- **Bulk updates** to assign the new profile to all your existing series and movies

It talks directly to the Sonarr/Radarr API. No config files to copy, no YAML to edit, no manual steps.

## How It Works

```
TRaSH Guides (GitHub) ──→ ProfSync Wizard ──→ Sonarr/Radarr API
                              │
                         12 questions about
                         your setup & preferences
```

1. Fetches the latest TRaSH Guides tier data (277+ release groups across 4 tiers)
2. Asks about your resolution, devices, audio, HDR, storage, and quality strictness
3. Generates custom formats with regex-matched release group scoring
4. Creates a quality profile with the right qualities enabled and cutoff set
5. Pushes everything to Sonarr and/or Radarr via their v3 API
6. Optionally bulk-updates all existing library items to use the new profile

## Quick Start

```bash
git clone https://gitea.sprooty.com/sprooty/profsync.git
cd profsync
pip install -e .
python wizard.py
```

The wizard will prompt for your Sonarr/Radarr URLs and API keys, then walk you through the configuration.

### What You'll Be Asked

| Question | Why It Matters |
|----------|---------------|
| Target resolution (1080p / 4K / both) | Controls which qualities are enabled and where the cutoff sits |
| Playback environment (home / remote) | Remote streaming may benefit from smaller, more compatible files |
| Device capability (modern / mixed / legacy) | Modern devices get HEVC/x265 boosts; legacy gets x264 preference |
| HDR support (full / HDR10 / none) | Adds scoring for HDR10 and Dolby Vision custom formats |
| Audio preference (lossless / standard) | Boosts TrueHD Atmos, DTS-HD MA when you have the hardware for it |
| Include remux (yes / no) | Remux releases are 30-80 GB — only enable if you have the storage |
| Storage constraint (none / moderate / tight) | Tight mode strips Bluray/Remux, keeps only WEB sources |
| Quality strictness (strict / balanced / permissive) | Controls how aggressively low-tier groups are penalized |
| Auto-upgrade (yes / no) | Whether to upgrade when a better release appears |

## CLI Options

```bash
python wizard.py                # Interactive — prompts for everything
python wizard.py --teststack    # Test mode — auto-loads credentials from test/.env
```

## Building a Standalone Binary

```bash
pip install pyinstaller
./build.sh              # Linux/macOS → ./dist/profsync-wizard
```

Windows:
```powershell
pip install pyinstaller
pyinstaller build.spec --clean -y   # → dist\profsync-wizard.exe
```

## Architecture

```
wizard.py                    # Entry point
├── src/
│   ├── main.py              # Orchestration — connects to apps, applies profiles
│   ├── questions.py         # Interactive prompts (questionary)
│   ├── arr_client.py        # Sonarr/Radarr v3 API client
│   ├── profile_builder.py   # Custom format + quality profile generation
│   └── trash_fetcher.py     # Fetches TRaSH Guides tier data from GitHub
```

### Scoring Model

ProfSync uses a **TRaSH-blended scoring** approach with three strictness levels:

| Tier | Strict | Balanced | Permissive |
|------|--------|----------|------------|
| Tier 01 (best groups) | +1500 | +1500 | +1500 |
| Tier 02 | -2000 | +400 | +200 |
| Tier 03 | -4000 | -100 | +50 |
| LQ (low quality) | -10000 | -10000 | -10000 |

On top of group tier scores, codec/audio/HDR custom formats add conditional bonuses (e.g., +200 for lossless audio, +100 for HEVC, +150 for Dolby Vision).

## Requirements

- Python 3.10+
- Sonarr v4+ or Radarr v6+ with API access
- `questionary >= 2.0`, `requests >= 2.31`

## Test Stack

A Docker-based test environment is included for development and validation. See [`test/README.md`](test/README.md) for full details.

```bash
cd test/
./init-stack.sh                  # Spins up Sonarr + Radarr with 20 series + 20 movies
cd ..
python wizard.py --teststack     # Run the wizard against the test stack
cd test/
./validate-wizard.sh             # Verify profiles were created correctly
```

The test stack runs Sonarr on port 8989 and Radarr on port 7878 with authentication disabled. Requires Docker and ~500 MB disk space.
