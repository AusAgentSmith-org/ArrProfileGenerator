"""Group profiler — aggregates release data into per-group quality profiles."""

from datetime import datetime, timezone

from sqlalchemy import func, case, and_

from profsync.db import get_session
from profsync.logging import setup_logging
from profsync.models import GroupProfile, Nuke, ParsedRelease, Release, ReleaseQuality

logger = setup_logging("analyzer.profiler")

# Minimum releases needed before we compute a tier
MIN_RELEASES_FOR_TIER = 10

# Tier thresholds based on a composite quality score (0-100)
TIER_THRESHOLDS = {
    "A+": 90,
    "A": 80,
    "B+": 70,
    "B": 60,
    "C+": 50,
    "C": 40,
    "D": 25,
    # Below 25 = "F"
}


def run_analysis() -> None:
    """Run full analysis cycle: compute profiles for all groups."""
    with get_session() as session:
        # Get all distinct group + resolution + media_type combos
        combos = (
            session.query(
                ParsedRelease.group,
                ParsedRelease.resolution,
                ParsedRelease.media_type,
            )
            .filter(
                ParsedRelease.group.isnot(None),
                ParsedRelease.group != "",
            )
            .group_by(
                ParsedRelease.group,
                ParsedRelease.resolution,
                ParsedRelease.media_type,
            )
            .having(func.count(ParsedRelease.id) >= 3)
            .all()
        )

        logger.info("Analyzing %d group/resolution/type combinations", len(combos))

        for group_name, resolution, media_type in combos:
            try:
                _compute_profile(session, group_name, resolution, media_type)
            except Exception:
                logger.exception(
                    "Error profiling %s/%s/%s", group_name, resolution, media_type
                )

        session.commit()
        logger.info("Analysis complete — %d profiles updated", len(combos))


def _compute_profile(
    session, group_name: str, resolution: str, media_type: str
) -> None:
    """Compute or update a group profile for a specific resolution and media type."""

    # Get all parsed releases for this group/resolution/type
    releases = (
        session.query(ParsedRelease, Release, ReleaseQuality)
        .join(Release, ParsedRelease.release_id == Release.id)
        .outerjoin(ReleaseQuality, ReleaseQuality.release_id == Release.id)
        .filter(
            ParsedRelease.group == group_name,
            ParsedRelease.resolution == resolution,
            ParsedRelease.media_type == media_type,
        )
        .all()
    )

    if not releases:
        return

    release_count = len(releases)

    # Count nukes for this group's releases
    release_ids = [r.Release.id for r in releases]
    nuke_count = (
        session.query(func.count(Nuke.id))
        .filter(
            Nuke.release_id.in_(release_ids),
            Nuke.type == "nuke",
        )
        .scalar()
    )

    # Count propers/repacks
    proper_repack_count = sum(
        1 for r in releases if r.ParsedRelease.is_proper or r.ParsedRelease.is_repack
    )

    # Aggregate quality metrics from NFO data
    quality_releases = [r for r in releases if r.ReleaseQuality is not None]
    nfo_coverage = len(quality_releases) / release_count if release_count > 0 else 0

    # Video bitrate stats
    video_bitrates = [
        r.ReleaseQuality.video_bitrate_kbps
        for r in quality_releases
        if r.ReleaseQuality.video_bitrate_kbps
    ]
    avg_video_bitrate = _mean(video_bitrates)

    # CRF stats
    crfs = [
        r.ReleaseQuality.crf_value
        for r in quality_releases
        if r.ReleaseQuality.crf_value is not None
    ]
    avg_crf = _mean(crfs)
    crf_std = _std_dev(crfs)

    # Encode ratio
    encode_ratios = [
        r.ReleaseQuality.encode_ratio
        for r in quality_releases
        if r.ReleaseQuality.encode_ratio is not None
    ]
    avg_encode_ratio = _mean(encode_ratios)

    # File sizes
    file_sizes = [
        r.ReleaseQuality.total_size_mb
        for r in quality_releases
        if r.ReleaseQuality.total_size_mb
    ]
    avg_file_size = _mean(file_sizes)

    # Audio format distribution
    audio_dist: dict[str, int] = {}
    for r in releases:
        codec = r.ParsedRelease.audio_codec or "Unknown"
        if r.ParsedRelease.audio_atmos:
            codec += " Atmos"
        audio_dist[codec] = audio_dist.get(codec, 0) + 1
    audio_distribution = {
        k: round(v / release_count, 2) for k, v in audio_dist.items()
    }

    # Source distribution
    source_dist: dict[str, int] = {}
    for r in releases:
        src = r.ParsedRelease.source or "Unknown"
        source_dist[src] = source_dist.get(src, 0) + 1
    source_distribution = {
        k: round(v / release_count, 2) for k, v in source_dist.items()
    }

    # Quality consistency (inverse of CRF std dev, normalized)
    quality_consistency = 0.0
    if crf_std is not None and crf_std >= 0:
        # Lower std dev = more consistent. Map 0-5 range to 1.0-0.0
        quality_consistency = max(0.0, 1.0 - (crf_std / 5.0))

    # Date range
    pre_dates = [r.Release.pre_at for r in releases if r.Release.pre_at]
    first_seen = min(pre_dates) if pre_dates else None
    last_seen = max(pre_dates) if pre_dates else None

    # Compute tier
    nuke_rate = nuke_count / release_count if release_count > 0 else 0
    proper_repack_rate = proper_repack_count / release_count if release_count > 0 else 0

    computed_tier, tier_confidence, tier_factors = _compute_tier(
        release_count=release_count,
        nuke_rate=nuke_rate,
        avg_crf=avg_crf,
        crf_std=crf_std,
        nfo_coverage=nfo_coverage,
        audio_distribution=audio_distribution,
        resolution=resolution,
        quality_consistency=quality_consistency,
    )

    # Upsert profile
    profile = (
        session.query(GroupProfile)
        .filter_by(
            group_name=group_name,
            resolution=resolution,
            media_type=media_type,
        )
        .first()
    )

    if not profile:
        profile = GroupProfile(
            group_name=group_name,
            resolution=resolution,
            media_type=media_type,
        )
        session.add(profile)

    profile.release_count = release_count
    profile.first_seen = first_seen
    profile.last_seen = last_seen
    profile.avg_video_bitrate_kbps = avg_video_bitrate
    profile.avg_crf = avg_crf
    profile.crf_std_dev = crf_std
    profile.avg_encode_ratio = avg_encode_ratio
    profile.avg_file_size_mb = avg_file_size
    profile.audio_format_distribution = audio_distribution
    profile.source_distribution = source_distribution
    profile.nuke_rate = nuke_rate
    profile.proper_repack_rate = proper_repack_rate
    profile.nfo_coverage = nfo_coverage
    profile.quality_consistency = quality_consistency
    profile.computed_tier = computed_tier
    profile.tier_confidence = tier_confidence
    profile.tier_factors = tier_factors
    profile.updated_at = datetime.now(timezone.utc)


