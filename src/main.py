"""ProfSync Configuration Wizard — generates Sonarr/Radarr profiles from TRaSH Guides data."""

from __future__ import annotations

import argparse
import sys

import questionary

from arr_client import ArrClient, ArrClientError
from profile_builder import build_all_custom_formats, build_quality_profile
from questions import UserProfile, run_wizard
from trash_fetcher import fetch_group_tiers


BANNER = """
╔══════════════════════════════════════════════════════════╗
║               ProfSync Configuration Wizard              ║
║                                                          ║
║  Sonarr/Radarr setup from TRaSH Guides data              ║
╚══════════════════════════════════════════════════════════╝
"""


def apply_to_app(
    client: ArrClient,
    all_cfs: list[dict],
    profile: UserProfile,
    group_tiers: dict[str, list[str]],
) -> int | None:
    """Apply custom formats and quality profiles to a single Sonarr/Radarr instance.

    Returns the profile_id of the created/updated profile, or None on failure.
    """

    # 1. Verify connection
    try:
        status = client.verify_connection()
    except ArrClientError as e:
        print(f"  ERROR: Could not connect to {client.app_name}: {e}")
        return None

    print(f"  Connected to {client.app_name} v{client.version}")

    # 2. Warn if Sonarr v3 (no CF support)
    skip_cfs = False
    if client.is_sonarr_v3:
        print(
            f"  WARNING: {client.app_name} v3 does not support custom formats."
        )
        print("  Quality profile will be created without custom format scoring.")
        print("  Upgrade to Sonarr v4 for full ProfSync support.")
        skip_cfs = True

    # 3. Trigger backup
    try:
        print(f"  Triggering backup...")
        client.trigger_backup()
        print(f"  Backup taken")
    except ArrClientError as e:
        print(f"  WARNING: Backup failed: {e}")
        print("  Continuing anyway...")

    # 4. Upsert custom formats
    cf_id_map: dict[str, int] = {}
    cf_count = 0
    if not skip_cfs:
        for cf in all_cfs:
            # Remove our internal score key before sending to API
            cf_payload = {k: v for k, v in cf.items() if k != "_profsync_score"}
            try:
                cf_id = client.upsert_custom_format(cf_payload)
                cf_id_map[cf["name"]] = cf_id
                cf_count += 1
            except ArrClientError as e:
                print(f"  WARNING: Failed to upsert CF '{cf['name']}': {e}")

    # 5. Fetch schema
    try:
        schema = client.get_quality_profile_schema()
    except ArrClientError as e:
        print(f"  ERROR: Could not fetch quality profile schema: {e}")
        return None

    # 6. Build and create quality profiles
    profiles_to_create: list[tuple[str, str]] = []
    if profile.resolution == "hd":
        profiles_to_create.append(("ProfSync HD", "hd"))
    elif profile.resolution == "uhd":
        profiles_to_create.append(("ProfSync UHD", "uhd"))
    else:  # both
        profiles_to_create.append(("ProfSync UHD", "both"))

    existing_profiles = client.get_quality_profiles()
    profile_count = 0
    profile_id = None

    for prof_name, res in profiles_to_create:
        qp = build_quality_profile(
            profile, schema, cf_id_map, all_cfs, prof_name, res
        )

        # If Sonarr v3, strip format items
        if skip_cfs:
            qp.pop("formatItems", None)
            qp.pop("minFormatScore", None)
            qp.pop("cutoffFormatScore", None)

        # Check if profile already exists — update it
        existing = next((p for p in existing_profiles if p["name"] == prof_name), None)
        try:
            if existing:
                qp["id"] = existing["id"]
                profile_id = client.update_quality_profile(qp)
                print(f"  Updated quality profile: {prof_name}")
            else:
                profile_id = client.create_quality_profile(qp)
                print(f"  Created quality profile: {prof_name}")
            profile_count += 1
        except ArrClientError as e:
            print(f"  ERROR: Failed to create profile '{prof_name}': {e}")

    print(
        f"  {client.app_name}: {cf_count} custom formats, "
        f"{profile_count} quality profile(s)"
    )

    return profile_id


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="ProfSync Configuration Wizard for Sonarr/Radarr",
        add_help=True,
    )
    parser.add_argument(
        "--teststack",
        action="store_true",
        help="Auto-load credentials from test/.env (teststack mode)",
    )
    args = parser.parse_args()

    print(BANNER)

    # 1. Run wizard
    profile = run_wizard(teststack=args.teststack)
    print()

    # 2. Fetch TRaSH tier data
    print("Fetching TRaSH tier data...", end="", flush=True)
    group_tiers = fetch_group_tiers()
    print(f" done ({sum(len(v) for v in group_tiers.values())} groups across {len(group_tiers)} tiers)")
    print()

    # 3. Build custom formats
    all_cfs = build_all_custom_formats(group_tiers, profile)
    print(f"Built {len(all_cfs)} custom formats")
    print()

    # 4. Apply to each app
    if profile.sonarr:
        print(f"Configuring Sonarr ({profile.sonarr.url})...")
        client = ArrClient(profile.sonarr.url, profile.sonarr.api_key, "Sonarr")
        sonarr_profile_id = apply_to_app(client, all_cfs, profile, group_tiers)
        print()

        # Bulk update series if requested
        if sonarr_profile_id and questionary.confirm(
            f"Update all existing Sonarr series to use this profile?",
            default=False,
        ).ask():
            try:
                series = client.get_series()
                series_ids = [s["id"] for s in series]
                client.bulk_update_series(series_ids, sonarr_profile_id)
                print(f"  Updated {len(series_ids)} series")
            except ArrClientError as e:
                print(f"  ERROR: Failed to bulk update series: {e}")
            print()

    if profile.radarr:
        print(f"Configuring Radarr ({profile.radarr.url})...")
        client = ArrClient(profile.radarr.url, profile.radarr.api_key, "Radarr")
        radarr_profile_id = apply_to_app(client, all_cfs, profile, group_tiers)
        print()

        # Bulk update movies if requested
        if radarr_profile_id and questionary.confirm(
            f"Update all existing Radarr movies to use this profile?",
            default=False,
        ).ask():
            try:
                movies = client.get_movies()
                movie_ids = [m["id"] for m in movies]
                client.bulk_update_movies(movie_ids, radarr_profile_id)
                print(f"  Updated {len(movie_ids)} movies")
            except ArrClientError as e:
                print(f"  ERROR: Failed to bulk update movies: {e}")
            print()

    # 5. Final instructions
    print("Done! Next steps:")
    print("  1. Open Sonarr/Radarr Settings > Profiles")
    print("  2. Assign 'ProfSync' profiles to your libraries/root folders")
    print("  3. Existing media will not be re-evaluated unless you trigger a search")
    print()


if __name__ == "__main__":
    main()
