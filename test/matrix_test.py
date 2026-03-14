#!/usr/bin/env python3
"""ProfSync matrix test — iterates through input combinations, applies to test stack, validates via API."""

import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arr_client import ArrClient, ArrClientError
from main import apply_to_app
from profile_builder import build_all_custom_formats
from questions import UserProfile, load_teststack_credentials


# ---------------------------------------------------------------------------
# Test matrix definitions
# ---------------------------------------------------------------------------

# Base config shared by most basic tests
BASE = dict(
    resolution="hd",
    consumption="home",
    can_transcode=True,
    device_capability="modern",
    hdr_support="none",
    audio_preference="standard",
    include_remux=False,
    storage_constraint="none",
    strictness="balanced",
    auto_upgrade=True,
)

# Pairwise-covering basic mode combos
BASIC_CASES: list[tuple[str, dict]] = [
    # Resolution variants
    ("basic_hd_modern_balanced", {**BASE}),
    ("basic_uhd_modern_balanced", {**BASE, "resolution": "uhd", "hdr_support": "full"}),
    ("basic_both_modern_balanced", {**BASE, "resolution": "both", "hdr_support": "full"}),

    # Device capability variants
    ("basic_hd_legacy_balanced", {**BASE, "device_capability": "legacy"}),
    ("basic_hd_mixed_balanced", {**BASE, "device_capability": "mixed"}),
    ("basic_uhd_legacy_strict", {**BASE, "resolution": "uhd", "device_capability": "legacy", "strictness": "strict"}),

    # Strictness variants
    ("basic_hd_modern_strict", {**BASE, "strictness": "strict"}),
    ("basic_hd_modern_permissive", {**BASE, "strictness": "permissive"}),
    ("basic_uhd_modern_strict", {**BASE, "resolution": "uhd", "hdr_support": "full", "strictness": "strict"}),
    ("basic_uhd_modern_permissive", {**BASE, "resolution": "uhd", "hdr_support": "hdr10", "strictness": "permissive"}),

    # Storage constraint variants
    ("basic_hd_moderate_storage", {**BASE, "storage_constraint": "moderate"}),
    ("basic_hd_tight_storage", {**BASE, "storage_constraint": "tight"}),
    ("basic_uhd_tight_storage", {**BASE, "resolution": "uhd", "storage_constraint": "tight"}),

    # Audio variants
    ("basic_hd_lossless_audio", {**BASE, "audio_preference": "lossless"}),
    ("basic_uhd_lossless_audio", {**BASE, "resolution": "uhd", "hdr_support": "full", "audio_preference": "lossless"}),

    # Remux variants
    ("basic_hd_remux", {**BASE, "include_remux": True}),
    ("basic_uhd_remux", {**BASE, "resolution": "uhd", "hdr_support": "full", "include_remux": True}),
    ("basic_both_remux", {**BASE, "resolution": "both", "hdr_support": "hdr10", "include_remux": True}),

    # HDR variants
    ("basic_uhd_hdr10_only", {**BASE, "resolution": "uhd", "hdr_support": "hdr10"}),
    ("basic_uhd_no_hdr", {**BASE, "resolution": "uhd", "hdr_support": "none"}),
    ("basic_both_hdr10", {**BASE, "resolution": "both", "hdr_support": "hdr10"}),

    # Auto-upgrade off
    ("basic_hd_no_upgrade", {**BASE, "auto_upgrade": False}),
    ("basic_uhd_no_upgrade", {**BASE, "resolution": "uhd", "hdr_support": "full", "auto_upgrade": False}),

    # Remote/transcoding combos
    ("basic_hd_remote_transcode", {**BASE, "consumption": "remote", "can_transcode": True}),
    ("basic_hd_remote_no_transcode", {**BASE, "consumption": "remote", "can_transcode": False}),

    # Cross-axis combos
    ("basic_uhd_legacy_permissive_tight", {**BASE, "resolution": "uhd", "device_capability": "legacy", "strictness": "permissive", "storage_constraint": "tight"}),
    ("basic_both_mixed_strict_lossless", {**BASE, "resolution": "both", "device_capability": "mixed", "strictness": "strict", "audio_preference": "lossless", "hdr_support": "full"}),
    ("basic_hd_legacy_tight_no_upgrade", {**BASE, "device_capability": "legacy", "storage_constraint": "tight", "auto_upgrade": False}),
    ("basic_both_permissive_remux", {**BASE, "resolution": "both", "strictness": "permissive", "include_remux": True, "hdr_support": "full"}),
    ("basic_uhd_mixed_moderate_lossless_remux", {**BASE, "resolution": "uhd", "device_capability": "mixed", "storage_constraint": "moderate", "audio_preference": "lossless", "include_remux": True, "hdr_support": "full"}),
]

