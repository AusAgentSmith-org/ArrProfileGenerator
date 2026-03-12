"""ProfSync Configuration Wizard — generates Sonarr/Radarr profiles from DB tier data."""

from __future__ import annotations

import sys
from collections import defaultdict

from sqlalchemy import func

from profsync.db import get_session
from profsync.models import GroupProfile

from arr_client import ArrClient, ArrClientError
from profile_builder import build_all_custom_formats, build_quality_profile
from questions import UserProfile, run_wizard


BANNER = """
╔══════════════════════════════════════════════════════════╗
║               ProfSync Configuration Wizard              ║
║                                                          ║
║  Data-driven quality profiles for Sonarr & Radarr        ║
╚══════════════════════════════════════════════════════════╝
"""


def get_group_tiers(session) -> dict[str, list[str]]:
    """Query GroupProfile for best tier per group, return {tier: [group_names]}.

    For groups appearing at multiple resolutions, use the best tier achieved.
    """
    tier_order = {"A+": 0, "A": 1, "B+": 2, "B": 3, "C+": 4, "C": 5, "D": 6, "F": 7}

    rows = (
        session.query(GroupProfile.group_name, GroupProfile.computed_tier)
        .filter(GroupProfile.computed_tier.isnot(None))
        .all()
    )

    # Pick best tier per group
    best: dict[str, str] = {}
    for group_name, tier in rows:
        if group_name not in best or tier_order.get(tier, 99) < tier_order.get(
            best[group_name], 99
        ):
            best[group_name] = tier

    # Invert to {tier: [groups]}
    tiers: dict[str, list[str]] = defaultdict(list)
    for group_name, tier in best.items():
        tiers[tier].append(group_name)

    return dict(tiers)


def apply_to_app(
    client: ArrClient,
    all_cfs: list[dict],
    profile: UserProfile,
    group_tiers: dict[str, list[str]],
) -> None:
    """Apply custom formats and quality profiles to a single Sonarr/Radarr instance."""

    # 1. Verify connection
    try:
        status = client.verify_connection()
    except ArrClientError as e:
        print(f"  ERROR: Could not connect to {client.app_name}: {e}")
        return

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
        return

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
                client.update_quality_profile(qp)
                print(f"  Updated quality profile: {prof_name}")
            else:
                client.create_quality_profile(qp)
                print(f"  Created quality profile: {prof_name}")
            profile_count += 1
        except ArrClientError as e:
            print(f"  ERROR: Failed to create profile '{prof_name}': {e}")

    print(
        f"  {client.app_name}: {cf_count} custom formats, "
        f"{profile_count} quality profile(s)"
    )


def main():
    print(BANNER)

    # 1. Run wizard
    profile = run_wizard()
    print()

    # 2. Load group tiers from DB
    session = get_session()
    try:
        group_tiers = get_group_tiers(session)
    finally:
        session.close()

    total_groups = sum(len(g) for g in group_tiers.values())
    if total_groups == 0:
        print("WARNING: No group tier data found in database.")
        print("Run the analyzer service first to compute group profiles.")
        print("Continuing with empty group tiers (only codec/audio CFs will be created)...")
        print()

    tier_summary = ", ".join(
        f"{tier}: {len(groups)}" for tier, groups in sorted(group_tiers.items())
    )
    if tier_summary:
        print(f"Loaded {total_groups} groups from database ({tier_summary})")
    print()

    # 3. Build custom formats
    all_cfs = build_all_custom_formats(group_tiers, profile)
    print(f"Built {len(all_cfs)} custom formats")
    print()

    # 4. Apply to each app
    if profile.sonarr:
        print(f"Configuring Sonarr ({profile.sonarr.url})...")
        client = ArrClient(profile.sonarr.url, profile.sonarr.api_key, "Sonarr")
        apply_to_app(client, all_cfs, profile, group_tiers)
        print()

    if profile.radarr:
        print(f"Configuring Radarr ({profile.radarr.url})...")
        client = ArrClient(profile.radarr.url, profile.radarr.api_key, "Radarr")
        apply_to_app(client, all_cfs, profile, group_tiers)
        print()

    # 5. Print strictness warning
    if profile.strictness == "strict":
        print("NOTE: Strict mode is active. Groups not in the ProfSync database")
        print("will score 0, which is below the minimum format score of 399.")
        print("This means unknown/new groups will be blocked until they are profiled.")
        print()

    # 6. Final instructions
    print("Done! Next steps:")
    print("  1. Open Sonarr/Radarr Settings > Profiles")
    print("  2. Assign 'ProfSync' profiles to your libraries/root folders")
    print("  3. Existing media will not be re-evaluated unless you trigger a search")
    print()


if __name__ == "__main__":
    main()
