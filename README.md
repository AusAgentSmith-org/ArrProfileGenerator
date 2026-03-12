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

For testing or development, use the included Docker test stack with pre-populated libraries:

#### Setup

```bash
# Initialize test environment (Sonarr + Radarr with 531 series + 1209 movies)
cd test
./init-stack.sh
```

This will:
1. ✅ Start Sonarr (port 8989) and Radarr (port 7878) containers
2. ✅ Create root folders and quality profiles
3. ✅ Configure authentication: **testuser** / **testpass123**
4. ✅ Import pre-populated libraries (531 TV series, 1209 movies)
5. ✅ Set local network bypass (no auth needed for 127.0.0.1)

#### Access

```bash
# Sonarr: http://localhost:8989
# Radarr: http://localhost:7878
# Username: testuser
# Password: testpass123
```

#### Run Wizard

```bash
cd ..
python wizard.py --teststack
```

This runs the wizard with:
- Auto-loaded credentials from `test/.env`
- No manual URL/API key entry needed
- Immediate configuration of your 531 series and 1209 movies

#### Cleanup

```bash
cd test
./cleanup-stack.sh
```

#### Options

```bash
# Skip authentication setup
./init-stack.sh --no-auth

# Skip library import (faster startup)
./init-stack.sh --no-fixtures

# Both
./init-stack.sh --no-auth --no-fixtures
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

### Wizard
- Python 3.10+
- questionary >= 2.0
- requests >= 2.31
- Sonarr v4+ or Radarr v6+ with API access

### Test Stack (Optional)
- Docker and Docker Compose
- ~500MB disk space (for containers and pre-populated libraries)
- Ports 8989 (Sonarr) and 7878 (Radarr) available
