"""Web dashboard for ProfSync pipeline monitoring."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, desc, case

from profsync.db import get_session
from profsync.models import GroupProfile, Nuke, ParsedRelease, Release, ReleaseQuality, TrashGroupTier
from profsync.queue import get_redis, queue_length, QUEUE_RAW_RELEASES, QUEUE_NFO_NEEDED

app = FastAPI(title="ProfSync Dashboard")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with get_session() as session:
        stats = _get_stats(session)
        recent = _get_recent_releases(session)
        profiles = _get_top_profiles(session)
        category_breakdown = _get_category_breakdown(session)
        nfo_stats = _get_nfo_stats(session)

    redis = get_redis()
    queue_stats = {
        "raw_releases": queue_length(redis, QUEUE_RAW_RELEASES),
        "nfo_needed": queue_length(redis, QUEUE_NFO_NEEDED),
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "recent": recent,
        "profiles": profiles,
        "queue_stats": queue_stats,
        "category_breakdown": category_breakdown,
        "nfo_stats": nfo_stats,
    })


@app.get("/api/stats")
def api_stats():
    with get_session() as session:
        stats = _get_stats(session)
    redis = get_redis()
    stats["queues"] = {
        "raw_releases": queue_length(redis, QUEUE_RAW_RELEASES),
        "nfo_needed": queue_length(redis, QUEUE_NFO_NEEDED),
    }
    return stats


@app.get("/groups", response_class=HTMLResponse)
def groups_page(request: Request):
    with get_session() as session:
        profiles = (
            session.query(GroupProfile)
            .filter(GroupProfile.release_count >= 3)
            .order_by(desc(GroupProfile.release_count))
            .all()
        )
        # Build TRaSH tier lookup for all groups in results
        group_names = [p.group_name for p in profiles]
        trash_rows = (
            session.query(TrashGroupTier)
            .filter(TrashGroupTier.group_name.in_(group_names))
            .all()
        ) if group_names else []
        trash_lookup = {}
        for t in trash_rows:
            trash_lookup.setdefault(t.group_name, []).append(t)
    return templates.TemplateResponse("groups.html", {
        "request": request,
        "profiles": profiles,
        "trash_lookup": trash_lookup,
    })


@app.get("/groups/{group_name}", response_class=HTMLResponse)
def group_detail(request: Request, group_name: str):
    with get_session() as session:
        profiles = (
            session.query(GroupProfile)
            .filter(GroupProfile.group_name == group_name)
            .order_by(GroupProfile.resolution)
            .all()
        )
        recent = (
            session.query(ParsedRelease, Release, ReleaseQuality)
            .join(Release, ParsedRelease.release_id == Release.id)
            .outerjoin(ReleaseQuality, ReleaseQuality.release_id == Release.id)
            .filter(ParsedRelease.group == group_name)
            .order_by(desc(Release.pre_at))
            .limit(50)
            .all()
        )
        trash_tiers = (
            session.query(TrashGroupTier)
            .filter(TrashGroupTier.group_name == group_name)
            .all()
        )
    return templates.TemplateResponse("group_detail.html", {
        "request": request,
        "group_name": group_name,
        "profiles": profiles,
        "recent": recent,
        "trash_tiers": trash_tiers,
    })


@app.get("/releases", response_class=HTMLResponse)
def releases_page(request: Request):
    with get_session() as session:
        releases = (
            session.query(ParsedRelease, Release, ReleaseQuality)
            .join(Release, ParsedRelease.release_id == Release.id)
            .outerjoin(ReleaseQuality, ReleaseQuality.release_id == Release.id)
            .order_by(desc(Release.pre_at))
            .limit(200)
            .all()
        )
    return templates.TemplateResponse("releases.html", {
        "request": request,
        "releases": releases,
    })


@app.get("/quality", response_class=HTMLResponse)
def quality_page(request: Request):
    with get_session() as session:
        quality_stats = _get_quality_stats(session)
        recent_quality = _get_recent_quality(session)
    return templates.TemplateResponse("quality.html", {
        "request": request,
        "stats": quality_stats,
        "recent": recent_quality,
    })


def _get_stats(session) -> dict:
    total_releases = session.query(func.count(Release.id)).scalar() or 0
    total_parsed = session.query(func.count(ParsedRelease.id)).scalar() or 0
    total_nfos = session.query(func.count(ReleaseQuality.id)).scalar() or 0
    total_nukes = session.query(func.count(Nuke.id)).scalar() or 0
    total_profiles = session.query(func.count(GroupProfile.id)).scalar() or 0
    unique_groups = (
        session.query(func.count(func.distinct(ParsedRelease.group))).scalar() or 0
    )

    movies = (
        session.query(func.count(ParsedRelease.id))
        .filter(ParsedRelease.media_type == "movie")
        .scalar() or 0
    )
    series = (
        session.query(func.count(ParsedRelease.id))
        .filter(ParsedRelease.media_type == "series")
        .scalar() or 0
    )

    tier_dist = {}
    for tier, count in (
        session.query(GroupProfile.computed_tier, func.count(GroupProfile.id))
        .group_by(GroupProfile.computed_tier)
        .all()
    ):
        tier_dist[tier or "Unranked"] = count

    return {
        "total_releases": total_releases,
        "total_parsed": total_parsed,
        "total_nfos": total_nfos,
        "total_nukes": total_nukes,
        "total_profiles": total_profiles,
        "unique_groups": unique_groups,
        "movies": movies,
        "series": series,
        "tier_distribution": tier_dist,
    }


def _get_recent_releases(session, limit: int = 25) -> list[dict]:
    rows = (
        session.query(ParsedRelease, Release)
        .join(Release, ParsedRelease.release_id == Release.id)
        .order_by(desc(Release.pre_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "name": r.Release.name,
            "title": r.ParsedRelease.title,
            "group": r.ParsedRelease.group,
            "resolution": r.ParsedRelease.resolution,
            "source": r.ParsedRelease.source,
            "video_codec": r.ParsedRelease.video_codec,
            "audio_codec": r.ParsedRelease.audio_codec,
            "media_type": r.ParsedRelease.media_type,
            "category": r.Release.category,
            "pre_at": r.Release.pre_at.strftime("%Y-%m-%d %H:%M") if r.Release.pre_at else "",
        }
        for r in rows
    ]


def _get_top_profiles(session, limit: int = 20) -> list[dict]:
    rows = (
        session.query(GroupProfile)
        .filter(GroupProfile.release_count >= 3)
        .order_by(desc(GroupProfile.release_count))
        .limit(limit)
        .all()
    )
    return [
        {
            "group_name": p.group_name,
            "resolution": p.resolution,
            "media_type": p.media_type,
            "release_count": p.release_count,
            "computed_tier": p.computed_tier or "—",
            "nuke_rate": f"{p.nuke_rate * 100:.1f}%" if p.nuke_rate is not None else "—",
            "avg_crf": f"{p.avg_crf:.1f}" if p.avg_crf is not None else "—",
            "nfo_coverage": f"{p.nfo_coverage * 100:.0f}%" if p.nfo_coverage is not None else "—",
            "audio_distribution": p.audio_format_distribution or {},
        }
        for p in rows
    ]


def _get_category_breakdown(session) -> list[dict]:
    rows = (
        session.query(Release.category, func.count(Release.id))
        .group_by(Release.category)
        .order_by(desc(func.count(Release.id)))
        .all()
    )
    return [{"category": cat or "Unknown", "count": count} for cat, count in rows]


def _get_nfo_stats(session) -> dict:
    """NFO pipeline stats for the dashboard."""
    # Status breakdown
    status_rows = (
        session.query(ParsedRelease.nfo_status, func.count(ParsedRelease.id))
        .group_by(ParsedRelease.nfo_status)
        .all()
    )
    nfo_status = {status: count for status, count in status_rows}

    # Source breakdown
    source_rows = (
        session.query(ReleaseQuality.nfo_source, func.count(ReleaseQuality.id))
        .group_by(ReleaseQuality.nfo_source)
        .all()
    )
    nfo_sources = {src or "unknown": count for src, count in source_rows}

    # Average parse confidence
    avg_confidence = (
        session.query(func.avg(ReleaseQuality.parse_confidence))
        .scalar()
    ) or 0

    return {
        "status": nfo_status,
        "sources": nfo_sources,
        "avg_confidence": avg_confidence,
    }


def _get_quality_stats(session) -> dict:
    """Detailed quality breakdown for the /quality page."""
    total = session.query(func.count(ReleaseQuality.id)).scalar() or 0

    # Source breakdown
    source_rows = (
        session.query(ReleaseQuality.nfo_source, func.count(ReleaseQuality.id))
        .group_by(ReleaseQuality.nfo_source)
        .order_by(desc(func.count(ReleaseQuality.id)))
        .all()
    )

    # Video codec breakdown
    codec_rows = (
        session.query(ReleaseQuality.video_codec_detail, func.count(ReleaseQuality.id))
        .filter(ReleaseQuality.video_codec_detail.isnot(None))
        .group_by(ReleaseQuality.video_codec_detail)
        .order_by(desc(func.count(ReleaseQuality.id)))
        .all()
    )

    # Audio format breakdown
    audio_rows = (
        session.query(ReleaseQuality.audio_format_detail, func.count(ReleaseQuality.id))
        .filter(ReleaseQuality.audio_format_detail.isnot(None))
        .group_by(ReleaseQuality.audio_format_detail)
        .order_by(desc(func.count(ReleaseQuality.id)))
        .all()
    )

    # Bitrate distribution (buckets)
    bitrate_buckets = []
    for label, low, high in [
        ("<2 Mbps", 0, 2000),
        ("2-4 Mbps", 2000, 4000),
        ("4-8 Mbps", 4000, 8000),
        ("8-15 Mbps", 8000, 15000),
        ("15-30 Mbps", 15000, 30000),
        ("30+ Mbps", 30000, 999999),
    ]:
        count = (
            session.query(func.count(ReleaseQuality.id))
            .filter(
                ReleaseQuality.video_bitrate_kbps >= low,
                ReleaseQuality.video_bitrate_kbps < high,
            )
            .scalar() or 0
        )
        if count > 0:
            bitrate_buckets.append({"label": label, "count": count})

    # NFO status breakdown
    status_rows = (
        session.query(ParsedRelease.nfo_status, func.count(ParsedRelease.id))
        .group_by(ParsedRelease.nfo_status)
        .all()
    )

    # Parse confidence distribution
    confidence_buckets = []
    for label, low, high in [
        ("0-20%", 0, 0.2),
        ("20-40%", 0.2, 0.4),
        ("40-60%", 0.4, 0.6),
        ("60-80%", 0.6, 0.8),
        ("80-100%", 0.8, 1.01),
    ]:
        count = (
            session.query(func.count(ReleaseQuality.id))
            .filter(
                ReleaseQuality.parse_confidence >= low,
                ReleaseQuality.parse_confidence < high,
            )
            .scalar() or 0
        )
        if count > 0:
            confidence_buckets.append({"label": label, "count": count})

    # Aggregate stats
    avg_bitrate = session.query(func.avg(ReleaseQuality.video_bitrate_kbps)).scalar()
    avg_size = session.query(func.avg(ReleaseQuality.total_size_mb)).scalar()
    avg_runtime = session.query(func.avg(ReleaseQuality.runtime_minutes)).scalar()
    avg_confidence = session.query(func.avg(ReleaseQuality.parse_confidence)).scalar()

    # Field coverage (what % of NFOs have each field)
    field_coverage = {}
    for field_name, col in [
        ("Video Bitrate", ReleaseQuality.video_bitrate_kbps),
        ("Video Codec", ReleaseQuality.video_codec_detail),
        ("Audio Format", ReleaseQuality.audio_format_detail),
        ("Audio Bitrate", ReleaseQuality.audio_bitrate_kbps),
        ("File Size", ReleaseQuality.total_size_mb),
        ("Runtime", ReleaseQuality.runtime_minutes),
        ("CRF Value", ReleaseQuality.crf_value),
        ("Encoder Preset", ReleaseQuality.encoder_preset),
        ("Bit Depth", ReleaseQuality.bit_depth),
        ("Encode Ratio", ReleaseQuality.encode_ratio),
        ("IMDb ID", ReleaseQuality.imdb_id),
    ]:
        count = session.query(func.count(ReleaseQuality.id)).filter(col.isnot(None)).scalar() or 0
        field_coverage[field_name] = {
            "count": count,
            "pct": round(count / total * 100, 1) if total > 0 else 0,
        }

    return {
        "total": total,
        "sources": [(src or "unknown", count) for src, count in source_rows],
        "codecs": [(codec, count) for codec, count in codec_rows],
        "audio_formats": [(fmt, count) for fmt, count in audio_rows],
        "bitrate_buckets": bitrate_buckets,
        "confidence_buckets": confidence_buckets,
        "nfo_status": [(status, count) for status, count in status_rows],
        "avg_bitrate": int(avg_bitrate) if avg_bitrate else 0,
        "avg_size_mb": int(avg_size) if avg_size else 0,
        "avg_runtime": int(avg_runtime) if avg_runtime else 0,
        "avg_confidence": float(avg_confidence) if avg_confidence else 0,
        "field_coverage": field_coverage,
    }


def _get_recent_quality(session, limit: int = 50) -> list:
    """Recent releases with quality data."""
    rows = (
        session.query(ParsedRelease, Release, ReleaseQuality)
        .join(Release, ParsedRelease.release_id == Release.id)
        .join(ReleaseQuality, ReleaseQuality.release_id == Release.id)
        .order_by(desc(ReleaseQuality.fetched_at))
        .limit(limit)
        .all()
    )
    return rows
