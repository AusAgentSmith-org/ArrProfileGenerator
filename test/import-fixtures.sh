#!/bin/bash
# Import test fixtures (series/movies) into teststack Sonarr/Radarr

set -e

SONARR_URL="${1:-http://localhost:8989}"
SONARR_API_KEY="${2}"
RADARR_URL="${3:-http://localhost:7878}"
RADARR_API_KEY="${4}"

if [ -z "$SONARR_API_KEY" ] || [ -z "$RADARR_API_KEY" ]; then
    echo "Usage: $0 <sonarr_url> <sonarr_api_key> <radarr_url> <radarr_api_key>"
    exit 1
fi

FIXTURES_DIR="$(dirname "$0")/fixtures"

# Helper function to import to Sonarr/Radarr
import_to_arr() {
    local app_url=$1
    local api_key=$2
    local app_name=$3
    local json_file=$4
    local endpoint=$5
    local root_folder=$6
    local profile_id=$7

    if [ ! -f "$json_file" ]; then
        echo "⚠️  Fixtures file not found: $json_file"
        return 0
    fi

    echo "Importing to $app_name from $json_file..."

    # Get root folders
    root_folders=$(curl -s -X GET "$app_url/api/v3/rootfolder" \
        -H "X-Api-Key: $api_key" | python3 -c "import sys, json; print(json.load(sys.stdin)[0]['path'] if json.load(sys.stdin) else '/data')" 2>/dev/null || echo "$root_folder")

    profile=$(curl -s -X GET "$app_url/api/v3/qualityprofile" \
        -H "X-Api-Key: $api_key" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data[0]['id'] if data else 1)" 2>/dev/null || echo "1")

    # Import each item from JSON
    count=0
    python3 << PYEOF
import json
import requests

with open('$json_file') as f:
    items = json.load(f)

for item in items:
    if '$endpoint' == 'series':
        payload = {
            'title': item.get('title'),
            'tvdbId': item.get('tvdbId', 0),
            'seriesType': item.get('seriesType', 'standard'),
            'qualityProfileId': int($profile),
            'rootFolderPath': '$root_folders',
            'monitored': True,
            'ignoreEpisodesWithoutFiles': False,
            'ignoreEpisodesWithoutAirDate': False,
            'useSceneNumbering': False,
            'addOptions': {'searchForMissingEpisodes': False},
        }
    else:  # movies
        payload = {
            'title': item.get('title'),
            'tmdbId': item.get('tmdbId', 0),
            'year': item.get('year'),
            'qualityProfileId': int($profile),
            'rootFolderPath': '$root_folders',
            'monitored': True,
            'addOptions': {'searchForMovie': False},
        }

    try:
        r = requests.post(
            '$app_url/api/v3/$endpoint',
            json=payload,
            headers={'X-Api-Key': '$api_key'},
            timeout=30
        )
        if r.status_code in (200, 201):
            print(f"  ✓ {item.get('title')}")
        else:
            pass  # Skip duplicates/errors
    except:
        pass

PYEOF

    echo "  ✓ Imported from $json_file"
}

# Import Sonarr series
echo "================================"
echo "Importing Sonarr fixtures..."
echo "================================"
import_to_arr "$SONARR_URL" "$SONARR_API_KEY" "Sonarr" \
    "$FIXTURES_DIR/sonarr-series.json" "series" "/tv" "1"
echo

# Import Radarr movies
echo "================================"
echo "Importing Radarr fixtures..."
echo "================================"
import_to_arr "$RADARR_URL" "$RADARR_API_KEY" "Radarr" \
    "$FIXTURES_DIR/radarr-movies.json" "movie" "/movies" "1"
echo

echo "✅ Fixtures imported!"
