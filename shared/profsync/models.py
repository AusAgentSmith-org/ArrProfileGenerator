from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Release(Base):
    """Raw release data from predb.ovh."""

    __tablename__ = "releases"

    id = Column(Integer, primary_key=True)
    predb_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(1024), nullable=False, index=True)
    team = Column(String(255), nullable=True, index=True)
    category = Column(String(100), nullable=True, index=True)
    genre = Column(String(255), nullable=True)
    url = Column(String(1024), nullable=True)
    size_kb = Column(Integer, nullable=True)
    files = Column(Integer, nullable=True)
    pre_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    parsed = relationship("ParsedRelease", back_populates="release", uselist=False)
    nuke = relationship("Nuke", back_populates="release", uselist=False)
    quality = relationship("ReleaseQuality", back_populates="release", uselist=False)

    __table_args__ = (
        Index("ix_releases_team_pre_at", "team", "pre_at"),
    )


class Nuke(Base):
    """Nuke status for a release."""

    __tablename__ = "nukes"

    id = Column(Integer, primary_key=True)
    release_id = Column(Integer, ForeignKey("releases.id"), nullable=False, index=True)
    predb_nuke_id = Column(Integer, nullable=True)
    type = Column(String(20), nullable=False)  # nuke, unnuke, modnuke, delpre, undelpre
    reason = Column(Text, nullable=True)
    network = Column(String(100), nullable=True)
    nuked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    release = relationship("Release", back_populates="nuke")

    __table_args__ = (
        UniqueConstraint("release_id", name="uq_nukes_release_id"),
    )


class ParsedRelease(Base):
    """Parsed metadata extracted from release name via guessit."""

    __tablename__ = "parsed_releases"

    id = Column(Integer, primary_key=True)
    release_id = Column(Integer, ForeignKey("releases.id"), nullable=False, unique=True)
    title = Column(String(512), nullable=True, index=True)
    year = Column(Integer, nullable=True)
    media_type = Column(String(20), nullable=False, index=True)  # movie, series
    season = Column(Integer, nullable=True)
    episode = Column(Integer, nullable=True)

    # Video
    resolution = Column(String(20), nullable=True, index=True)  # 720p, 1080p, 2160p
    source = Column(String(50), nullable=True, index=True)  # Blu-ray, WEB-DL, WEBRip, HDTV
    video_codec = Column(String(50), nullable=True)  # x264, x265, AV1
    video_profile = Column(String(50), nullable=True)  # HDR, HDR10+, DV, SDR

    # Audio
    audio_codec = Column(String(50), nullable=True)  # TrueHD, DTS-HD MA, AC3, AAC
    audio_channels = Column(String(20), nullable=True)  # 5.1, 7.1, 2.0
    audio_atmos = Column(Boolean, default=False)

    # Release info
    group = Column(String(100), nullable=True, index=True)
    is_proper = Column(Boolean, default=False)
    is_repack = Column(Boolean, default=False)
    is_remux = Column(Boolean, default=False)
    edition = Column(String(255), nullable=True)  # Director's Cut, Extended, etc.
    language = Column(String(50), nullable=True)

    # Processing
    nfo_status = Column(
        String(20), default="pending", nullable=False, index=True
    )  # pending, fetched, not_found, error
    parsed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    release = relationship("Release", back_populates="parsed")

    __table_args__ = (
        Index("ix_parsed_group_resolution", "group", "resolution"),
        Index("ix_parsed_type_group", "media_type", "group"),
    )


class ReleaseQuality(Base):
    """Quality metrics extracted from NFO files."""

    __tablename__ = "release_quality"

    id = Column(Integer, primary_key=True)
    release_id = Column(Integer, ForeignKey("releases.id"), nullable=False, unique=True)

    # NFO source
    nfo_source = Column(String(50), nullable=True)  # xrel, predb.net, etc.
    nfo_raw = Column(Text, nullable=True)

    # Video quality metrics
    video_bitrate_kbps = Column(Integer, nullable=True)
    source_bitrate_kbps = Column(Integer, nullable=True)
    encode_ratio = Column(Float, nullable=True)  # video_bitrate / source_bitrate
    crf_value = Column(Float, nullable=True)
    video_codec_detail = Column(String(100), nullable=True)  # e.g., x265 10-bit
    encoder_preset = Column(String(50), nullable=True)  # slow, slower, veryslow
    bit_depth = Column(Integer, nullable=True)  # 8, 10

    # Audio quality metrics
    audio_format_detail = Column(String(100), nullable=True)  # TrueHD Atmos 7.1
    audio_bitrate_kbps = Column(Integer, nullable=True)
    audio_channels_detail = Column(String(20), nullable=True)  # 7.1, 5.1

    # File metrics
    total_size_mb = Column(Integer, nullable=True)
    runtime_minutes = Column(Integer, nullable=True)
    bitrate_per_minute = Column(Float, nullable=True)

    # Linked media
    imdb_id = Column(String(20), nullable=True, index=True)
    tvdb_id = Column(String(20), nullable=True)

    # Processing
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    parse_confidence = Column(
        Float, default=0.0
    )  # 0.0-1.0, how many fields we extracted

    release = relationship("Release", back_populates="quality")


class GroupProfile(Base):
    """Aggregated quality profile for a release group."""

    __tablename__ = "group_profiles"

    id = Column(Integer, primary_key=True)
    group_name = Column(String(100), nullable=False, index=True)
    resolution = Column(String(20), nullable=False)  # 720p, 1080p, 2160p, all
    media_type = Column(String(20), nullable=False)  # movie, series, all

    # Volume
    release_count = Column(Integer, default=0)
    first_seen = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)

    # Quality metrics (aggregated)
    avg_video_bitrate_kbps = Column(Float, nullable=True)
    avg_crf = Column(Float, nullable=True)
    crf_std_dev = Column(Float, nullable=True)
    avg_encode_ratio = Column(Float, nullable=True)
    avg_file_size_mb = Column(Float, nullable=True)

    # Audio breakdown (JSON: {"TrueHD Atmos": 0.45, "DTS-HD MA": 0.30, ...})
    audio_format_distribution = Column(JSONB, default=dict)

    # Source breakdown (JSON: {"Blu-ray": 0.80, "WEB-DL": 0.20, ...})
    source_distribution = Column(JSONB, default=dict)

    # Quality signals
    nuke_rate = Column(Float, default=0.0)
    proper_repack_rate = Column(Float, default=0.0)
    nfo_coverage = Column(Float, default=0.0)  # % of releases with parsed NFO data
    quality_consistency = Column(Float, default=0.0)  # inverse of quality variance

    # Computed tier (A+, A, B+, B, C+, C, D, F)
    computed_tier = Column(String(5), nullable=True, index=True)
    tier_confidence = Column(Float, default=0.0)  # 0.0-1.0
    tier_factors = Column(JSONB, default=dict)  # explanation of tier calculation

    # Quality trend (JSON array: [{"period": "2025-H2", "tier": "A+"}, ...])
    quality_trend = Column(JSONB, default=list)

    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("group_name", "resolution", "media_type", name="uq_group_profile"),
        Index("ix_group_profiles_tier", "computed_tier"),
    )
