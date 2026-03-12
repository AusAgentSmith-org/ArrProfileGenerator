"""Fetch NFO from multiple sources and parse quality metrics."""

import requests

from profsync.db import get_session
from profsync.logging import setup_logging
from profsync.models import ParsedRelease, ReleaseQuality

from src.nfo_parser import parse_nfo

logger = setup_logging("nfo-fetcher.fetcher")


class RateLimitError(Exception):
    """Raised when an API returns 429."""
    pass


# Sources in priority order — srrdb is fast, free, no auth
NFO_SOURCES = [
    ("srrdb", "_fetch_from_srrdb"),
    ("predb.net", "_fetch_from_predb"),
]


def fetch_and_parse_nfo(message: dict) -> bool:
    """Fetch NFO for a release from available sources, parse it, and store quality metrics.

    Tries each source in order until one returns an NFO.
    Returns True if an NFO was found and parsed.
    """
    release_id = message.get("release_id")
    release_name = message.get("release_name", "")

    if not release_id:
        return False

    # Try each source in order
    nfo_text = None
    nfo_source = None
    for source_name, method_name in NFO_SOURCES:
        fetcher = globals().get(method_name)
        if fetcher is None:
            continue
        try:
            nfo_text = fetcher(release_name)
            if nfo_text:
                nfo_source = source_name
                break
        except RateLimitError:
            raise  # Let the caller handle rate limits
        except Exception:
            logger.debug("Source %s failed for %s", source_name, release_name)
            continue

    with get_session() as session:
        parsed = (
            session.query(ParsedRelease).filter_by(release_id=release_id).first()
        )

        if not parsed:
            return False

        if nfo_text:
            quality_data = parse_nfo(nfo_text)

            quality = ReleaseQuality(
                release_id=release_id,
                nfo_source=nfo_source,
                nfo_raw=nfo_text,
                video_bitrate_kbps=quality_data.get("video_bitrate_kbps"),
                source_bitrate_kbps=quality_data.get("source_bitrate_kbps"),
                encode_ratio=quality_data.get("encode_ratio"),
                crf_value=quality_data.get("crf_value"),
                video_codec_detail=quality_data.get("video_codec_detail"),
                encoder_preset=quality_data.get("encoder_preset"),
                bit_depth=quality_data.get("bit_depth"),
                audio_format_detail=quality_data.get("audio_format_detail"),
                audio_bitrate_kbps=quality_data.get("audio_bitrate_kbps"),
                audio_channels_detail=quality_data.get("audio_channels_detail"),
                total_size_mb=quality_data.get("total_size_mb"),
                runtime_minutes=quality_data.get("runtime_minutes"),
                bitrate_per_minute=quality_data.get("bitrate_per_minute"),
                imdb_id=quality_data.get("imdb_id"),
                tvdb_id=quality_data.get("tvdb_id"),
                fetched_at=quality_data.get("fetched_at"),
                parse_confidence=quality_data.get("parse_confidence", 0.0),
            )
            session.add(quality)
            parsed.nfo_status = "fetched"
        else:
            parsed.nfo_status = "not_found"

        session.commit()

    return nfo_text is not None


def _fetch_from_srrdb(release_name: str) -> str | None:
    """Fetch NFO from srrdb.com — free, no auth, fast.

    1. GET https://api.srrdb.com/v1/nfo/<release> → returns NFO filenames + download URLs
    2. GET the download URL → returns raw NFO text
    """
    try:
        resp = requests.get(
            f"https://api.srrdb.com/v1/nfo/{release_name}",
            timeout=15,
        )

        if resp.status_code == 429:
            raise RateLimitError("srrdb returned 429")

        if resp.status_code != 200:
            return None

        data = resp.json()
        nfo_links = data.get("nfolink", [])
        if not nfo_links:
            return None

        # Download the first NFO file
        nfo_resp = requests.get(nfo_links[0], timeout=15)
        if nfo_resp.status_code != 200:
            return None

        nfo_text = nfo_resp.text
        if not nfo_text or len(nfo_text) < 10:
            return None

        return nfo_text

    except RateLimitError:
        raise
    except requests.RequestException:
        logger.debug("srrdb request failed for %s", release_name)
        return None


def _fetch_from_predb(release_name: str) -> str | None:
    """Fetch NFO from predb.net — fallback source.

    1. GET https://api.predb.net/?type=nfo&release=<name> → returns NFO URL
    2. GET the NFO URL → returns raw NFO text
    """
    try:
        resp = requests.get(
            "https://api.predb.net/",
            params={"type": "nfo", "release": release_name},
            timeout=15,
        )

        if resp.status_code == 429:
            raise RateLimitError("predb.net returned 429")

        if resp.status_code != 200:
            return None

        data = resp.json()
        if data.get("status") != "success":
            return None

        nfo_url = data.get("data", {}).get("nfo", "")
        if not nfo_url:
            return None

        nfo_resp = requests.get(nfo_url, timeout=15)
        if nfo_resp.status_code != 200:
            return None

        nfo_text = nfo_resp.text
        if not nfo_text or len(nfo_text) < 10:
            return None

        return nfo_text

    except RateLimitError:
        raise
    except requests.RequestException:
        logger.debug("predb.net request failed for %s", release_name)
        return None
