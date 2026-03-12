#!/usr/bin/env python3
"""Import series/movies from live Sonarr/Radarr instances to teststack."""

import sys
sys.path.insert(0, '/home/sprooty/profsync/src')

from arr_client import ArrClient, ArrClientError

# Live instances
LIVE_SONARR_URL = "https://sonarr.sprooty.com/sonarr"
LIVE_SONARR_KEY = "a36b55e3f45f455eb6abed6916f7ff5e"

LIVE_RADARR_URL = "https://radarr.sprooty.com"
LIVE_RADARR_KEY = "5d7d0870cc184983aaf73359fd60f7a1"

# Teststack instances
TEST_SONARR_URL = "http://localhost:8989"
TEST_SONARR_KEY = "testkey"  # Will be loaded from test/.env

TEST_RADARR_URL = "http://localhost:7878"
TEST_RADARR_KEY = "testkey"  # Will be loaded from test/.env

def load_teststack_keys():
    """Load teststack API keys from test/.env"""
    from pathlib import Path
    teststack_env = Path(__file__).parent / "test" / ".env"

    if not teststack_env.exists():
        print("ERROR: test/.env not found. Run: cd test && ./init-stack.sh")
        return None, None

    env_vars = {}
    with open(teststack_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()

    sonarr_key = env_vars.get("SONARR_API_KEY")
    radarr_key = env_vars.get("RADARR_API_KEY")

    if not sonarr_key or not radarr_key:
        print("ERROR: Could not load API keys from test/.env")
        return None, None

    return sonarr_key, radarr_key

def import_sonarr(live_client, test_client):
    """Import all series from live to teststack."""
    print("Importing Sonarr series...")
    try:
        live_series = live_client.get_series()
        print(f"  Found {len(live_series)} series in live instance")

        # Get or create root folder in teststack
        test_root_folders = test_client.get_root_folders()
        test_profiles = test_client.get_quality_profiles()

        if not test_root_folders:
            print("  Creating root folder /tv in teststack...")
            try:
                result = test_client.create_root_folder("/tv")
                test_root_folders = [result]
            except ArrClientError as e:
                print(f"  ERROR: Could not create root folder: {e}")
                return 0

        root_folder_path = test_root_folders[0]["path"]
        default_profile_id = test_profiles[0]["id"] if test_profiles else None

        if not default_profile_id:
            print("  ERROR: No quality profiles in teststack")
            return 0

        imported = 0
        for series in live_series:
            # Build series payload for teststack
            # Minimal payload: title, tvdbId, qualityProfileId, rootFolderPath, monitored
            payload = {
                "title": series.get("title", "Unknown"),
                "tvdbId": series.get("tvdbId", 0),
                "qualityProfileId": default_profile_id,
                "rootFolderPath": root_folder_path,
                "monitored": True,
                "seriesType": series.get("seriesType", "standard"),
                "ignoreEpisodesWithoutFiles": False,
                "ignoreEpisodesWithoutAirDate": False,
                "useSceneNumbering": False,
                "addOptions": {"searchForMissingEpisodes": False},
            }

            try:
                # POST to /api/v3/series
                result = test_client._post("/series", payload)
                imported += 1
                if imported % 10 == 0:
                    print(f"  Imported {imported} series...")
            except ArrClientError as e:
                # Likely duplicate, skip
                pass

        print(f"  ✓ Imported {imported} series to teststack Sonarr")
        return imported
    except ArrClientError as e:
        print(f"  ERROR: {e}")
        return 0

def import_radarr(live_client, test_client):
    """Import all movies from live to teststack."""
    print("Importing Radarr movies...")
    try:
        live_movies = live_client.get_movies()
        print(f"  Found {len(live_movies)} movies in live instance")

        # Get or create root folder in teststack
        test_root_folders = test_client.get_root_folders()
        test_profiles = test_client.get_quality_profiles()

        if not test_root_folders:
            print("  Creating root folder /movies in teststack...")
            try:
                result = test_client.create_root_folder("/movies")
                test_root_folders = [result]
            except ArrClientError as e:
                print(f"  ERROR: Could not create root folder: {e}")
                return 0

        root_folder_path = test_root_folders[0]["path"]
        default_profile_id = test_profiles[0]["id"] if test_profiles else None

        if not default_profile_id:
            print("  ERROR: No quality profiles in teststack")
            return 0

        imported = 0
        for movie in live_movies:
            # Build movie payload for teststack
            payload = {
                "title": movie.get("title", "Unknown"),
                "tmdbId": movie.get("tmdbId", 0),
                "qualityProfileId": default_profile_id,
                "rootFolderPath": root_folder_path,
                "monitored": True,
                "addOptions": {"searchForMovie": False},
            }

            try:
                # POST to /api/v3/movie
                result = test_client._post("/movie", payload)
                imported += 1
                if imported % 10 == 0:
                    print(f"  Imported {imported} movies...")
            except ArrClientError as e:
                # Likely duplicate, skip
                pass

        print(f"  ✓ Imported {imported} movies to teststack Radarr")
        return imported
    except ArrClientError as e:
        print(f"  ERROR: {e}")
        return 0

def main():
    print("ProfSync Library Importer: Live → Teststack\n")

    # Load teststack keys
    test_sonarr_key, test_radarr_key = load_teststack_keys()
    if not test_sonarr_key or not test_radarr_key:
        return 1

    # Connect to live instances
    print("Connecting to live instances...")
    live_sonarr = ArrClient(LIVE_SONARR_URL, LIVE_SONARR_KEY, "Sonarr Live")
    live_radarr = ArrClient(LIVE_RADARR_URL, LIVE_RADARR_KEY, "Radarr Live")

    try:
        live_sonarr.verify_connection()
        print(f"  ✓ Connected to Sonarr Live (v{live_sonarr.version})")
    except ArrClientError as e:
        print(f"  ERROR: Could not connect to live Sonarr: {e}")
        return 1

    try:
        live_radarr.verify_connection()
        print(f"  ✓ Connected to Radarr Live (v{live_radarr.version})")
    except ArrClientError as e:
        print(f"  ERROR: Could not connect to live Radarr: {e}")
        return 1

    # Connect to teststack
    print("Connecting to teststack instances...")
    test_sonarr = ArrClient(TEST_SONARR_URL, test_sonarr_key, "Sonarr Teststack")
    test_radarr = ArrClient(TEST_RADARR_URL, test_radarr_key, "Radarr Teststack")

    try:
        test_sonarr.verify_connection()
        print(f"  ✓ Connected to Sonarr Teststack (v{test_sonarr.version})")
    except ArrClientError as e:
        print(f"  ERROR: Could not connect to teststack Sonarr: {e}")
        return 1

    try:
        test_radarr.verify_connection()
        print(f"  ✓ Connected to Radarr Teststack (v{test_radarr.version})")
    except ArrClientError as e:
        print(f"  ERROR: Could not connect to teststack Radarr: {e}")
        return 1

    print()

    # Import
    sonarr_count = import_sonarr(live_sonarr, test_sonarr)
    radarr_count = import_radarr(live_radarr, test_radarr)

    print()
    print("Done!")
    print(f"  Sonarr: {sonarr_count} series imported")
    print(f"  Radarr: {radarr_count} movies imported")

    return 0

if __name__ == "__main__":
    sys.exit(main())