def _compute_tier(
    release_count: int,
    nuke_rate: float,
    avg_crf: float | None,
    crf_std: float | None,
    nfo_coverage: float,
    audio_distribution: dict,
    resolution: str,
    quality_consistency: float,
) -> tuple[str | None, float, dict]:
    """Compute quality tier from aggregated metrics.

    Returns (tier, confidence, factors_dict).
    """
    if release_count < MIN_RELEASES_FOR_TIER:
        return None, 0.0, {"reason": "insufficient_data"}

    score = 50.0  # Start at midpoint
    factors = {}

    # --- Nuke rate (huge negative signal) ---
    # 0% nukes = +15, 5% = 0, 10%+ = -30
    nuke_score = max(-30, 15 - (nuke_rate * 300))
    score += nuke_score
    factors["nuke_rate"] = {"value": round(nuke_rate, 3), "score_impact": round(nuke_score, 1)}

    # --- CRF value (lower is better quality, higher file size) ---
    if avg_crf is not None:
        # For 2160p: CRF 14-16 is excellent, 18+ is poor
        # For 1080p: CRF 17-19 is excellent, 22+ is poor
        if resolution == "2160p":
            crf_score = max(-15, min(15, (18 - avg_crf) * 5))
        else:
            crf_score = max(-15, min(15, (20 - avg_crf) * 4))
        score += crf_score
        factors["avg_crf"] = {"value": round(avg_crf, 1), "score_impact": round(crf_score, 1)}

    # --- Quality consistency ---
    consistency_score = quality_consistency * 10  # 0-10 points
    score += consistency_score
    factors["consistency"] = {"value": round(quality_consistency, 2), "score_impact": round(consistency_score, 1)}

    # --- Audio quality ---
    lossless_audio = sum(
        v for k, v in audio_distribution.items()
        if any(fmt in k for fmt in ["TrueHD", "DTS-HD MA", "DTS:X", "LPCM", "FLAC", "Atmos"])
    )
    audio_score = lossless_audio * 10  # Up to 10 points if 100% lossless
    score += audio_score
    factors["lossless_audio_pct"] = {"value": round(lossless_audio, 2), "score_impact": round(audio_score, 1)}

    # --- NFO coverage (meta signal — groups with NFOs tend to be more established) ---
    nfo_score = nfo_coverage * 5  # Up to 5 bonus points
    score += nfo_score
    factors["nfo_coverage"] = {"value": round(nfo_coverage, 2), "score_impact": round(nfo_score, 1)}

    # --- Volume bonus (more releases = more reliable data) ---
    volume_score = min(5, release_count / 100 * 5)
    score += volume_score
    factors["volume"] = {"value": release_count, "score_impact": round(volume_score, 1)}

    # Clamp to 0-100
    score = max(0, min(100, score))
    factors["total_score"] = round(score, 1)

    # Map score to tier
    tier = "F"
    for tier_name, threshold in TIER_THRESHOLDS.items():
        if score >= threshold:
            tier = tier_name
            break

    # Confidence based on data completeness
    confidence = min(1.0, (
        (0.3 if avg_crf is not None else 0.0) +
        (0.2 if nfo_coverage > 0.3 else nfo_coverage * 0.67) +
        (0.2 if release_count >= 50 else release_count / 250) +
        (0.15 if quality_consistency > 0 else 0.0) +
        (0.15 if nuke_rate is not None else 0.0)
    ))

    return tier, round(confidence, 2), factors


def _mean(values: list) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _std_dev(values: list) -> float | None:
    if len(values) < 2:
        return None
    m = sum(values) / len(values)
    variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return variance ** 0.5
