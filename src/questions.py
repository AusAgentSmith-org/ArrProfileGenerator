"""Interactive prompts for the ProfSync configuration wizard."""

from dataclasses import dataclass, field
from pathlib import Path
import os

import questionary


@dataclass
class AppConfig:
    """Connection details for a Sonarr or Radarr instance."""

    url: str = ""
    api_key: str = ""


@dataclass
class UserProfile:
    """All user choices from the wizard interview."""

    sonarr: AppConfig | None = None
    radarr: AppConfig | None = None

    resolution: str = "hd"  # "hd", "uhd", "both"
    consumption: str = "home"  # "home", "remote"
    can_transcode: bool = True
    device_capability: str = "modern"  # "modern", "mixed", "legacy"
    hdr_support: str = "none"  # "full", "hdr10", "none"
    audio_preference: str = "standard"  # "lossless", "standard"
    include_remux: bool = False
    storage_constraint: str = "none"  # "none", "moderate", "tight"
    strictness: str = "balanced"  # "strict", "balanced", "permissive"
    auto_upgrade: bool = True

    # Derived
    wants_hevc: bool = field(init=False, default=True)
    wants_hdr: bool = field(init=False, default=False)

    def __post_init__(self):
        self._derive_flags()

    def _derive_flags(self):
        self.wants_hevc = self.device_capability in ("modern", "mixed")
        self.wants_hdr = self.hdr_support in ("full", "hdr10")


