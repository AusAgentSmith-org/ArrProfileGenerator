"""Parse quality metrics from NFO text using regex patterns."""

import re
from datetime import datetime, timezone

from profsync.logging import setup_logging

logger = setup_logging("nfo-fetcher.nfo_parser")


def parse_nfo(nfo_text: str) -> dict:
    """Extract structured quality data from an NFO file's text content.

    Returns a dict of quality metrics with a parse_confidence score
    indicating what fraction of target fields were extracted.
    """
    result = {}
    fields_found = 0
    total_fields = 13  # number of fields we try to extract

    # --- Video bitrate ---
    video_br = _extract_video_bitrate(nfo_text)
    if video_br is not None:
        result["video_bitrate_kbps"] = video_br
        fields_found += 1

    # --- Source bitrate ---
    source_br = _extract_source_bitrate(nfo_text)
    if source_br is not None:
        result["source_bitrate_kbps"] = source_br
        fields_found += 1

    # Compute encode ratio
    if video_br and source_br and source_br > 0:
        result["encode_ratio"] = round(video_br / source_br, 3)

    # --- CRF value ---
    crf = _extract_crf(nfo_text)
    if crf is not None:
        result["crf_value"] = crf
        fields_found += 1

    # --- Video codec detail ---
    codec = _extract_video_codec(nfo_text)
    if codec:
        result["video_codec_detail"] = codec
        fields_found += 1

    # --- Encoder preset ---
    preset = _extract_preset(nfo_text)
    if preset:
        result["encoder_preset"] = preset
        fields_found += 1

    # --- Bit depth ---
    depth = _extract_bit_depth(nfo_text)
    if depth:
        result["bit_depth"] = depth
        fields_found += 1

    # --- Audio format ---
    audio_fmt = _extract_audio_format(nfo_text)
    if audio_fmt:
        result["audio_format_detail"] = audio_fmt
        fields_found += 1

    # --- Audio bitrate ---
    audio_br = _extract_audio_bitrate(nfo_text)
    if audio_br is not None:
        result["audio_bitrate_kbps"] = audio_br
        fields_found += 1

    # --- Audio channels ---
    channels = _extract_audio_channels(nfo_text)
    if channels:
        result["audio_channels_detail"] = channels
        fields_found += 1

    # --- File size ---
    size_mb = _extract_file_size(nfo_text)
    if size_mb is not None:
        result["total_size_mb"] = size_mb
        fields_found += 1

    # --- Runtime ---
    runtime = _extract_runtime(nfo_text)
    if runtime is not None:
        result["runtime_minutes"] = runtime
        fields_found += 1

        # Compute bitrate per minute
        if video_br:
            result["bitrate_per_minute"] = round(video_br / runtime, 1)

    # --- IMDb ID ---
    imdb = _extract_imdb(nfo_text)
    if imdb:
        result["imdb_id"] = imdb
        fields_found += 1

    # --- TVDB ID ---
    tvdb = _extract_tvdb(nfo_text)
    if tvdb:
        result["tvdb_id"] = tvdb

    # --- Video profile (HDR/SDR) ---
    video_profile = _extract_video_profile(nfo_text)
    if video_profile:
        result["video_profile_detail"] = video_profile
        fields_found += 1

    result["parse_confidence"] = round(fields_found / total_fields, 2)
    result["fetched_at"] = datetime.now(timezone.utc)

    return result


# --- Extraction functions ---

def _extract_video_bitrate(text: str) -> int | None:
    """Extract video bitrate in kbps."""
    # Patterns explicitly tagged as video — no audio guard needed
    specific_patterns = [
        r"video\s*(?:bit\s*rate|bitrate)\s*[:\.]\s*([\d\s,\.]+)\s*(kbps|kb/s|kbit/s|mbps|mb/s|mbit/s)",
    ]
    result = _match_bitrate(text, specific_patterns)
    if result is not None:
        return result

    # Generic bitrate patterns — skip lines that mention "audio"
    generic_patterns = [
        r"bitrate\s*[:\.]\s*([\d\s,\.]+)\s*(kbps|kb/s|kbit/s|mbps|mb/s|mbit/s)",
        r"bit\s*rate\s*[:\.]\s*([\d\s,\.]+)\s*(kbps|kb/s|kbit/s|mbps|mb/s|mbit/s)",
    ]
    return _match_bitrate(text, generic_patterns, skip_audio_lines=True)


