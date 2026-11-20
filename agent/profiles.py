"""Saved profiles, one JSON file per person, plus the per-sender "waiting for onboarding answer" marker."""
import re
from pathlib import Path

from contracts.models import GuestProfile

_SAFE = re.compile(r"[A-Za-z0-9+@_-][A-Za-z0-9+@._-]{0,63}")  # phone numbers and handles; no slash, no leading dot


class ProfileStore:
    def __init__(self, data_dir: str = ".data"):
        self.dir = Path(data_dir) / "profiles"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, person_id: str, ext: str = ".json") -> Path:
        if not _SAFE.fullmatch(person_id or ""):  # ids arrive over HTTP; never let them form a path
            raise ValueError(f"unsafe profile id: {person_id!r}")
        return self.dir / f"{person_id}{ext}"

    def get(self, person_id: str) -> GuestProfile | None:
        if not _SAFE.fullmatch(person_id or ""):
            return None  # an unsafe id can never have been saved
        p = self._path(person_id)
        return GuestProfile.model_validate_json(p.read_text()) if p.exists() else None

    def save(self, profile: GuestProfile) -> GuestProfile:
        p = self._path(profile.id)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(profile.model_dump_json())
        tmp.replace(p)
        return profile

    def pending(self, person_id: str) -> bool:
        return self._path(person_id, ".pending").exists()

    def set_pending(self, person_id: str, on: bool) -> None:
        p = self._path(person_id, ".pending")
        p.touch() if on else p.unlink(missing_ok=True)
