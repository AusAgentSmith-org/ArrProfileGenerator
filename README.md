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

### Testing with Local Sonarr/Radarr Stack

For testing or development, use the included Docker test stack:

```bash
# Initialize test environment (Sonarr + Radarr)
cd test
./init-stack.sh

# Run wizard with auto-loaded credentials from teststack
cd ..
python wizard.py --teststack

# Cleanup when done
cd test
./cleanup-stack.sh
```

See [`test/README.md`](test/README.md) for detailed test stack documentation.

## What It Does

1. Fetches the latest TRaSH Guides tier data from GitHub
2. Asks 12 questions about your preferences (resolution, codec, audio, HDR, strictness, etc.)
3. Creates custom formats and quality profiles in Sonarr/Radarr
4. Optionally bulk-updates all existing series/movies to use the new profile

## CLI Options

```bash
python wizard.py                # Interactive mode - prompts for all settings
python wizard.py --teststack    # Test mode - auto-loads credentials from test/.env
```

In `--teststack` mode:
- Sonarr and Radarr URLs and API keys are automatically loaded from `test/.env`
- No need to manually enter connection details
- Useful for testing and development

## Building a Standalone Binary

### Linux/macOS
```bash
pip install pyinstaller
./build.sh
```
Output: `./dist/profsync-wizard`

### Windows (PowerShell)
```powershell
pip install pyinstaller
pyinstaller build.spec --clean -y
```
Output: `dist\profsync-wizard.exe`

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
