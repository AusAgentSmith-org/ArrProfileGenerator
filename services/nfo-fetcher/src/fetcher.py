"""Fetch NFO from xREL API and parse quality metrics."""

import requests

from profsync.config import settings
from profsync.db import get_session
from profsync.logging import setup_logging
from profsync.models import ParsedRelease, ReleaseQuality

from src.nfo_parser import parse_nfo

logger = setup_logging("nfo-fetcher.fetcher")


def fetch_and_parse_nfo(message: dict) -> bool:
    """Fetch NFO for a release, parse it, and store quality metrics.

    Returns True if an NFO was found and parsed.
    """
    release_id = message.get("release_id")
    release_name = message.get("release_name", "")

    if not release_id:
        return False

    # Try to fetch NFO from xREL
    nfo_text = _fetch_from_xrel(release_name)

    with get_session() as session:
        parsed = (
            session.query(ParsedRelease).filter_by(release_id=release_id).first()
        )

        if not parsed:
            return False

        if nfo_text:
            # Parse quality metrics from NFO text
            quality_data = parse_nfo(nfo_text)

            quality = ReleaseQuality(
                release_id=release_id,
                nfo_source="xrel",
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


def _fetch_from_xrel(release_name: str) -> str | None:
    """Search xREL for a release and fetch its NFO."""
    try:
        # Search for the release
        resp = requests.get(
            f"{settings.xrel_api_url}/search/releases.json",
            params={"q": release_name, "limit": 1},
            headers=_xrel_headers(),
            timeout=15,
        )

        if resp.status_code != 200:
            logger.debug("xREL search returned %d for %s", resp.status_code, release_name)
            return None

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None

        release_id = results[0].get("id")
        if not release_id:
            return None

        # Fetch NFO
        nfo_resp = requests.get(
            f"{settings.xrel_api_url}/nfo/release.json",
            params={"id": release_id},
            headers=_xrel_headers(),
            timeout=15,
        )

        if nfo_resp.status_code != 200:
            return None

        nfo_data = nfo_resp.json()
        return nfo_data.get("nfo", None)

    except requests.RequestException:
        logger.debug("xREL request failed for %s", release_name)
        return None


def _xrel_headers() -> dict:
    headers = {"Accept": "application/json"}
    if settings.xrel_api_key:
        headers["X-Auth-Token"] = settings.xrel_api_key
    return headers