# Advanced mode — each feature axis tested independently
ADVANCED_CASES: list[tuple[str, dict]] = [
    # Custom qualities
    ("adv_custom_qual_web_only", {**BASE, "advanced_mode": True, "custom_qualities": ["WEBDL-1080p", "WEBRip-1080p"]}),
    ("adv_custom_qual_bluray_only", {**BASE, "advanced_mode": True, "custom_qualities": ["Bluray-1080p"]}),
    ("adv_custom_qual_all_hd", {**BASE, "advanced_mode": True, "custom_qualities": [
        "WEBDL-720p", "WEBRip-720p", "Bluray-720p",
        "WEBDL-1080p", "WEBRip-1080p", "Bluray-1080p", "Remux-1080p",
    ]}),
    ("adv_custom_qual_uhd", {**BASE, "resolution": "uhd", "advanced_mode": True, "custom_qualities": ["WEBDL-2160p", "Bluray-2160p"]}),

    # Fallback behavior
    ("adv_fallback_strict_cutoff", {**BASE, "advanced_mode": True, "fallback_behavior": "strict_cutoff"}),
    ("adv_fallback_no_fallback", {**BASE, "advanced_mode": True, "fallback_behavior": "no_fallback"}),
    ("adv_fallback_default", {**BASE, "advanced_mode": True, "fallback_behavior": "default"}),

    # Subtitle avoidance
    ("adv_subs_hardcoded", {**BASE, "advanced_mode": True, "avoid_hardcoded_subs": True}),
    ("adv_subs_rushed", {**BASE, "advanced_mode": True, "avoid_rushed_subs": True}),
    ("adv_subs_fan_penalize", {**BASE, "advanced_mode": True, "avoid_fan_subs": "penalize"}),
    ("adv_subs_fan_block", {**BASE, "advanced_mode": True, "avoid_fan_subs": "block"}),
    ("adv_subs_all", {**BASE, "advanced_mode": True, "avoid_hardcoded_subs": True, "avoid_rushed_subs": True, "avoid_fan_subs": "block"}),

    # Granular codec preferences
    ("adv_codec_prefer_x265", {**BASE, "advanced_mode": True, "codec_preferences": {"x264": "allow", "x265": "prefer", "AV1": "allow"}}),
    ("adv_codec_block_x265", {**BASE, "advanced_mode": True, "codec_preferences": {"x264": "prefer", "x265": "block", "AV1": "allow"}}),
    ("adv_codec_prefer_av1", {**BASE, "advanced_mode": True, "codec_preferences": {"x264": "allow", "x265": "allow", "AV1": "prefer"}}),
]

# Corner cases — stress tests
CORNER_CASES: list[tuple[str, dict]] = [
    ("adv_all_features_on", {
        **BASE,
        "advanced_mode": True,
        "custom_qualities": ["WEBDL-1080p", "Bluray-1080p"],
        "fallback_behavior": "strict_cutoff",
        "avoid_hardcoded_subs": True,
        "avoid_rushed_subs": True,
        "avoid_fan_subs": "block",
        "codec_preferences": {"x264": "allow", "x265": "prefer", "AV1": "block"},
    }),
    ("adv_no_fallback_all_subs", {
        **BASE,
        "advanced_mode": True,
        "fallback_behavior": "no_fallback",
        "avoid_hardcoded_subs": True,
        "avoid_rushed_subs": True,
        "avoid_fan_subs": "penalize",
    }),
    ("adv_all_codecs_blocked", {
        **BASE,
        "advanced_mode": True,
        "codec_preferences": {"x264": "block", "x265": "block", "AV1": "block"},
    }),
    ("adv_all_codecs_preferred", {
        **BASE,
        "advanced_mode": True,
        "codec_preferences": {"x264": "prefer", "x265": "prefer", "AV1": "prefer"},
    }),
    ("adv_uhd_full_advanced", {
        **BASE,
        "resolution": "uhd",
        "hdr_support": "full",
        "audio_preference": "lossless",
        "advanced_mode": True,
        "custom_qualities": ["WEBDL-2160p", "Bluray-2160p", "Remux-2160p"],
        "fallback_behavior": "strict_cutoff",
        "avoid_hardcoded_subs": True,
        "avoid_fan_subs": "block",
        "codec_preferences": {"x264": "block", "x265": "prefer", "AV1": "prefer"},
    }),
]

