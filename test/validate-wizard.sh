#!/usr/bin/env bash
# Post-wizard validation for ProfSync.
# Checks that custom formats and quality profiles were correctly created.

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

check_json() {
    local desc=$1
    local jq_expr=$2
    local url=$3
    local api_key=$4
    local min_val=$5

    local resp
    resp=$(curl -sf -H "X-Api-Key: $api_key" "$url" 2>/dev/null) || { echo "  ✗ $desc (HTTP error)"; FAIL=$((FAIL + 1)); return; }
    local val
    val=$(echo "$resp" | python3 -c "
import sys, json
data = json.load(sys.stdin)
$jq_expr
" 2>/dev/null) || { echo "  ✗ $desc (parse error)"; FAIL=$((FAIL + 1)); return; }
    if [ "$val" -ge "$min_val" ] 2>/dev/null; then
        echo "  ✓ $desc (value: $val)"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $desc (expected >= $min_val, got $val)"
        FAIL=$((FAIL + 1))
    fi
}

validate_app() {
    local app_name=$1
    local url=$2
    local api_key=$3

    echo "$app_name ($url):"

    # Check ProfSync custom formats exist
    check_json "ProfSync custom formats exist" \
        "print(len([cf for cf in data if cf['name'].startswith('ProfSync')]))" \
        "$url/api/v3/customformat" "$api_key" 1

    # Check ProfSync quality profile exists
    local profiles_resp
    profiles_resp=$(curl -sf -H "X-Api-Key: $api_key" "$url/api/v3/qualityprofile" 2>/dev/null) || { echo "  ✗ Could not fetch profiles"; FAIL=$((FAIL + 1)); return; }

    local profile_json
    profile_json=$(echo "$profiles_resp" | python3 -c "
import sys, json
data = json.load(sys.stdin)
ps = [p for p in data if p['name'].startswith('ProfSync')]
if ps:
    print(json.dumps(ps[0]))
else:
    print('null')
" 2>/dev/null)

    if [ "$profile_json" = "null" ] || [ -z "$profile_json" ]; then
        echo "  ✗ ProfSync quality profile exists"
        FAIL=$((FAIL + 1))
        return
    fi
    echo "  ✓ ProfSync quality profile exists"
    PASS=$((PASS + 1))

    # Check profile has allowed qualities
    local allowed_count
    allowed_count=$(echo "$profile_json" | python3 -c "
import sys, json
p = json.load(sys.stdin)
count = 0
for item in p.get('items', []):
    if item.get('allowed'):
        count += 1
    for sub in item.get('items', []):
        if sub.get('allowed'):
            count += 1
print(count)
" 2>/dev/null) || allowed_count=0

    if [ "$allowed_count" -gt 0 ]; then
        echo "  ✓ Profile has allowed qualities (count: $allowed_count)"
        PASS=$((PASS + 1))
    else
        echo "  ✗ Profile has allowed qualities (count: $allowed_count)"
        FAIL=$((FAIL + 1))
    fi

    # Check profile has formatItems with non-zero scores
    local scored_count
    scored_count=$(echo "$profile_json" | python3 -c "
import sys, json
p = json.load(sys.stdin)
count = len([fi for fi in p.get('formatItems', []) if fi.get('score', 0) != 0])
print(count)
" 2>/dev/null) || scored_count=0

    if [ "$scored_count" -gt 0 ]; then
        echo "  ✓ Profile has scored format items (count: $scored_count)"
        PASS=$((PASS + 1))
    else
        echo "  ✗ Profile has scored format items (count: $scored_count)"
        FAIL=$((FAIL + 1))
    fi

    # Check cutoff is set
    local cutoff
    cutoff=$(echo "$profile_json" | python3 -c "
import sys, json
p = json.load(sys.stdin)
print(p.get('cutoff', 0))
" 2>/dev/null) || cutoff=0

    if [ "$cutoff" -gt 0 ]; then
        echo "  ✓ Profile cutoff is set (id: $cutoff)"
        PASS=$((PASS + 1))
    else
        echo "  ✗ Profile cutoff is not set (id: $cutoff)"
        FAIL=$((FAIL + 1))
    fi

    echo
}

echo "=== Validating Wizard Results ==="
echo

validate_app "Sonarr" "$SONARR_URL" "$SONARR_API_KEY"
validate_app "Radarr" "$RADARR_URL" "$RADARR_API_KEY"

# --- Summary ---
TOTAL=$((PASS + FAIL))
echo "=== Results: $PASS/$TOTAL passed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL check(s) failed"
    exit 1
else
    echo "ALL CHECKS PASSED"
fi
