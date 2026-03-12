#!/bin/bash
# Configure authentication for teststack Sonarr/Radarr
# Sets username/password and local network bypass on first startup

set -e

SONARR_URL="${1:-http://localhost:8989}"
SONARR_API_KEY="${2}"
RADARR_URL="${3:-http://localhost:7878}"
RADARR_API_KEY="${4}"

USERNAME="${5:-testuser}"
PASSWORD="${6:-testpass123}"

# Local network IPs to bypass auth
# 127.0.0.1 = localhost
# 172.17.0.0/16 = Docker bridge network
BYPASS_IPS="127.0.0.1,::1,172.17.0.0/16,192.168.0.0/16"

if [ -z "$SONARR_API_KEY" ] || [ -z "$RADARR_API_KEY" ]; then
    echo "Usage: $0 <sonarr_url> <sonarr_api_key> <radarr_url> <radarr_api_key> [username] [password]"
    exit 1
fi

configure_auth() {
    local app_url=$1
    local api_key=$2
    local app_name=$3

    echo "Configuring auth for $app_name..."

    # Get current auth config
    auth_config=$(curl -s -X GET "$app_url/api/v3/config/auth" \
        -H "X-Api-Key: $api_key")

    # Update with new auth settings
    updated_config=$(echo "$auth_config" | python3 << PYEOF
import sys
import json

config = json.load(sys.stdin)

# Enable authentication
config['authenticationMethod'] = 'Form'  # Form-based auth
config['authenticationRequired'] = 'EnabledForLocalAddresses'  # Require auth except local
config['username'] = '$USERNAME'
config['password'] = '$PASSWORD'
config['enableBasicAuth'] = True

# Set local network bypass
config['enableBroadcastProxyProtocol'] = False
config['allowBypassAuthenticationIfAddressMatches'] = True
config['bypassAuthenticationIfAddressMatches'] = '$BYPASS_IPS'

print(json.dumps(config))
PYEOF
)

    # Apply the updated config
    curl -s -X PUT "$app_url/api/v3/config/auth" \
        -H "X-Api-Key: $api_key" \
        -H "Content-Type: application/json" \
        -d "$updated_config" > /dev/null

    echo "  ✓ Auth configured for $app_name"
    echo "    Username: $USERNAME"
    echo "    Password: $PASSWORD"
    echo "    Local bypass: Enabled for $BYPASS_IPS"
}

echo "================================"
echo "Configuring Teststack Auth"
echo "================================"
echo

configure_auth "$SONARR_URL" "$SONARR_API_KEY" "Sonarr"
echo

configure_auth "$RADARR_URL" "$RADARR_API_KEY" "Radarr"
echo

echo "✅ Authentication configured!"
echo
echo "You can now access:"
echo "  Sonarr:  $SONARR_URL"
echo "  Radarr:  $RADARR_URL"
echo
echo "Login with:"
echo "  Username: $USERNAME"
echo "  Password: $PASSWORD"
echo
echo "Note: Local network access (127.0.0.1) bypasses authentication"
