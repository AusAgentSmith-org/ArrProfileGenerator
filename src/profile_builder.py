"""Translates UserProfile + DB tier data into Sonarr/Radarr CF and profile objects."""

from __future__ import annotations

import re

from questions import UserProfile

# Tier → score mapping per strictness level
# Using TRaSH Guides tier names: Tier 01/02/03 + LQ
TIER_SCORES: dict[str, dict[str, int]] = {
    "strict": {
        "Tier 01": 1500, "Tier 02": -2000, "Tier 03": -4000, "LQ": -10000,
    },
    "balanced": {
        "Tier 01": 1500, "Tier 02": 400, "Tier 03": -100, "LQ": -10000,
    },
    "permissive": {
        "Tier 01": 1500, "Tier 02": 200, "Tier 03": 50, "LQ": -10000,
    },
}


def _release_group_spec(regex: str) -> dict:
    """Build a ReleaseGroupSpecification."""
    return {
        "name": "Group",
        "implementation": "ReleaseGroupSpecification",
        "negate": False,
        "required": False,
        "fields": [{"name": "value", "value": regex}],
    }


def _release_title_spec(name: str, regex: str) -> dict:
    """Build a ReleaseTitleSpecification."""
    return {
        "name": name,
        "implementation": "ReleaseTitleSpecification",
        "negate": False,
        "required": False,
        "fields": [{"name": "value", "value": regex}],
    }


def build_group_custom_formats(
    group_tiers: dict[str, list[str]], profile: UserProfile
) -> list[dict]:
    """Build one CF per tier from TRaSH tier data.

    group_tiers: {"Tier 01": ["FLUX", "DON", ...], "Tier 02": [...], "LQ": [...]}
    """
    scores = TIER_SCORES[profile.strictness]
    cfs = []

    for tier, groups in group_tiers.items():
        if not groups:
            continue
        # Escape any regex-special chars in group names, join with |
        escaped = [re.escape(g) for g in sorted(groups)]
        regex = r"\b(" + "|".join(escaped) + r")\b"

        cf_name = f"ProfSync {tier}"
        cfs.append({
            "name": cf_name,
            "includeCustomFormatWhenRenaming": False,
            "specifications": [_release_group_spec(regex)],
            "_profsync_score": scores.get(tier, 0),
        })

    return cfs


def build_codec_audio_cfs(profile: UserProfile) -> list[dict]:
    """Build conditional CFs for codec, audio, and HDR preferences."""
    cfs = []

    # Codec preferences
    if profile.device_capability == "legacy":
        # Prefer x264, penalize x265
        cfs.append({
            "name": "ProfSync x264 Preferred",
            "includeCustomFormatWhenRenaming": False,
            "specifications": [
                _release_title_spec("x264", r"\b(x264|h\.?264|AVC)\b")
            ],
            "_profsync_score": 200,
        })
        cfs.append({
            "name": "ProfSync x265 Penalty",
            "includeCustomFormatWhenRenaming": False,
            "specifications": [
                _release_title_spec("x265", r"\b(x265|HEVC|h\.?265)\b")
            ],
            "_profsync_score": -500,
        })
    elif profile.device_capability in ("modern", "mixed"):
        # Boost HEVC
        cfs.append({
            "name": "ProfSync HEVC/x265",
            "includeCustomFormatWhenRenaming": False,
            "specifications": [
                _release_title_spec("HEVC", r"\b(x265|HEVC|h\.?265)\b")
            ],
            "_profsync_score": 100,
        })

    # Audio
    if profile.audio_preference == "lossless":
        cfs.append({
            "name": "ProfSync Lossless Audio",
            "includeCustomFormatWhenRenaming": False,
            "specifications": [
                _release_title_spec(
                    "Lossless Audio",
                    r"\b(TrueHD|DTS-HD|DTS[\. ]MA|LPCM|FLAC|Atmos)\b",
                )
            ],
            "_profsync_score": 200,
        })

    # HDR
    if profile.hdr_support in ("full", "hdr10"):
        cfs.append({
            "name": "ProfSync HDR10",
            "includeCustomFormatWhenRenaming": False,
            "specifications": [
                _release_title_spec("HDR10", r"\b(HDR10|HDR)\b")
            ],
            "_profsync_score": 100,
        })

    if profile.hdr_support == "full":
        cfs.append({
            "name": "ProfSync Dolby Vision",
            "includeCustomFormatWhenRenaming": False,
            "specifications": [
                _release_title_spec("DV", r"\b(DV|DoVi|Dolby.?Vision)\b")
            ],
            "_profsync_score": 150,
        })

    return cfs


def build_all_custom_formats(
    group_tiers: dict[str, list[str]], profile: UserProfile
) -> list[dict]:
    """Build the complete list of custom formats."""
    cfs = build_group_custom_formats(group_tiers, profile)
    cfs.extend(build_codec_audio_cfs(profile))
    return cfs


