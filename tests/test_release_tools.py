from __future__ import annotations

import runpy
import tomllib
from pathlib import Path

from app.core import app_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_TOOLS = PROJECT_ROOT / "Build_Tools"
APP_NAME = "AppCircuit"


def test_release_configuration_has_no_unresolved_placeholders() -> None:
    files = (
        BUILD_TOOLS / "AppCircuit.spec",
        BUILD_TOOLS / "post_build.py",
        BUILD_TOOLS / "SpecCompiler.pyw",
        PROJECT_ROOT / "00_CrRel_setup.pyw",
        PROJECT_ROOT / "00_Move.pyw",
    )
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "REPLACE_WITH" not in text
        assert "REPLACE-WITH" not in text


def test_version_is_single_sourced_from_version_file() -> None:
    metadata = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()

    assert metadata["project"]["dynamic"] == ["version"]
    assert metadata["tool"]["setuptools"]["dynamic"]["version"] == {
        "file": ["VERSION"]
    }
    parts = version.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_appcircuit_branding_is_used_by_runtime_and_build_tools() -> None:
    assert app_config.APP_NAME == APP_NAME
    assert app_config.APP_USER_MODEL_ID == "frommer.appcircuit.desktop.1"
    assert (PROJECT_ROOT / "AppCircuit.py").is_file()
    assert (BUILD_TOOLS / "AppCircuit.spec").is_file()
    assert not (PROJECT_ROOT / "job-app-off-on.py").exists()
    assert not (BUILD_TOOLS / "Job App Off On.spec").exists()


def test_spec_prioritizes_trusted_dll_search_paths() -> None:
    spec_text = (BUILD_TOOLS / "AppCircuit.spec").read_text(encoding="utf-8")

    assert "prioritize_trusted_dll_search_paths" in spec_text
    assert 'system_root / "System32"' in spec_text
    assert 'os.environ["PATH"] = os.pathsep.join(unique_paths)' in spec_text
    assert "TRUSTED_BINARY_ROOTS" in spec_text
    assert "Path(binary[1]).resolve().is_relative_to(root)" in spec_text
    assert "foreign_binaries" in spec_text
    assert "raise RuntimeError" in spec_text
    assert "existing_paths" not in spec_text
    assert "qt_msvc_runtime" in spec_text
    assert "pyi_rth_pyside6_dll_path.py" not in spec_text


def test_required_release_documents_and_icon_exist() -> None:
    required = (
        "logo.ico",
        "LICENSE",
        "EULA.md",
        "THIRD_PARTY_NOTICES.md",
        "SOURCE_CODE_ACCESS.md",
        "QT_PYSIDE6_COMPLIANCE.md",
        "LGPL-3.0.txt",
        "GPL-3.0.txt",
    )
    assert all((PROJECT_ROOT / filename).is_file() for filename in required)
    assert (PROJECT_ROOT / "logo.ico").stat().st_size > 0
    assert (PROJECT_ROOT / "LGPL-3.0.txt").stat().st_size > 7_000
    assert (PROJECT_ROOT / "GPL-3.0.txt").stat().st_size > 30_000


def test_resource_path_falls_back_to_pyinstaller_bundle(monkeypatch, tmp_path) -> None:
    external = tmp_path / "release"
    bundle = tmp_path / "release" / "_internal"
    bundled_icon = bundle / "assets" / "icons" / "add.svg"
    bundled_icon.parent.mkdir(parents=True)
    bundled_icon.touch()
    monkeypatch.setattr(app_config, "ROOT_DIR", external)
    monkeypatch.setattr(app_config, "BUNDLE_DIR", bundle)

    assert app_config.resource_path("assets", "icons", "add.svg") == bundled_icon


def test_inno_script_contains_required_install_and_uninstall_rules(tmp_path) -> None:
    namespace = runpy.run_path(str(PROJECT_ROOT / "00_CrRel_setup.pyw"))
    version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    script = namespace["build_iss_script"](
        app_name=APP_NAME,
        app_id=namespace["APP_ID"],
        app_publisher="Frommer-droid",
        version=version,
        exe_name=f"{APP_NAME}.exe",
        work_dir=tmp_path / APP_NAME,
        output_dir=tmp_path,
        default_install_dir=Path(r"D:\Apps") / APP_NAME,
        setup_icon_file=PROJECT_ROOT / "logo.ico",
    )

    assert "UsePreviousAppDir=no" in script
    assert "DefaultDirName=\"D:\\Apps\\AppCircuit\"" in script
    assert "Flags: nowait postinstall skipifsilent" in script
    assert "Type: filesandordirs; Name: \"{app}\"" in script
    assert "ArchitecturesInstallIn64BitMode=x64compatible" in script
    assert "WorkingDir: \"{app}\"" in script


def test_portable_replacement_preserves_settings(tmp_path) -> None:
    namespace = runpy.run_path(str(PROJECT_ROOT / "00_Move.pyw"))
    source = tmp_path / "source"
    target = tmp_path / "AppCircuit"
    legacy = tmp_path / "Previous App"
    source.mkdir()
    target.mkdir()
    legacy.mkdir()
    (source / "AppCircuit.exe").touch()
    (target / "settings.json").write_text("current", encoding="utf-8")
    (legacy / "settings.json").write_text("legacy", encoding="utf-8")

    preserved = namespace["preserved_runtime_files"](target, (legacy,))
    namespace["replace_portable_folder"](source, target, preserved)

    assert (target / "AppCircuit.exe").is_file()
    assert (target / "settings.json").read_text(encoding="utf-8") == "current"
