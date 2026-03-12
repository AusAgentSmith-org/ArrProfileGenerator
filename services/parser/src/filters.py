"""Filters for English-only movie/TV content, excluding anime and foreign."""

import re

from profsync.logging import setup_logging

logger = setup_logging("parser.filters")

# Patterns in release names that indicate non-English or anime content
FOREIGN_PATTERNS = re.compile(
    r"""
    (?:                         # Non-English language indicators
        \.(?:GERMAN|FRENCH|ITALIAN|SPANISH|PORTUGUESE|RUSSIAN|
             CHINESE|JAPANESE|KOREAN|DUTCH|SWEDISH|NORWEGIAN|
             DANISH|FINNISH|POLISH|CZECH|HUNGARIAN|TURKISH|
             ARABIC|HINDI|TAMIL|THAI|VIETNAMESE|INDONESIAN|
             ROMANIAN|GREEK|HEBREW|PERSIAN|UKRAINIAN|
             FLEMISH|CATALAN|SUBBED|MULTi)\.
    ) |
    (?:                         # Anime indicators
        \.(?:ANIME|ANiME)\.
    ) |
    (?:                         # Common anime group naming patterns
        \[(?:SubsPlease|Erai-raws|HorribleSubs|
             Judas|ASW|Tsundere-Raws|EMBER)\]
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# guessit language codes that are not English
NON_ENGLISH_LANGUAGES = {
    "de", "fr", "it", "es", "pt", "ru", "zh", "ja", "ko", "nl",
    "sv", "no", "da", "fi", "pl", "cs", "hu", "tr", "ar", "hi",
    "ta", "th", "vi", "id", "ro", "el", "he", "fa", "uk",
}


def is_english_content(guess: dict, release_name: str) -> bool:
    """Return True if the release appears to be English-language movie/TV content."""

    # Check guessit language detection
    language = guess.get("subtitle_language") or guess.get("language")
    if language:
        lang_list = language if isinstance(language, list) else [language]
        for lang in lang_list:
            lang_code = str(getattr(lang, "alpha2", lang)).lower()
            if lang_code in NON_ENGLISH_LANGUAGES:
                return False

    # Check release name for foreign/anime patterns
    if FOREIGN_PATTERNS.search(release_name):
        return False

    return True
