#!/usr/bin/env python3
"""Non-interactive wizard runner for CI/testing.

Calls the same code paths as main.py but with hardcoded UserProfile answers.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arr_client import ArrClient, ArrClientError
from main import apply_to_app
from profile_builder import build_all_custom_formats
from questions import UserProfile, load_teststack_credentials
from trash_fetcher import fetch_group_tiers


def main():
    sonarr_config, radarr_config = load_teststack_credentials()
    if not sonarr_config and not radarr_config:
        print("ERROR: No teststack credentials found in test/.env")
        sys.exit(1)

    profile = UserProfile(
        sonarr=sonarr_config,
        radarr=radarr_config,
        resolution="both",
        consumption="home",
        can_transcode=True,
        device_capability="modern",
        hdr_support="full",
        audio_preference="lossless",
        include_remux=False,
        storage_constraint="none",
        strictness="balanced",
        auto_upgrade=True,
    )

    print("Fetching TRaSH tier data...", end="", flush=True)
    group_tiers = fetch_group_tiers()
    total = sum(len(v) for v in group_tiers.values())
    print(f" done ({total} groups across {len(group_tiers)} tiers)")
    print()

    all_cfs = build_all_custom_formats(group_tiers, profile)
    print(f"Built {len(all_cfs)} custom formats")
    print()

    ok = True
    if profile.sonarr:
        print(f"Configuring Sonarr ({profile.sonarr.url})...")
        client = ArrClient(profile.sonarr.url, profile.sonarr.api_key, "Sonarr")
        if apply_to_app(client, all_cfs, profile, group_tiers) is None:
            ok = False
        print()

    if profile.radarr:
        print(f"Configuring Radarr ({profile.radarr.url})...")
        client = ArrClient(profile.radarr.url, profile.radarr.api_key, "Radarr")
        if apply_to_app(client, all_cfs, profile, group_tiers) is None:
            ok = False
        print()

    if ok:
        print("Wizard completed successfully.")
    else:
        print("Wizard completed with errors.")
        sys.exit(1)


if __name__ == "__main__":
    main()
