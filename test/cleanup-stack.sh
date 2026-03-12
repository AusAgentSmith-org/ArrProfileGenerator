#!/usr/bin/env bash
# Stop and remove test stack containers and volumes

set -e

echo "=== Cleaning up ProfSync Test Stack ==="
echo

# Stop containers
echo "Stopping containers..."
docker-compose down --remove-orphans 2>/dev/null || true
echo "✓ Containers stopped"
echo

# Remove volumes (optional)
read -p "Remove data volumes? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Removing volumes..."
    rm -rf sonarr-config sonarr-tv sonarr-downloads
    rm -rf radarr-config radarr-movies radarr-downloads
    echo "✓ Volumes removed"
fi

echo
echo "Test stack cleaned up"
