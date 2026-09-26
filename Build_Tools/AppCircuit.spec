# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir-сборка AppCircuit для Windows."""

import os
import sys
from pathlib import Path

import PySide6
import shiboken6
from PyInstaller.building.datastruct import Tree


APP_NAME = "AppCircuit"
PROJECT_ROOT = Path(SPECPATH).parent
ENTRYPOINT = PROJECT_ROOT / "AppCircuit.py"
PYSIDE_ROOT = Path(PySide6.__file__).resolve().parent
SHIBOKEN_ROOT = Path(shiboken6.__file__).resolve().parent


def prioritize_trusted_dll_search_paths():
    """Искать native DLL только в доверенных каталогах."""
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    preferred_paths = (
        PYSIDE_ROOT,
        SHIBOKEN_ROOT,
        Path(sys.prefix) / "Scripts",
        Path(sys.base_prefix),
        Path(sys.base_prefix) / "DLLs",
        system_root / "System32",
    )
    unique_paths = []
    seen = set()
    for path in preferred_paths:
        if not path.is_dir():
            continue
        path_text = str(path).strip()
        if not path_text:
            continue
        normalized = os.path.normcase(os.path.abspath(path_text))
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_paths.append(path_text)
    os.environ["PATH"] = os.pathsep.join(unique_paths)


prioritize_trusted_dll_search_paths()

TRUSTED_BINARY_ROOTS = tuple(
    path.resolve()
    for path in (
        PROJECT_ROOT,
        Path(sys.prefix),
        Path(sys.base_prefix),
        PYSIDE_ROOT,
        SHIBOKEN_ROOT,
        Path(os.environ.get("SystemRoot", r"C:\Windows")),
    )
)

datas = []
for filename in (
    "VERSION",
    "logo.ico",
    "LICENSE",
    "EULA.md",
    "THIRD_PARTY_NOTICES.md",
    "SOURCE_CODE_ACCESS.md",
    "QT_PYSIDE6_COMPLIANCE.md",
    "LGPL-3.0.txt",
    "GPL-3.0.txt",
):
    source = PROJECT_ROOT / filename
    if source.is_file():
        datas.append((str(source), "."))

for translations_dir, destination in (
    (PYSIDE_ROOT / "translations", "PySide6/translations"),
    (PYSIDE_ROOT / "Qt" / "translations", "PySide6/Qt/translations"),
):
    translation = translations_dir / "qtbase_ru.qm"
    if translation.is_file():
        datas.append((str(translation), destination))
        break

analysis = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ],
    hookspath=[str(Path(SPECPATH))],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PIL", "torch", "tensorflow"],
    noarchive=False,
)

# Любой посторонний источник означает ошибку анализа, а не повод незаметно
# удалить DLL из комплекта.
foreign_binaries = [
    binary
    for binary in analysis.binaries
    if not any(Path(binary[1]).resolve().is_relative_to(root) for root in TRUSTED_BINARY_ROOTS)
]
if foreign_binaries:
    details = "\n".join(f"{binary[0]} <- {binary[1]}" for binary in foreign_binaries)
    raise RuntimeError(f"Обнаружены DLL из недоверенных каталогов:\n{details}")

# Корневой _internal MSVC runtime должен целиком происходить из PySide6.
qt_msvc_runtime = {
    path.name.casefold(): path
    for path in PYSIDE_ROOT.glob("*.dll")
    if path.name.casefold().startswith(("concrt140", "msvcp140", "vcruntime140", "vcamp140", "vccorlib140", "vcomp140"))
}
required_msvc_runtime = {"concrt140.dll", "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"}
missing_msvc_runtime = required_msvc_runtime - qt_msvc_runtime.keys()
if missing_msvc_runtime:
    raise RuntimeError(f"В PySide6 отсутствует MSVC runtime: {sorted(missing_msvc_runtime)}")
analysis.binaries = [
    binary
    for binary in analysis.binaries
    if not (
        "/" not in binary[0].replace("\\", "/")
        and binary[0].casefold() in qt_msvc_runtime
    )
]
analysis.binaries += [
    (path.name, str(path), "BINARY") for path in qt_msvc_runtime.values()
]

assets_dir = PROJECT_ROOT / "assets"
runner_template = assets_dir / "runner" / "AppCircuitSession.exe"
if not runner_template.is_file() or runner_template.read_bytes()[:2] != b"MZ":
    raise RuntimeError(f"Не найден автономный запускатель сессий: {runner_template}")
if assets_dir.is_dir():
    analysis.datas += Tree(str(assets_dir), prefix="assets")

pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(PROJECT_ROOT / "logo.ico"),
)
collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name=APP_NAME,
)
