"""Group profiler — aggregates release data into per-group quality profiles."""

from datetime import datetime, timezone

from sqlalchemy import func, case, and_

from profsync.db import get_session
from profsync.logging import setup_logging
from profsync.models import (
    GroupProfile, Nuke, ParsedRelease, Release, ReleaseQuality, TrashGroupTier,
)

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
        # Preload TRaSH tier lookup — best non-LQ tier per group
        trash_lookup = _build_trash_lookup(session)

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
                _compute_profile(session, group_name, resolution, media_type, trash_lookup)
            except Exception:
                logger.exception(
                    "Error profiling %s/%s/%s", group_name, resolution, media_type
                )

        session.commit()
        logger.info("Analysis complete — %d profiles updated", len(combos))


def _build_trash_lookup(session) -> dict:
    """Build a lookup: group_name -> best TrashGroupTier row (lowest tier_number, non-LQ).

    Also stores LQ status separately.
    """
    all_trash = session.query(TrashGroupTier).all()
    lookup = {}  # group_name -> {"best": TrashGroupTier | None, "is_lq": bool}
    for t in all_trash:
        entry = lookup.setdefault(t.group_name, {"best": None, "is_lq": False})
        if t.trash_tier_category == "lq":
            entry["is_lq"] = True
        else:
            if entry["best"] is None or t.trash_tier_number < entry["best"].trash_tier_number:
                entry["best"] = t
    return lookup


