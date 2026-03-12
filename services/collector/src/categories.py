"""Category filtering for movie/TV releases only."""

# predb.ovh category values that indicate movie or TV content.
# These are matched case-insensitively against the 'cat' field.
MOVIE_CATEGORIES = {
    "movie",
    "movies",
    "x264",
    "x265",
    "xvid",
    "bluray",
    "dvdr",
    "uhd",
    "x264-bluray",
    "x265-bluray",
}

TV_CATEGORIES = {
    "tv",
    "tv-x264",
    "tv-x265",
    "tv-xvid",
    "tv-bluray",
    "tv-dvdr",
    "tv-uhd",
    "tv-hd",
    "tv-sd",
}

ALLOWED_CATEGORIES = MOVIE_CATEGORIES | TV_CATEGORIES

# Categories to explicitly exclude
EXCLUDED_CATEGORIES = {
    "anime",
    "xxx",
    "ebook",
    "audiobook",
    "music",
    "mp3",
    "flac",
    "games",
    "apps",
    "0day",
    "pda",
    "dox",
}


def is_relevant_category(category: str | None) -> bool:
    """Check if a release category is relevant (movie/TV, not anime/foreign)."""
    if category is None:
        # Unknown category — accept for now, parser will filter further
        return True

    cat_lower = category.lower().strip()

    # Explicit exclusions first
    for excluded in EXCLUDED_CATEGORIES:
        if excluded in cat_lower:
            return False

    # If we have known categories, check against allowed list
    if ALLOWED_CATEGORIES:
        for allowed in ALLOWED_CATEGORIES:
            if allowed in cat_lower:
                return True

    # Unknown category — accept for now, parser will filter
    return True
