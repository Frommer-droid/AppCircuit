from __future__ import annotations

import json
import logging
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.models import ApplicationEntry, Session

LOGGER = logging.getLogger(__name__)

DEFAULT_APPLICATIONS: list[ApplicationEntry] = []
MAX_RECENT_APPLICATION_DIRECTORIES = 5

DEFAULT_SETTINGS: dict[str, Any] = {
    "window_pos_x": None,
    "window_pos_y": None,
    "window_width": None,
    "window_height": 560,
    "window_geometry": None,
    "maximized": False,
    "applications": [item.to_dict() for item in DEFAULT_APPLICATIONS],
    "recent_application_directories": [],
    "sessions": [],
    "ui_scale_mode": "auto",
    "ui_scale_delta_percent": 0,
    "ui_scale_percent": 100,
}


class SettingsStore:
    def __init__(
        self,
        settings_file: Path,
        legacy_settings_files: tuple[Path, ...] = (),
    ) -> None:
        self.settings_file = settings_file
        self.legacy_settings_files = legacy_settings_files

    def load(self) -> dict[str, Any]:
        settings = deepcopy(DEFAULT_SETTINGS)
        source = self.settings_file
        migrated = False
        if not source.exists():
            source = next(
                (candidate for candidate in self.legacy_settings_files if candidate.is_file()),
                source,
            )
            migrated = source != self.settings_file
        if not source.exists():
            return settings
        loaded_dict: dict[str, object] | None = None
        try:
            loaded = json.loads(source.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                loaded_dict = loaded  # type: ignore[assignment]
                settings.update(loaded)
        except (OSError, json.JSONDecodeError):
            LOGGER.exception("Не удалось прочитать настройки, используются значения по умолчанию")
        if loaded_dict is not None:
            if "ui_scale_percent" in loaded_dict and "ui_scale_delta_percent" not in loaded_dict:
                from app.services.ui_scale_service import (
                    normalize_ui_scale_delta_percent,
                )

                try:
                    legacy_percent = int(loaded_dict.get("ui_scale_percent", 100))  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    legacy_percent = 100
                settings["ui_scale_delta_percent"] = normalize_ui_scale_delta_percent(
                    legacy_percent - 100
                )
        normalized = self._normalize(settings)
        if migrated:
            try:
                self.save(normalized)
            except OSError:
                LOGGER.exception("Не удалось перенести настройки прежней установки")
        session_migrated = self._migrate_legacy_applications_to_session(normalized)
        if session_migrated:
            try:
                self.save(normalized)
            except OSError:
                LOGGER.exception("Не удалось перенести приложения в сессию")
        return normalized

    def save(self, settings: dict[str, Any]) -> None:
        normalized = self._normalize(deepcopy(settings))
        temporary = self.settings_file.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.settings_file)

    @staticmethod
    def _migrate_legacy_applications_to_session(settings: dict[str, Any]) -> bool:
        sessions = settings.get("sessions")
        if isinstance(sessions, list) and sessions:
            return False
        applications = settings.get("applications")
        if not isinstance(applications, list) or not applications:
            return False
        from app.models import Session

        settings["sessions"] = [
            Session.from_dict(
                {"name": "Приложения", "applications": applications}
            ).to_dict()
        ]
        settings["applications"] = []
        return True

    @staticmethod
    def _normalize(settings: dict[str, Any]) -> dict[str, Any]:
        width = settings.get("window_width")
        if width is None:
            settings["window_width"] = None
        else:
            try:
                settings["window_width"] = max(1, int(width))
            except (TypeError, ValueError):
                settings["window_width"] = None

        try:
            settings["window_height"] = max(
                300,
                int(settings.get("window_height", DEFAULT_SETTINGS["window_height"])),
            )
        except (TypeError, ValueError):
            settings["window_height"] = DEFAULT_SETTINGS["window_height"]
        for key in ("window_pos_x", "window_pos_y"):
            try:
                value = settings.get(key)
                settings[key] = None if value is None else int(value)
            except (TypeError, ValueError):
                settings[key] = None
        geometry = settings.get("window_geometry")
        settings["window_geometry"] = geometry if isinstance(geometry, str) and geometry else None
        settings["maximized"] = bool(settings.get("maximized", False))

        applications = settings.get("applications")
        if not isinstance(applications, list):
            applications = deepcopy(DEFAULT_SETTINGS["applications"])
        normalized_applications = [
            ApplicationEntry.from_dict(item)
            for item in applications
            if isinstance(item, dict) and str(item.get("path", "")).strip()
        ]
        name_counts = Counter(
            application.name.casefold() for application in normalized_applications
        )
        for application in normalized_applications:
            if name_counts[application.name.casefold()] > 1:
                application.name = ApplicationEntry.default_name_for_path(
                    application.path
                )
        settings["applications"] = [
            application.to_dict() for application in normalized_applications
        ]

        raw_sessions = settings.get("sessions")
        if not isinstance(raw_sessions, list):
            raw_sessions = []
        normalized_sessions = [
            Session.from_dict(item)
            for item in raw_sessions
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ]
        settings["sessions"] = [session.to_dict() for session in normalized_sessions]

        from app.services.ui_scale_service import (
            normalize_ui_scale_delta_percent,
            normalize_ui_scale_mode,
            normalize_ui_scale_percent,
        )

        settings["ui_scale_mode"] = normalize_ui_scale_mode(
            settings.get("ui_scale_mode")
        )
        settings["ui_scale_delta_percent"] = normalize_ui_scale_delta_percent(
            settings.get("ui_scale_delta_percent")
        )
        settings["ui_scale_percent"] = normalize_ui_scale_percent(
            settings.get("ui_scale_percent", 100)
        )

        recent_directories = settings.get("recent_application_directories")
        if not isinstance(recent_directories, list):
            recent_directories = []
        normalized_directories: list[str] = []
        known_directories: set[str] = set()
        for value in recent_directories:
            directory = Path(str(value)).expanduser()
            if not directory.is_dir():
                continue
            normalized = str(directory.resolve())
            key = normalized.casefold()
            if key in known_directories:
                continue
            normalized_directories.append(normalized)
            known_directories.add(key)
            if len(normalized_directories) == MAX_RECENT_APPLICATION_DIRECTORIES:
                break
        settings["recent_application_directories"] = normalized_directories
        return settings