def load_teststack_credentials() -> tuple[AppConfig | None, AppConfig | None]:
    """Load Sonarr/Radarr credentials from test/.env if it exists.

    Returns (sonarr_config, radarr_config) or (None, None) if not found.
    """
    teststack_env = Path(__file__).parent.parent / "test" / ".env"

    if not teststack_env.exists():
        return None, None

    # Parse .env file
    env_vars = {}
    with open(teststack_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()

    sonarr_config = None
    radarr_config = None

    if "SONARR_URL" in env_vars and "SONARR_API_KEY" in env_vars:
        sonarr_config = AppConfig(
            url=env_vars["SONARR_URL"],
            api_key=env_vars["SONARR_API_KEY"],
        )

    if "RADARR_URL" in env_vars and "RADARR_API_KEY" in env_vars:
        radarr_config = AppConfig(
            url=env_vars["RADARR_URL"],
            api_key=env_vars["RADARR_API_KEY"],
        )

    return sonarr_config, radarr_config


def run_wizard(teststack: bool = False) -> UserProfile:
    """Run the interactive wizard and return a UserProfile.

    Args:
        teststack: If True, auto-load credentials from test/.env
    """
    profile = UserProfile()

    if teststack:
        # Load from teststack .env
        sonarr_config, radarr_config = load_teststack_credentials()

        if sonarr_config:
            profile.sonarr = sonarr_config
            print(f"✓ Loaded Sonarr from teststack ({sonarr_config.url})")
        if radarr_config:
            profile.radarr = radarr_config
            print(f"✓ Loaded Radarr from teststack ({radarr_config.url})")

        if not profile.sonarr and not profile.radarr:
            print("\nERROR: Could not load teststack credentials from test/.env")
            print("Run: cd test && ./init-stack.sh")
            raise SystemExit(1)
        print()
    else:
        # 1. Sonarr
        if questionary.confirm("Configure Sonarr?", default=False).ask():
            url = questionary.text(
                "Sonarr URL (e.g. http://192.168.1.10:8989):"
            ).ask()
            api_key = questionary.text("Sonarr API key:").ask()
            profile.sonarr = AppConfig(url=url.rstrip("/"), api_key=api_key)

        # 2. Radarr
        if questionary.confirm("Configure Radarr?", default=False).ask():
            url = questionary.text(
                "Radarr URL (e.g. http://192.168.1.10:7878):"
            ).ask()
            api_key = questionary.text("Radarr API key:").ask()
            profile.radarr = AppConfig(url=url.rstrip("/"), api_key=api_key)

        if not profile.sonarr and not profile.radarr:
            print("\nNo apps selected. Nothing to configure.")
            raise SystemExit(0)

    # 3. Resolution
    res = questionary.select(
        "Target resolution?",
        choices=[
            questionary.Choice("1080p HD only", value="hd"),
            questionary.Choice("4K UHD only", value="uhd"),
            questionary.Choice("Both (4K preferred, 1080p fallback)", value="both"),
        ],
    ).ask()
    profile.resolution = res

    # 4. Consumption
    consumption = questionary.select(
        "Where is your media consumed?",
        choices=[
            questionary.Choice("Home only (same network as server)", value="home"),
            questionary.Choice(
                "Remote streaming via Plex/Emby/Jellyfin", value="remote"
            ),
        ],
    ).ask()
    profile.consumption = consumption

    # 5. Transcoding (if remote)
    if consumption == "remote":
        profile.can_transcode = questionary.select(
            "Can your server transcode?",
            choices=[
                questionary.Choice(
                    "Yes (hardware/software transcoding)", value=True
                ),
                questionary.Choice("No (must direct play)", value=False),
            ],
        ).ask()

    # 6. Device capability
    profile.device_capability = questionary.select(
        "What devices play your media?",
        choices=[
            questionary.Choice(
                "Modern devices (Apple TV 4K, Shield, Fire 4K) — support HEVC/x265",
                value="modern",
            ),
            questionary.Choice(
                "Mixed — some older devices may not support x265", value="mixed"
            ),
            questionary.Choice(
                "Older/compatibility devices — x264/H.264 only", value="legacy"
            ),
        ],
    ).ask()

    # 7. HDR (if 4K)
    if profile.resolution in ("uhd", "both"):
        profile.hdr_support = questionary.select(
            "Does your display support HDR?",
            choices=[
                questionary.Choice("Full HDR (HDR10 + Dolby Vision)", value="full"),
                questionary.Choice("HDR10 only", value="hdr10"),
                questionary.Choice("No HDR support", value="none"),
            ],
        ).ask()

    # 8. Audio
    profile.audio_preference = questionary.select(
        "Audio quality preference?",
        choices=[
            questionary.Choice(
                "Lossless (TrueHD Atmos, DTS-HD MA) — requires AV receiver or capable soundbar",
                value="lossless",
            ),
            questionary.Choice(
                "Standard is fine (AAC, Dolby Digital)", value="standard"
            ),
        ],
    ).ask()

    # 9. Remux
    profile.include_remux = questionary.select(
        "Include remux releases? (lossless video, 30-80 GB per movie)",
        choices=[
            questionary.Choice(
                "Yes — I have storage and want the absolute best", value=True
            ),
            questionary.Choice(
                "No — encoded releases (x265/x264) preferred", value=False
            ),
        ],
    ).ask()

    # 10. Storage
    profile.storage_constraint = questionary.select(
        "Storage/bandwidth constraints?",
        choices=[
            questionary.Choice(
                "None — large storage, fast connection", value="none"
            ),
            questionary.Choice(
                "Moderate — prefer balance of quality vs size", value="moderate"
            ),
            questionary.Choice("Tight — minimize file sizes", value="tight"),
        ],
    ).ask()

    # 11. Strictness
    profile.strictness = questionary.select(
        "Group quality strictness?",
        choices=[
            questionary.Choice(
                "Strict — only A+ and A tier groups (unknown groups also blocked)",
                value="strict",
            ),
            questionary.Choice(
                "Balanced — B tier and above (default; unknown groups are allowed)",
                value="balanced",
            ),
            questionary.Choice(
                "Permissive — accept anything except F/LQ tier groups",
                value="permissive",
            ),
        ],
        default="Balanced — B tier and above (default; unknown groups are allowed)",
    ).ask()

    # 12. Auto-upgrade
    profile.auto_upgrade = questionary.select(
        "Auto-upgrade when better quality found?",
        choices=[
            questionary.Choice(
                "Yes — upgrade to better releases automatically", value=True
            ),
            questionary.Choice("No — keep the first good match", value=False),
        ],
    ).ask()

    # Re-derive flags after all answers
    profile._derive_flags()

    return profile
