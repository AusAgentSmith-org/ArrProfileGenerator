"""Web dashboard for ProfSync pipeline monitoring."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, desc

from profsync.db import get_session
from profsync.models import GroupProfile, Nuke, ParsedRelease, Release, ReleaseQuality
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
    return templates.TemplateResponse("groups.html", {
        "request": request,
        "profiles": profiles,
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
            session.query(ParsedRelease, Release)
            .join(Release, ParsedRelease.release_id == Release.id)
            .filter(ParsedRelease.group == group_name)
            .order_by(desc(Release.pre_at))
            .limit(50)
            .all()
        )
    return templates.TemplateResponse("group_detail.html", {
        "request": request,
        "group_name": group_name,
        "profiles": profiles,
        "recent": recent,
    })


@app.get("/releases", response_class=HTMLResponse)
def releases_page(request: Request):
    with get_session() as session:
        releases = (
            session.query(ParsedRelease, Release)
            .join(Release, ParsedRelease.release_id == Release.id)
            .order_by(desc(Release.pre_at))
            .limit(200)
            .all()
        )
    return templates.TemplateResponse("releases.html", {
        "request": request,
        "releases": releases,
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
