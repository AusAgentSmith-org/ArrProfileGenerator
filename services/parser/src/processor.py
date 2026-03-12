"""Process raw releases: parse with guessit, filter, store to DB."""

from datetime import datetime, timezone

from guessit import guessit

from profsync.db import get_session
from profsync.logging import setup_logging
from profsync.models import Nuke, ParsedRelease, Release
from profsync.queue import QUEUE_NFO_NEEDED, enqueue, get_redis

from src.filters import is_english_content

logger = setup_logging("parser.processor")
redis = get_redis()

# Map guessit source values to our normalized form
SOURCE_MAP = {
    "Blu-ray": "Blu-ray",
    "Ultra HD Blu-ray": "UHD Blu-ray",
    "Web": "WEB-DL",
    "HDTV": "HDTV",
    "DVD": "DVD",
    "Analog HDTV": "HDTV",
    "Digital TV": "HDTV",
    "Satellite": "HDTV",
}


def process_release(message: dict) -> None:
    release_data = message.get("release", {})
    name = release_data.get("name", "")
    if not name:
        return

    # Parse release name with guessit
    guess = guessit(name, {"type": None})

    media_type = _get_media_type(guess)
    if media_type is None:
        return  # Not a movie or series

    # Filter to English content only
    if not is_english_content(guess, name):
        return

    with get_session() as session:
        # Upsert release
        predb_id = release_data.get("predb_id")
        if predb_id:
            existing = (
                session.query(Release).filter_by(predb_id=predb_id).first()
            )
            if existing:
                _handle_nuke(session, existing.id, message)
                session.commit()
                return

        release = Release(
            predb_id=predb_id,
            name=name,
            team=release_data.get("team", ""),
            category=release_data.get("category", ""),
            genre=release_data.get("genre", ""),
            url=release_data.get("url", ""),
            size_kb=release_data.get("size_kb"),
            files=release_data.get("files"),
            pre_at=_parse_datetime(release_data.get("pre_at")),
        )
        session.add(release)
        session.flush()

        # Store parsed metadata
        parsed = ParsedRelease(
            release_id=release.id,
            title=str(guess.get("title", "")),
            year=guess.get("year"),
            media_type=media_type,
            season=guess.get("season"),
            episode=_get_episode(guess),
            resolution=_normalize_resolution(guess.get("screen_size", "")),
            source=SOURCE_MAP.get(str(guess.get("source", "")), str(guess.get("source", ""))),
            video_codec=str(guess.get("video_codec", "")),
            video_profile=_get_video_profile(guess, name),
            audio_codec=str(guess.get("audio_codec", "")),
            audio_channels=str(guess.get("audio_channels", "")),
            audio_atmos="atmos" in name.lower(),
            group=str(guess.get("release_group", release_data.get("team", ""))),
            is_proper=guess.get("proper_count", 0) > 0,
            is_repack="Repack" in str(guess.get("other", [])),
            is_remux="Remux" in str(guess.get("other", [])),
            edition=_get_edition(guess),
            language="English",
        )
        session.add(parsed)

        # Handle nuke if present
        _handle_nuke(session, release.id, message)

        session.commit()

        # Enqueue for NFO fetching
        enqueue(
            redis,
            QUEUE_NFO_NEEDED,
            {
                "release_id": release.id,
                "release_name": name,
                "group": parsed.group,
                "media_type": media_type,
            },
        )


def _get_media_type(guess: dict) -> str | None:
    gtype = str(guess.get("type", "")).lower()
    if gtype == "movie":
        return "movie"
    if gtype == "episode":
        return "series"
    return None


def _get_episode(guess: dict) -> int | None:
    ep = guess.get("episode")
    if isinstance(ep, list):
        return ep[0] if ep else None
    return ep


def _normalize_resolution(screen_size: str) -> str:
    s = str(screen_size).lower()
    if "2160" in s or "4k" in s:
        return "2160p"
    if "1080" in s:
        return "1080p"
    if "720" in s:
        return "720p"
    if "480" in s:
        return "480p"
    return screen_size or ""


def _get_video_profile(guess: dict, name: str) -> str:
    other = [str(o) for o in (guess.get("other") or [])]
    name_lower = name.lower()
    if "dolby vision" in name_lower or "dv" in name_lower or "DoVi" in name:
        if "hdr" in name_lower or "hdr10" in name_lower:
            return "DV HDR"
        return "DV"
    if "hdr10+" in name_lower or "hdr10plus" in name_lower:
        return "HDR10+"
    if "hdr10" in name_lower or "hdr" in name_lower or "HDR" in other:
        return "HDR"
    return "SDR"


def _get_edition(guess: dict) -> str | None:
    edition = guess.get("edition")
    if edition:
        if isinstance(edition, list):
            return ", ".join(str(e) for e in edition)
        return str(edition)
    return None


def _handle_nuke(session, release_id: int, message: dict) -> None:
    nuke_data = message.get("nuke")
    if not nuke_data:
        return

    existing_nuke = session.query(Nuke).filter_by(release_id=release_id).first()
    if existing_nuke:
        existing_nuke.type = nuke_data.get("type", "nuke")
        existing_nuke.reason = nuke_data.get("reason", "")
        existing_nuke.nuked_at = _parse_datetime(nuke_data.get("nuked_at"))
    else:
        nuke = Nuke(
            release_id=release_id,
            predb_nuke_id=nuke_data.get("nuke_id"),
            type=nuke_data.get("type", "nuke"),
            reason=nuke_data.get("reason", ""),
            network=nuke_data.get("network", ""),
            nuked_at=_parse_datetime(nuke_data.get("nuked_at")),
        )
        session.add(nuke)


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            except (ValueError, OSError):
                return None
    return None
