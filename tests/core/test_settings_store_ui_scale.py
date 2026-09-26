import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from app.core.settings_store import SettingsStore


def test_defaults_contain_scale_keys(tmp_path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = store.load()
    assert settings["ui_scale_mode"] == "auto"
    assert settings["ui_scale_delta_percent"] == 0
    assert settings["ui_scale_percent"] == 100


def test_normalization_clamps_delta_and_percent(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"ui_scale_delta_percent": 100, "ui_scale_percent": 999}),
        encoding="utf-8",
    )
    settings = SettingsStore(path).load()
    assert settings["ui_scale_delta_percent"] == 50
    assert settings["ui_scale_percent"] == 300


def test_legacy_percent_migrated_to_delta(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"ui_scale_percent": 120}), encoding="utf-8")
    settings = SettingsStore(path).load()
    assert settings["ui_scale_delta_percent"] == 20
    assert settings["ui_scale_percent"] == 120


def test_normalization_rounds_delta_to_step_10(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"ui_scale_delta_percent": 7}), encoding="utf-8")
    settings = SettingsStore(path).load()
    assert settings["ui_scale_delta_percent"] == 10