# Quality name constants (as they appear in Sonarr/Radarr schemas)
HD_QUALITIES = ["Bluray-1080p", "WEBDL-1080p", "WEBRip-1080p"]
HD_REMUX = "Remux-1080p"
UHD_QUALITIES = ["Bluray-2160p", "WEBDL-2160p", "WEBRip-2160p"]
UHD_REMUX = "Remux-2160p"


def _find_quality_item(schema_items: list[dict], name: str) -> dict | None:
    """Find a quality item by name in the schema, searching inside groups too."""
    for item in schema_items:
        if item.get("quality", {}).get("name") == name:
            return item
        # Check inside quality groups
        if item.get("items"):
            for sub in item["items"]:
                if sub.get("quality", {}).get("name") == name:
                    return sub
    return None


def _get_quality_id(schema_items: list[dict], name: str) -> int | None:
    """Get the quality id for a named quality from the schema."""
    item = _find_quality_item(schema_items, name)
    if item:
        return item.get("quality", {}).get("id")
    return None


def build_quality_profile(
    profile: UserProfile,
    schema: dict,
    cf_id_map: dict[str, int],
    all_cfs: list[dict],
    profile_name: str,
    resolution: str,
) -> dict:
    """Build a quality profile payload for Sonarr/Radarr.

    resolution: "hd", "uhd", or "both"
    """
    schema_items = schema.get("items", [])

    # Determine which qualities to enable
    enabled_names: list[str] = []
    if resolution in ("uhd", "both"):
        enabled_names.extend(UHD_QUALITIES)
        if profile.include_remux and profile.storage_constraint != "tight":
            enabled_names.append(UHD_REMUX)
    if resolution in ("hd", "both"):
        enabled_names.extend(HD_QUALITIES)
        if profile.include_remux and profile.storage_constraint != "tight":
            enabled_names.append(HD_REMUX)

    # If tight storage, prefer WEB over Bluray by removing Bluray
    if profile.storage_constraint == "tight":
        enabled_names = [n for n in enabled_names if "Bluray" not in n and "Remux" not in n]
        # Ensure we have at least WEB qualities
        if resolution in ("uhd", "both"):
            for q in ["WEBDL-2160p", "WEBRip-2160p"]:
                if q not in enabled_names:
                    enabled_names.append(q)
        if resolution in ("hd", "both"):
            for q in ["WEBDL-1080p", "WEBRip-1080p"]:
                if q not in enabled_names:
                    enabled_names.append(q)

    # Build items list — mark matching ones as allowed
    items = []
    for item in schema_items:
        new_item = dict(item)
        quality_name = item.get("quality", {}).get("name", "")
        if quality_name in enabled_names:
            new_item["allowed"] = True
        else:
            new_item["allowed"] = False

        # Handle groups with sub-items
        if item.get("items"):
            new_sub = []
            for sub in item["items"]:
                sub_copy = dict(sub)
                sub_name = sub.get("quality", {}).get("name", "")
                sub_copy["allowed"] = sub_name in enabled_names
                new_sub.append(sub_copy)
            new_item["items"] = new_sub

        items.append(new_item)

    # Determine cutoff quality
    if resolution == "uhd" or resolution == "both":
        if profile.include_remux and profile.storage_constraint != "tight":
            cutoff_name = UHD_REMUX
        else:
            cutoff_name = "Bluray-2160p" if profile.storage_constraint != "tight" else "WEBDL-2160p"
    else:
        if profile.include_remux and profile.storage_constraint != "tight":
            cutoff_name = HD_REMUX
        else:
            cutoff_name = "Bluray-1080p" if profile.storage_constraint != "tight" else "WEBDL-1080p"

    cutoff_id = _get_quality_id(schema_items, cutoff_name)
    # Fallback to first enabled quality
    if cutoff_id is None and enabled_names:
        cutoff_id = _get_quality_id(schema_items, enabled_names[0])
    if cutoff_id is None:
        cutoff_id = 0

    # Build format items (CF assignments with scores)
    format_items = []
    for cf in all_cfs:
        cf_name = cf["name"]
        if cf_name in cf_id_map:
            format_items.append({
                "format": cf_id_map[cf_name],
                "name": cf_name,
                "score": cf["_profsync_score"],
            })

    # Min format score
    if profile.strictness == "strict":
        min_score = 399
    else:
        min_score = -9999

    # Cutoff format score
    if profile.strictness == "strict":
        cutoff_format_score = 999
    else:
        cutoff_format_score = 1499

    return {
        "name": profile_name,
        "upgradeAllowed": profile.auto_upgrade,
        "cutoff": cutoff_id,
        "items": items,
        "minFormatScore": min_score,
        "cutoffFormatScore": cutoff_format_score,
        "formatItems": format_items,
    }
