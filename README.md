# ProfSync Wizard

Standalone CLI wizard to configure Sonarr and Radarr using TRaSH Guides data.

## Quick Start

### Installation

```bash
pip install -e .
```

### Running the Wizard

```bash
python wizard.py
# or
profsync
```

## What It Does

1. Fetches the latest TRaSH Guides tier data from GitHub
2. Asks 12 questions about your preferences (resolution, codec, audio, HDR, strictness, etc.)
3. Creates custom formats and quality profiles in Sonarr/Radarr
4. Optionally bulk-updates all existing series/movies to use the new profile

## Building a Standalone Binary

```bash
pip install pyinstaller
./build.sh
```

Output:
- Linux/macOS: `./dist/profsync-wizard`
- Windows: `./dist/profsync-wizard.exe`

## Architecture

```
wizard.py           # Entry point
├── src/
│   ├── main.py     # Orchestration + bulk update logic
│   ├── questions.py # Interactive prompts
│   ├── arr_client.py # Sonarr/Radarr API wrapper
│   ├── profile_builder.py # CF + quality profile generation
│   └── trash_fetcher.py # TRaSH Guides data fetching
```

## Requirements

- Python 3.10+
- questionary >= 2.0
- requests >= 2.31
- Sonarr v4+ (or Radarr) with API access