ALL_CASES = BASIC_CASES + ADVANCED_CASES + CORNER_CASES


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup_profsync(client: ArrClient):
    """Delete all ProfSync CFs and quality profiles."""
    for p in client.get_quality_profiles():
        if p["name"].startswith("ProfSync"):
            client.delete_quality_profile(p["id"])
    for cf in client.get_custom_formats():
        if cf["name"].startswith("ProfSync"):
            client.delete_custom_format(cf["id"])


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]


def validate_test_case(
    client: ArrClient,
    profile: UserProfile,
    all_cfs: list[dict],
) -> ValidationResult:
    """Validate that the applied profile matches expectations."""
    errors: list[str] = []

    # Fetch current state
    existing_cfs = client.get_custom_formats()
    existing_profiles = client.get_quality_profiles()

    profsync_cfs = {cf["name"]: cf for cf in existing_cfs if cf["name"].startswith("ProfSync")}
    profsync_profiles = [p for p in existing_profiles if p["name"].startswith("ProfSync")]

    # 1. All expected ProfSync CFs exist
    expected_cf_names = {cf["name"] for cf in all_cfs}
    actual_cf_names = set(profsync_cfs.keys())
    missing_cfs = expected_cf_names - actual_cf_names
    if missing_cfs:
        errors.append(f"Missing CFs: {missing_cfs}")

    # 2. ProfSync quality profile(s) exist
    if not profsync_profiles:
        errors.append("No ProfSync quality profile found")
        return ValidationResult(ok=False, errors=errors)

    qp = profsync_profiles[0]

    # 3. Each CF has correct score in profile's formatItems
    format_items_by_name = {fi["name"]: fi for fi in qp.get("formatItems", [])}
    for cf in all_cfs:
        fi = format_items_by_name.get(cf["name"])
        if fi is None:
            errors.append(f"CF '{cf['name']}' not in profile formatItems")
        elif fi["score"] != cf["_profsync_score"]:
            errors.append(f"CF '{cf['name']}' score {fi['score']} != expected {cf['_profsync_score']}")

    # 4. Profile has at least 1 allowed quality
    allowed_count = 0
    for item in qp.get("items", []):
        if item.get("allowed"):
            allowed_count += 1
        for sub in item.get("items", []):
            if sub.get("allowed"):
                allowed_count += 1
    if allowed_count == 0:
        errors.append("No allowed qualities in profile")

    # 5. Cutoff is set (non-zero)
    if qp.get("cutoff", 0) == 0:
        errors.append("Cutoff is zero/unset")

    # 6. upgradeAllowed matches expectation
    if profile.fallback_behavior == "no_fallback":
        if qp.get("upgradeAllowed") is not False:
            errors.append("upgradeAllowed should be False for no_fallback")
    else:
        if qp.get("upgradeAllowed") != profile.auto_upgrade:
            errors.append(f"upgradeAllowed {qp.get('upgradeAllowed')} != expected {profile.auto_upgrade}")

    # 7. minFormatScore matches expectation
    if profile.fallback_behavior == "strict_cutoff":
        if qp.get("minFormatScore") != 0:
            errors.append(f"minFormatScore {qp.get('minFormatScore')} != expected 0 for strict_cutoff")
    elif profile.fallback_behavior == "no_fallback":
        if qp.get("minFormatScore") != 399:
            errors.append(f"minFormatScore {qp.get('minFormatScore')} != expected 399 for no_fallback")
    elif profile.strictness == "strict":
        if qp.get("minFormatScore") != 399:
            errors.append(f"minFormatScore {qp.get('minFormatScore')} != expected 399 for strict")
    else:
        if qp.get("minFormatScore") != -9999:
            errors.append(f"minFormatScore {qp.get('minFormatScore')} != expected -9999")

    # 8. When custom_qualities set, only those qualities are enabled
    if profile.custom_qualities is not None:
        enabled_names = set()
        for item in qp.get("items", []):
            if item.get("allowed") and item.get("quality", {}).get("name"):
                enabled_names.add(item["quality"]["name"])
            for sub in item.get("items", []):
                if sub.get("allowed") and sub.get("quality", {}).get("name"):
                    enabled_names.add(sub["quality"]["name"])
        # Normalize remux names — Sonarr uses "Bluray-Xp Remux", Radarr uses "Remux-Xp"
        _remux_normalize = {
            "Bluray-1080p Remux": "Remux-1080p",
            "Bluray-2160p Remux": "Remux-2160p",
        }
        normalized_enabled = {_remux_normalize.get(n, n) for n in enabled_names}
        normalized_expected = {_remux_normalize.get(n, n) for n in profile.custom_qualities}
        if normalized_enabled != normalized_expected:
            extra = normalized_enabled - normalized_expected
            missing = normalized_expected - normalized_enabled
            if extra:
                errors.append(f"Unexpected enabled qualities: {extra}")
            if missing:
                errors.append(f"Expected enabled qualities missing: {missing}")

    # 9. Subtitle CFs present when expected
    if profile.avoid_hardcoded_subs and "ProfSync Hardcoded Subs" not in profsync_cfs:
        errors.append("Missing 'ProfSync Hardcoded Subs' CF")
    if profile.avoid_rushed_subs and "ProfSync Rushed Subs" not in profsync_cfs:
        errors.append("Missing 'ProfSync Rushed Subs' CF")
    if profile.avoid_fan_subs in ("penalize", "block") and "ProfSync Fan Subs" not in profsync_cfs:
        errors.append("Missing 'ProfSync Fan Subs' CF")

    # 10. Codec CFs match preferences
    if profile.codec_preferences is not None:
        for codec, pref in profile.codec_preferences.items():
            if pref == "prefer":
                name = f"ProfSync {codec} Preferred"
                if name not in profsync_cfs:
                    errors.append(f"Missing '{name}' CF")
            elif pref == "block":
                name = f"ProfSync {codec} Blocked"
                if name not in profsync_cfs:
                    errors.append(f"Missing '{name}' CF")

    return ValidationResult(ok=len(errors) == 0, errors=errors)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== ProfSync Matrix Test ===")

    # Load credentials
    sonarr_config, radarr_config = load_teststack_credentials()
    if not sonarr_config and not radarr_config:
        print("ERROR: No teststack credentials found in test/.env")
        sys.exit(1)

    # Build clients
    clients: list[tuple[str, ArrClient]] = []
    if sonarr_config:
        clients.append(("Sonarr", ArrClient(sonarr_config.url, sonarr_config.api_key, "Sonarr")))
    if radarr_config:
        clients.append(("Radarr", ArrClient(radarr_config.url, radarr_config.api_key, "Radarr")))

    # Verify connections
    for name, client in clients:
        try:
            client.verify_connection()
            print(f"Connected to {name} v{client.version}")
        except ArrClientError as e:
            print(f"ERROR: Could not connect to {name}: {e}")
            sys.exit(1)

    # Fetch TRaSH data once
    print("Fetching TRaSH data...", end="", flush=True)
    from trash_fetcher import fetch_group_tiers
    group_tiers = fetch_group_tiers()
    total = sum(len(v) for v in group_tiers.values())
    print(f" done ({total} groups)")
    print()

    total_cases = len(ALL_CASES)
    passed = 0
    failed = 0
    failures: list[tuple[str, str, list[str]]] = []

    for idx, (case_name, kwargs) in enumerate(ALL_CASES, 1):
        # Build UserProfile
        profile = UserProfile(sonarr=sonarr_config, radarr=radarr_config, **kwargs)

        # Build CFs
        all_cfs = build_all_custom_formats(group_tiers, profile)

        # Track per-app results
        app_results: list[str] = []
        case_ok = True

        for app_name, client in clients:
            # Cleanup
            cleanup_profsync(client)

            # Apply
            try:
                profile_id = apply_to_app(
                    client, all_cfs, profile, group_tiers, skip_backup=True
                )
                if profile_id is None:
                    app_results.append(f"{app_name}: apply failed")
                    case_ok = False
                    continue
            except Exception as e:
                app_results.append(f"{app_name}: exception: {e}")
                case_ok = False
                continue

            # Validate
            result = validate_test_case(client, profile, all_cfs)
            if result.ok:
                app_results.append(f"{app_name}: OK")
            else:
                app_results.append(f"{app_name}: FAIL")
                case_ok = False
                for err in result.errors:
                    failures.append((case_name, app_name, [err]))

        status = "PASS" if case_ok else "FAIL"
        detail = ", ".join(app_results)
        label = f"[{idx:3d}/{total_cases}] {case_name}"
        dots = "." * max(1, 55 - len(label))
        print(f"{label} {dots} {status} ({detail})")

        if case_ok:
            passed += 1
        else:
            failed += 1
            for case, app, errs in failures:
                if case == case_name:
                    for err in errs:
                        print(f"         {app}: {err}")

    # Cleanup after last test
    for _, client in clients:
        cleanup_profsync(client)

    print()
    print(f"=== Results: {passed}/{total_cases} passed, {failed} failed ===")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
