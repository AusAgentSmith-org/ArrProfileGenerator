#!/usr/bin/env bash
# Post-deployment validation for the ProfSync test stack.
# Checks that Sonarr and Radarr APIs are functional and fixtures are loaded.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found. Run init-stack.sh first."
    exit 1
fi

source "$ENV_FILE"

PASS=0
FAIL=0

check() {
    local desc=$1
    shift
    if "$@" > /dev/null 2>&1; then
        echo "  ✓ $desc"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $desc"
        FAIL=$((FAIL + 1))
    fi
}

check_json_count() {
    local desc=$1
    local url=$2
    local api_key=$3
    local min_count=$4

    local resp
    resp=$(curl -sf -H "X-Api-Key: $api_key" "$url" 2>/dev/null) || { echo "  ✗ $desc (HTTP error)"; FAIL=$((FAIL + 1)); return; }
    local count
    count=$(echo "$resp" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null) || { echo "  ✗ $desc (parse error)"; FAIL=$((FAIL + 1)); return; }
    if [ "$count" -ge "$min_count" ]; then
        echo "  ✓ $desc (count: $count)"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $desc (expected >= $min_count, got $count)"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Validating Test Stack ==="
echo

# --- Sonarr ---
echo "Sonarr ($SONARR_URL):"

check "API responds 200" \
    curl -sf -H "X-Api-Key: $SONARR_API_KEY" "$SONARR_URL/api/v3/system/status"

check_json_count "Root folders exist" \
    "$SONARR_URL/api/v3/rootfolder" "$SONARR_API_KEY" 1

check_json_count "Series imported (fixtures)" \
    "$SONARR_URL/api/v3/series" "$SONARR_API_KEY" 1

check "Quality profiles endpoint accessible" \
    curl -sf -H "X-Api-Key: $SONARR_API_KEY" "$SONARR_URL/api/v3/qualityprofile"

check "Custom formats endpoint accessible" \
    curl -sf -H "X-Api-Key: $SONARR_API_KEY" "$SONARR_URL/api/v3/customformat"

echo

# --- Radarr ---
echo "Radarr ($RADARR_URL):"

check "API responds 200" \
    curl -sf -H "X-Api-Key: $RADARR_API_KEY" "$RADARR_URL/api/v3/system/status"

check_json_count "Root folders exist" \
    "$RADARR_URL/api/v3/rootfolder" "$RADARR_API_KEY" 1

check_json_count "Movies imported (fixtures)" \
    "$RADARR_URL/api/v3/movie" "$RADARR_API_KEY" 1

check "Quality profiles endpoint accessible" \
    curl -sf -H "X-Api-Key: $RADARR_API_KEY" "$RADARR_URL/api/v3/qualityprofile"

check "Custom formats endpoint accessible" \
    curl -sf -H "X-Api-Key: $RADARR_API_KEY" "$RADARR_URL/api/v3/customformat"

echo

# --- Summary ---
TOTAL=$((PASS + FAIL))
echo "=== Results: $PASS/$TOTAL passed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL check(s) failed"
    exit 1
else
    echo "ALL CHECKS PASSED"
fi
