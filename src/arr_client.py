"""Sonarr/Radarr API v3 client."""

import time

import requests


class ArrClientError(Exception):
    pass


class ArrClient:
    """Thin wrapper around the Sonarr/Radarr v3 REST API."""

    def __init__(self, base_url: str, api_key: str, app_name: str = "App"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.app_name = app_name
        self.session = requests.Session()
        self.session.headers["X-Api-Key"] = api_key
        self._version: str | None = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v3{path}"

    def _get(self, path: str) -> dict | list:
        resp = self.session.get(self._url(path), timeout=30)
        if resp.status_code != 200:
            raise ArrClientError(
                f"{self.app_name} GET {path} failed: {resp.status_code} {resp.text[:200]}"
            )
        return resp.json()

    def _post(self, path: str, data: dict) -> dict:
        resp = self.session.post(self._url(path), json=data, timeout=30)
        if resp.status_code not in (200, 201):
            raise ArrClientError(
                f"{self.app_name} POST {path} failed: {resp.status_code} {resp.text[:300]}"
            )
        return resp.json()

    def _put(self, path: str, data: dict) -> dict:
        resp = self.session.put(self._url(path), json=data, timeout=30)
        if resp.status_code not in (200, 202):
            raise ArrClientError(
                f"{self.app_name} PUT {path} failed: {resp.status_code} {resp.text[:300]}"
            )
        return resp.json()

    # --- Public API ---

    def verify_connection(self) -> dict:
        """GET /api/v3/system/status — returns status dict, caches version."""
        status = self._get("/system/status")
        self._version = status.get("version", "unknown")
        return status

    @property
    def version(self) -> str:
        return self._version or "unknown"

    @property
    def is_sonarr_v3(self) -> bool:
        """True if this is Sonarr running a pre-v4 version (no CF support)."""
        return (
            self.app_name.lower() == "sonarr"
            and self._version is not None
            and self._version.startswith("3.")
        )

    def trigger_backup(self) -> None:
        """POST /api/v3/command {name: Backup}, poll until complete."""
        result = self._post("/command", {"name": "Backup"})
        cmd_id = result.get("id")
        if not cmd_id:
            return
        for _ in range(60):
            time.sleep(2)
            status = self._get(f"/command/{cmd_id}")
            if status.get("status") == "completed":
                return
            if status.get("status") in ("failed", "aborted"):
                raise ArrClientError(
                    f"{self.app_name} backup failed: {status.get('message', '')}"
                )
        raise ArrClientError(f"{self.app_name} backup timed out")

    def get_quality_definition(self) -> list:
        """GET /api/v3/qualitydefinition"""
        return self._get("/qualitydefinition")

    def get_quality_profile_schema(self) -> dict:
        """GET /api/v3/qualityprofile/schema — empty template for building profiles."""
        return self._get("/qualityprofile/schema")

    def get_custom_formats(self) -> list:
        """GET /api/v3/customformat"""
        return self._get("/customformat")

    def upsert_custom_format(self, cf: dict) -> int:
        """Create or update a custom format by name. Returns the CF id."""
        existing = self.get_custom_formats()
        match = next((e for e in existing if e["name"] == cf["name"]), None)
        if match:
            cf["id"] = match["id"]
            result = self._put(f"/customformat/{match['id']}", cf)
        else:
            result = self._post("/customformat", cf)
        return result["id"]

    def bulk_upsert_custom_formats(self, cfs: list[dict]) -> dict[str, int]:
        """Create or update multiple custom formats. Fetches existing list once.

        Returns a dict mapping CF name → CF id.
        """
        existing = self.get_custom_formats()
        existing_by_name = {e["name"]: e for e in existing}
        result_map: dict[str, int] = {}

        for cf in cfs:
            match = existing_by_name.get(cf["name"])
            if match:
                cf["id"] = match["id"]
                result = self._put(f"/customformat/{match['id']}", cf)
            else:
                result = self._post("/customformat", cf)
            result_map[cf["name"]] = result["id"]
            # Update cache so duplicate names in the batch are handled
            existing_by_name[cf["name"]] = result

        return result_map

    def get_quality_profiles(self) -> list:
        """GET /api/v3/qualityprofile"""
        return self._get("/qualityprofile")

    def create_quality_profile(self, profile: dict) -> int:
        """POST /api/v3/qualityprofile — returns profile id."""
        result = self._post("/qualityprofile", profile)
        return result["id"]

    def update_quality_profile(self, profile: dict) -> int:
        """PUT /api/v3/qualityprofile/{id} — returns profile id."""
        result = self._put(f"/qualityprofile/{profile['id']}", profile)
        return result["id"]

    def get_series(self) -> list:
        """GET /api/v3/series — returns list of series."""
        return self._get("/series")

    def get_movies(self) -> list:
        """GET /api/v3/movie — returns list of movies."""
        return self._get("/movie")

    def bulk_update_series(self, series_ids: list[int], quality_profile_id: int) -> None:
        """PUT /api/v3/series/editor — bulk update series with new quality profile."""
        self._put("/series/editor", {
            "seriesIds": series_ids,
            "qualityProfileId": quality_profile_id,
        })

    def bulk_update_movies(self, movie_ids: list[int], quality_profile_id: int) -> None:
        """PUT /api/v3/movie/editor — bulk update movies with new quality profile."""
        self._put("/movie/editor", {
            "movieIds": movie_ids,
            "qualityProfileId": quality_profile_id,
        })

    def get_root_folders(self) -> list:
        """GET /api/v3/rootfolder — returns list of root folders."""
        return self._get("/rootfolder")

    def update_root_folder(self, folder: dict) -> dict:
        """PUT /api/v3/rootfolder/{id} — update root folder default quality profile."""
        return self._put(f"/rootfolder/{folder['id']}", folder)

    def create_root_folder(self, path: str) -> dict:
        """POST /api/v3/rootfolder — create a new root folder."""
        return self._post("/rootfolder", {"path": path})
