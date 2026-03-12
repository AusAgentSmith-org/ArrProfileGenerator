"""Fetch TRaSH Guides tier data from GitHub without DB dependency."""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import requests


RADARR_BASE = (
    "https://raw.githubusercontent.com/TRaSH-Guides/Guides/master/docs/json/radarr/cf"
)
SONARR_BASE = (
    "https://raw.githubusercontent.com/TRaSH-Guides/Guides/master/docs/json/sonarr/cf"
)

# filename slug -> (category, tier_number)
TIER_FILES = {
    "hd-bluray-tier-01": ("hd-bluray", 1),
    "hd-bluray-tier-02": ("hd-bluray", 2),
    "hd-bluray-tier-03": ("hd-bluray", 3),
    "uhd-bluray-tier-01": ("uhd-bluray", 1),
    "uhd-bluray-tier-02": ("uhd-bluray", 2),
    "uhd-bluray-tier-03": ("uhd-bluray", 3),
    "web-tier-01": ("web", 1),
    "web-tier-02": ("web", 2),
    "web-tier-03": ("web", 3),
    "remux-tier-01": ("remux", 1),
    "remux-tier-02": ("remux", 2),
    "remux-tier-03": ("remux", 3),
    "lq": ("lq", 0),
}

# Tier number → key used in profile_builder TIER_SCORES
TIER_NUMBER_TO_KEY = {1: "Tier 01", 2: "Tier 02", 3: "Tier 03", 0: "LQ"}

# Cache location and TTL
CACHE_DIR = Path.home() / ".cache" / "profsync"
CACHE_FILE = CACHE_DIR / "trash_tiers.json"
CACHE_TTL_HOURS = 24


def _get_cache_file() -> Path:
    """Ensure cache directory exists and return cache file path."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_FILE


def _is_cache_fresh() -> bool:
    """Check if cache file exists and is within TTL."""
    cache_file = _get_cache_file()
    if not cache_file.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
    return age < timedelta(hours=CACHE_TTL_HOURS)


def _load_cache() -> dict[str, list[str]] | None:
    """Load group tiers from cache if fresh."""
    if not _is_cache_fresh():
        return None
    try:
        with open(_get_cache_file()) as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(data: dict[str, list[str]]) -> None:
    """Save group tiers to cache."""
    try:
        cache_file = _get_cache_file()
        with open(cache_file, "w") as f:
            json.dump(data, f)
    except Exception:
        pass  # Silently fail on cache write errors


def fetch_json(url: str, retries: int = 3) -> dict | None:
    """Fetch JSON from URL with simple retry."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def extract_groups(data: dict) -> list[str]:
    """Extract group names from TRaSH CF JSON specifications."""
    groups = []
    for spec in data.get("specifications", []):
        if spec.get("implementation") != "ReleaseGroupSpecification":
            continue
        fields = spec.get("fields", {})
        value = fields.get("value", "")
        if not value:
            continue
        # Strip regex anchors
        cleaned = value.strip("^$")
        # Extract names from parenthesized groups, or use the whole string
        paren_groups = re.findall(r"\(([^)]+)\)", cleaned)
        if paren_groups:
            for group in paren_groups:
                # Handle alternation within parens
                groups.extend(group.split("|"))
        else:
            # No parens — handle alternation at top level
            groups.extend(cleaned.split("|"))
    # Clean up: strip whitespace, remove empty strings
    return [g.strip() for g in groups if g.strip()]


def _fetch_tier_file(
    slug: str,
    category: str,
    tier_number: int,
    base_url: str,
) -> tuple[str, list[str]] | None:
    """Fetch a single tier file and return (tier_key, groups)."""
    url = f"{base_url}/{slug}.json"
    data = fetch_json(url)
    if data is None:
        return None

    groups = extract_groups(data)
    if not groups:
        return None

    tier_key = TIER_NUMBER_TO_KEY.get(tier_number)
    if not tier_key:
        return None

    return (tier_key, groups)


def fetch_group_tiers(use_cache: bool = True) -> dict[str, list[str]]:
    """Fetch TRaSH tier data from GitHub.

    Returns dict[str, list[str]]: {"Tier 01": ["FLUX", "DON", ...], "LQ": [...], ...}
    Groups are deduplicated across Sonarr/Radarr (takes group from either source).
    """
    # Try cache first
    if use_cache:
        cached = _load_cache()
        if cached:
            return cached

    # Fetch all tier files concurrently
    tier_groups: dict[str, list[str]] = {}
    seen_groups: set[tuple[str, str]] = set()  # (tier_key, group_name)

    tasks = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        for slug, (category, tier_number) in TIER_FILES.items():
            for base_url in [RADARR_BASE, SONARR_BASE]:
                future = executor.submit(
                    _fetch_tier_file, slug, category, tier_number, base_url
                )
                tasks.append(future)

        for future in as_completed(tasks):
            result = future.result()
            if result:
                tier_key, groups = result
                # Deduplicate across sources — take first seen for each group+tier
                for group in groups:
                    key = (tier_key, group)
                    if key not in seen_groups:
                        tier_groups.setdefault(tier_key, []).append(group)
                        seen_groups.add(key)

    # Save to cache
    if tier_groups:
        _save_cache(tier_groups)

    return tier_groups
