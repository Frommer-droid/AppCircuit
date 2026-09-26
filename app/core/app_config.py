from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "AppCircuit"
APP_USER_MODEL_ID = "frommer.appcircuit.desktop.1"


def application_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


ROOT_DIR = application_directory()
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", ROOT_DIR))
SETTINGS_FILE = ROOT_DIR / "settings.json"
LOG_FILE = ROOT_DIR / "application.log"
VERSION_FILE = ROOT_DIR / "VERSION"
LEGACY_SETTINGS_FILES = tuple(
    ROOT_DIR.parent / legacy_name / "settings.json"
    for legacy_name in ("Job App Off On", "job-app-off-on")
    if ROOT_DIR.parent / legacy_name != ROOT_DIR
)


def resource_path(*parts: str) -> Path:
    external_path = ROOT_DIR.joinpath(*parts)
    if external_path.exists():
        return external_path
    return BUNDLE_DIR.joinpath(*parts)


ICON_FILE = resource_path("logo.ico")
ICONS_DIR = resource_path("assets", "icons")


def read_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"


APP_VERSION = read_version()