def _extract_source_bitrate(text: str) -> int | None:
    """Extract source video bitrate in kbps."""
    patterns = [
        r"source\s*(?:video\s*)?(?:bit\s*rate|bitrate)\s*[:\.]\s*([\d\s,\.]+)\s*(kbps|kb/s|kbit/s|mbps|mb/s|mbit/s)",
        r"src\.?\s*(?:bit\s*rate|bitrate)\s*[:\.]\s*([\d\s,\.]+)\s*(kbps|kb/s|kbit/s|mbps|mb/s|mbit/s)",
    ]
    return _match_bitrate(text, patterns)


def _match_bitrate(text: str, patterns: list[str], skip_audio_lines: bool = False) -> int | None:
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if skip_audio_lines:
                # Get the line containing this match and skip if it mentions audio
                line_start = text.rfind("\n", 0, match.start()) + 1
                line_end = text.find("\n", match.end())
                if line_end == -1:
                    line_end = len(text)
                line = text[line_start:line_end]
                if re.search(r"audio", line, re.IGNORECASE):
                    continue
            value_str = match.group(1).replace(" ", "").replace(",", "")
            unit = match.group(2).lower()
            try:
                value = float(value_str)
                if "mb" in unit or "mbit" in unit:
                    value *= 1000
                return int(value)
            except ValueError:
                continue
    return None