def _compute_profile(
    session, group_name: str, resolution: str, media_type: str, trash_lookup: dict
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

    # Audio format distribution (from parsed release name)
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

    # Codec distribution (from guessit-parsed video_codec)
    codec_dist: dict[str, int] = {}
    for r in releases:
        vc = r.ParsedRelease.video_codec or "Unknown"
        codec_dist[vc] = codec_dist.get(vc, 0) + 1
    codec_distribution = {
        k: round(v / release_count, 2) for k, v in codec_dist.items()
    }

    # Video profile distribution (HDR10, DV, SDR — None → SDR)
    vp_dist: dict[str, int] = {}
    for r in releases:
        vp = r.ParsedRelease.video_profile or "SDR"
        vp_dist[vp] = vp_dist.get(vp, 0) + 1
    video_profile_distribution = {
        k: round(v / release_count, 2) for k, v in vp_dist.items()
    }

    # Audio bitrate and bit depth from ReleaseQuality
    audio_bitrates = [
        r.ReleaseQuality.audio_bitrate_kbps
        for r in quality_releases
        if r.ReleaseQuality.audio_bitrate_kbps
    ]
    avg_audio_bitrate = _mean(audio_bitrates)

    bit_depths = [
        r.ReleaseQuality.bit_depth
        for r in quality_releases
        if r.ReleaseQuality.bit_depth is not None
    ]
    avg_bit_depth = _mean(bit_depths)

    # Quality consistency (inverse of CRF std dev, normalized)
    quality_consistency = 0.0
    if crf_std is not None and crf_std >= 0:
        quality_consistency = max(0.0, 1.0 - (crf_std / 5.0))

    # Date range
    pre_dates = [r.Release.pre_at for r in releases if r.Release.pre_at]
    first_seen = min(pre_dates) if pre_dates else None
    last_seen = max(pre_dates) if pre_dates else None

    # Compute tier
    nuke_rate = nuke_count / release_count if release_count > 0 else 0
    proper_repack_rate = proper_repack_count / release_count if release_count > 0 else 0

    # TRaSH lookup for this group
    trash_entry = trash_lookup.get(group_name)
    trash_best = trash_entry["best"] if trash_entry else None
    trash_is_lq = trash_entry["is_lq"] if trash_entry else False

    # Lossless audio fraction for scoring
    lossless_audio_pct = sum(
        v for k, v in audio_distribution.items()
        if any(fmt in k for fmt in ["TrueHD", "DTS-HD MA", "DTS:X", "LPCM", "FLAC", "Atmos"])
    )

    computed_tier, tier_confidence, tier_factors = _compute_tier(
        release_count=release_count,
        nuke_rate=nuke_rate,
        proper_repack_rate=proper_repack_rate,
        avg_crf=avg_crf,
        avg_video_bitrate=avg_video_bitrate,
        nfo_coverage=nfo_coverage,
        lossless_audio_pct=lossless_audio_pct,
        trash_best=trash_best,
        trash_is_lq=trash_is_lq,
    )

    # Denormalized TRaSH fields
    trash_tier_name_val = None
    trash_score_val = None
    if trash_is_lq:
        trash_tier_name_val = "Low Quality"
        trash_score_val = 0
    elif trash_best:
        trash_tier_name_val = trash_best.trash_tier_name
        trash_score_val = trash_best.trash_score

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
    profile.codec_distribution = codec_distribution
    profile.video_profile_distribution = video_profile_distribution
    profile.avg_audio_bitrate_kbps = avg_audio_bitrate
    profile.avg_bit_depth = avg_bit_depth
    profile.trash_tier_name = trash_tier_name_val
    profile.trash_score = trash_score_val
    profile.updated_at = datetime.now(timezone.utc)


def _compute_tier(
    release_count: int,
    nuke_rate: float,
    proper_repack_rate: float,
    avg_crf: float | None,
    avg_video_bitrate: float | None,
    nfo_coverage: float,
    lossless_audio_pct: float,
    trash_best,
    trash_is_lq: bool,
) -> tuple[str | None, float, dict]:
    """Compute quality tier using TRaSH-blended scoring.

    score = quality_score (0-60) + reliability_score (0-40)
    Returns (tier, confidence, factors_dict).
    """
    if release_count < MIN_RELEASES_FOR_TIER:
        return None, 0.0, {"reason": "insufficient_data"}

    signals = {}

    # --- QUALITY SCORE (0-60) ---
    if trash_is_lq:
        # LQ tag forces F tier
        quality_score = 0.0
        signals["trash_tier"] = "LQ"
        signals["trash_score"] = 0
    elif trash_best and trash_best.trash_score is not None:
        # TRaSH-validated group
        quality_score = min(60.0, trash_best.trash_score / 3500 * 60)
        signals["trash_tier"] = trash_best.trash_tier_name
        signals["trash_score"] = trash_best.trash_score
    else:
        # No TRaSH data — use CRF or bitrate, capped at 30
        if avg_crf is not None:
            quality_score = min(30.0, max(0.0, (22 - avg_crf) * 3))
            signals["avg_crf"] = round(avg_crf, 1)
        elif avg_video_bitrate is not None:
            quality_score = min(20.0, avg_video_bitrate / 10000 * 20)
            signals["avg_bitrate_kbps"] = round(avg_video_bitrate, 0)
        else:
            quality_score = 0.0

    # --- RELIABILITY SCORE (0-40) ---

    # Nuke rate: dominant signal
    nuke_score = max(-20.0, 20 - nuke_rate * 200)
    signals["nuke_rate"] = round(nuke_rate, 4)

    # Lossless audio fraction
    audio_score = lossless_audio_pct * 10
    signals["lossless_audio_pct"] = round(lossless_audio_pct, 2)

    # Volume bonus
    volume_score = min(5.0, release_count / 200 * 5)

    # Proper/repack rate penalty
    proper_score = max(-5.0, 5 - proper_repack_rate * 50)

    # NFO coverage bonus
    nfo_score = nfo_coverage * 5

    reliability_score = nuke_score + audio_score + volume_score + proper_score + nfo_score
    reliability_score = max(0.0, min(40.0, reliability_score))

    # --- TOTAL ---
    total_score = quality_score + reliability_score

    # Force F for LQ groups regardless of reliability
    if trash_is_lq:
        total_score = 0.0

    total_score = max(0.0, min(100.0, total_score))

    # Map score to tier
    tier = "F"
    for tier_name, threshold in TIER_THRESHOLDS.items():
        if total_score >= threshold:
            tier = tier_name
            break

    if trash_is_lq:
        tier = "F"

    # --- CONFIDENCE ---
    confidence = 0.1  # nuke_rate always populated
    if trash_best or trash_is_lq:
        confidence += 0.4
    if avg_crf is not None:
        confidence += 0.2
    if release_count >= 50:
        confidence += 0.2
    if nfo_coverage > 0.3:
        confidence += 0.1
    confidence = min(1.0, confidence)

    factors = {
        "quality_score": round(quality_score, 1),
        "reliability_score": round(reliability_score, 1),
        "total_score": round(total_score, 1),
        "signals": signals,
    }

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
