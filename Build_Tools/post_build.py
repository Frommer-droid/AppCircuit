"""Формирует корневую onedir-папку и runtime manifest после PyInstaller."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

APP_NAME = "AppCircuit"
MANIFEST_NAME = "RUNTIME_MANIFEST.json"
ROOT_FILES = (
    "VERSION",
    "logo.ico",
    "LICENSE",
    "EULA.md",
    "THIRD_PARTY_NOTICES.md",
    "SOURCE_CODE_ACCESS.md",
    "QT_PYSIDE6_COMPLIANCE.md",
    "LGPL-3.0.txt",
    "GPL-3.0.txt",
)
MANIFEST_PACKAGES = ("PySide6", "shiboken6", "PyInstaller")


def installed_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def remove_readonly(func, path, _exc_info) -> None:
    os.chmod(path, 0o700)
    func(path)


def copy_required_files(project_root: Path, target: Path) -> None:
    missing = [name for name in ROOT_FILES if not (project_root / name).is_file()]
    if missing:
        raise FileNotFoundError("Не найдены release-файлы: " + ", ".join(missing))
    for filename in ROOT_FILES:
        shutil.copy2(project_root / filename, target / filename)


def scan_qt_runtime(target: Path) -> dict[str, object]:
    qt_dlls: list[str] = []
    plugin_dirs: set[str] = set()
    for root, dirs, files in os.walk(target):
        root_path = Path(root)
        relative = root_path.relative_to(target)
        for filename in files:
            if filename.startswith("Qt6") and filename.lower().endswith(".dll"):
                qt_dlls.append((relative / filename).as_posix())
        for dirname in dirs:
            if dirname.lower() in {"platforms", "imageformats", "styles", "iconengines", "tls"}:
                plugin_dirs.add((relative / dirname).as_posix())
    return {
        "qt_dlls": sorted(qt_dlls),
        "qt_plugin_directories": sorted(plugin_dirs),
    }


def write_manifest(project_root: Path, target: Path) -> None:
    packages = {name: installed_version(name) for name in MANIFEST_PACKAGES}
    manifest = {
        "manifest_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "application": {
            "name": APP_NAME,
            "version": (project_root / "VERSION").read_text(encoding="utf-8").strip(),
        },
        "build_environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "packages": packages,
        },
        "qt_runtime": scan_qt_runtime(target),
        "release_documents": [name for name in ROOT_FILES if name != "logo.ico"],
    }
    (target / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def cleanup(build_tools: Path, project_root: Path) -> None:
    for folder in (
        build_tools / "build",
        build_tools / "dist",
        build_tools / "__pycache__",
        project_root / "build",
        project_root / "dist",
    ):
        if folder.exists():
            shutil.rmtree(folder, onerror=remove_readonly)


def main() -> int:
    build_tools = Path(__file__).resolve().parent
    project_root = build_tools.parent
    source = build_tools / "dist" / APP_NAME
    target = project_root / APP_NAME
    if not source.is_dir():
        print(f"[ERROR] Не найдена папка PyInstaller: {source}")
        return 1
    try:
        copy_required_files(project_root, source)
        if target.exists():
            shutil.rmtree(target, onerror=remove_readonly)
        shutil.move(str(source), str(target))
        write_manifest(project_root, target)
        cleanup(build_tools, project_root)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] Post-build не выполнен: {exc}")
        return 1
    print(f"[OK] Готовая сборка: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