def _extract_crf(text: str) -> float | None:
    patterns = [
        r"CRF\s*[:=\.]\s*(\d+\.?\d*)",
        r"--crf\s+(\d+\.?\d*)",
        r"crf=(\d+\.?\d*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                val = float(match.group(1))
                if 0 <= val <= 51:  # valid CRF range
                    return val
            except ValueError:
                continue
    return None


def _extract_video_codec(text: str) -> str | None:
    patterns = [
        # "Video : AVC (High@L4)" — predb.net ETHEL-style
        r"video\s*[:\.]\s*(AVC|HEVC|x264|x265|h\.?264|h\.?265)\s*(?:\([^)]*\))?",
        # Standalone codec mentions
        r"(x265|x264|h\.?265|h\.?264|HEVC|AVC)\s*(?:10[- ]?bit|8[- ]?bit)?",
        r"video\s*codec\s*[:\.]\s*(\S+(?:\s+\S+)?)",
        r"codec\s*(?:id)?\s*[:\.]\s*(?:V_)?(HEVC|AVC|MPEG[24H])",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            codec = match.group(1).strip()
            # Check for bit depth nearby
            depth_match = re.search(r"(10|8)[- ]?bit", text[max(0, match.start()-50):match.end()+50], re.IGNORECASE)
            if depth_match:
                codec += f" {depth_match.group(1)}-bit"
            return codec
    return None


def _extract_preset(text: str) -> str | None:
    patterns = [
        r"preset\s*[:\.=]\s*(ultrafast|superfast|veryfast|faster|fast|medium|slow|slower|veryslow|placebo)",
        r"--(ultrafast|superfast|veryfast|faster|fast|medium|slow|slower|veryslow|placebo)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).lower()
    return None


def _extract_bit_depth(text: str) -> int | None:
    patterns = [
        r"bit\s*depth\s*[:\.]\s*(\d+)\s*(?:bit)?",
        r"(\d+)[- ]?bit\s+(?:color|depth|profile)",
        r"(10|8)[- ]?bit",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                val = int(match.group(1))
                if val in (8, 10, 12):
                    return val
            except ValueError:
                continue
    return None


def _extract_audio_format(text: str) -> str | None:
    """Extract audio format with detail (e.g., 'TrueHD Atmos 7.1')."""
    # Order matters — match most specific first
    audio_formats = [
        (r"DTS[:\s-]*X", "DTS:X"),
        (r"TrueHD\s*(?:/\s*)?Atmos", "TrueHD Atmos"),
        (r"TrueHD", "TrueHD"),
        (r"DTS[:\s-]*HD\s*(?:MA|Master\s*Audio)", "DTS-HD MA"),
        (r"DTS[:\s-]*HD\s*(?:HRA?|High\s*Res)", "DTS-HD HRA"),
        (r"DTS", "DTS"),
        (r"E[- ]?AC[- ]?3\s*(?:Atmos|JOC)", "E-AC3 Atmos"),
        (r"(?:Dolby\s*Digital\s*Plus|DD\+|EAC3|E[- ]?AC[- ]?3)", "E-AC3"),
        (r"(?:Dolby\s*Digital|DD|AC[- ]?3)", "AC3"),
        (r"FLAC", "FLAC"),
        (r"PCM|LPCM", "LPCM"),
        (r"AAC(?:[- ]?LC)?", "AAC"),
        (r"Opus", "Opus"),
        (r"MP3", "MP3"),
    ]

    for pattern, name in audio_formats:
        if re.search(pattern, text, re.IGNORECASE):
            # Try to get channels alongside
            channels = _extract_audio_channels(text)
            if channels:
                return f"{name} {channels}"
            return name

    return None


def _extract_audio_bitrate(text: str) -> int | None:
    patterns = [
        # "Audio : English E-AC-3 384 kb/s @ 6 channels" — predb.net style
        r"audio\s*[:\.]\s*.*?(\d[\d\s,\.]*)\s*(kbps|kb/s|kbit/s|mbps|mb/s)",
        # "Audio Bitrate : 1234 kbps"
        r"audio\s*(?:bit\s*rate|bitrate)\s*[:\.]\s*([\d\s,\.]+)\s*(kbps|kb/s|kbit/s|mbps|mb/s)",
    ]
    return _match_bitrate(text, patterns)


def _extract_audio_channels(text: str) -> str | None:
    patterns = [
        # "@ 6 channels" — predb.net ETHEL-style
        r"@\s*(\d+)\s*channel",
        # "Channels : 5.1" or "channel layout : 7.1"
        r"channel(?:s|_?layout)?\s*[:\.]\s*(\d+\.?\d*)",
        r"(\d+\.\d+)\s*ch(?:annel)?",
        r"(7\.1|5\.1|2\.1|2\.0|1\.0)\s",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = match.group(1)
            # Convert "6" to "5.1" etc.
            if val.isdigit():
                ch = int(val)
                channel_map = {8: "7.1", 6: "5.1", 3: "2.1", 2: "2.0", 1: "1.0"}
                return channel_map.get(ch, f"{ch}.0")
            return val
    return None


def _extract_file_size(text: str) -> int | None:
    patterns = [
        r"(?:file\s*)?size\s*[:\.]\s*([\d,\.]+)\s*(GiB|GB|MiB|MB|gib|gb|mib|mb)",
        r"([\d,\.]+)\s*(GiB|GB|MiB|MB)\s*(?:\(|total)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                value = float(match.group(1).replace(",", ""))
                unit = match.group(2).lower()
                if unit in ("gib", "gb"):
                    return int(value * 1024)
                return int(value)
            except ValueError:
                continue
    return None


def _extract_runtime(text: str) -> int | None:
    patterns = [
        # "Duration : 41 min 55 s" — predb.net style
        r"(?:duration|runtime|run\s*time|length)\s*[:\.]\s*(\d+)\s*min\s+(\d+)\s*s",
        # "Duration: 2h 15min" or "Runtime: 2h15m"
        r"(?:duration|runtime|run\s*time|length)\s*[:\.]\s*(\d+)\s*h\s*(\d+)\s*m",
        # "Duration: 135 min"
        r"(?:duration|runtime|run\s*time|length)\s*[:\.]\s*(\d+)\s*min",
        # "Duration: 01:35:22"
        r"(?:duration|runtime)\s*[:\.]\s*(\d+):(\d+):(\d+)",
    ]
    for i, pattern in enumerate(patterns):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                if i == 0:  # Xmin Ys
                    return int(match.group(1))
                elif i == 1:  # Xh Ym
                    return int(match.group(1)) * 60 + int(match.group(2))
                elif i == 2:  # N min
                    return int(match.group(1))
                elif i == 3:  # HH:MM:SS
                    return int(match.group(1)) * 60 + int(match.group(2))
            except ValueError:
                continue
    return None


def _extract_imdb(text: str) -> str | None:
    match = re.search(r"imdb\.com/title/(tt\d{7,})", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"(tt\d{7,})", text)
    if match:
        return match.group(1)
    return None


def _extract_tvdb(text: str) -> str | None:
    # "URL : https://www.tvmaze.com/shows/59/chicago-fire" — predb.net style
    match = re.search(r"tvmaze\.com/shows/(\d+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"(?:thetvdb|tvdb)\.com\S*?(\d{4,})", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _extract_video_profile(text: str) -> str | None:
    """Extract HDR format from NFO text."""
    # Order matters — match most specific first
    profiles = [
        (r"HDR10\+", "HDR10+"),
        (r"Dolby\s*Vision", "DV"),
        (r"\bDV\b", "DV"),
        (r"\bHDR10\b", "HDR10"),
        (r"\bHDR\b", "HDR10"),
        (r"\bSDR\b", "SDR"),
    ]
    for pattern, name in profiles:
        if re.search(pattern, text, re.IGNORECASE):
            return name
    return None
