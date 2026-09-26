import json

from app.core.application import ApplicationCore
from app.core.settings_store import SettingsStore
from app.models import ApplicationEntry


def test_missing_settings_returns_empty_application_list(tmp_path) -> None:
    settings = SettingsStore(tmp_path / "settings.json").load()

    assert settings["applications"] == []
    assert settings["window_width"] is None
    assert settings["window_geometry"] is None
    assert settings["recent_application_directories"] == []


def test_applications_and_window_size_round_trip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    entry = ApplicationEntry.from_path(r"C:\Tools\demo.exe")
    settings = store.load()
    settings["applications"] = [entry.to_dict()]
    settings["window_width"] = 1100
    settings["window_geometry"] = "dGVzdC1nZW9tZXRyeQ=="

    store.save(settings)
    restored = store.load()

    assert restored["applications"] == []
    assert len(restored["sessions"]) == 1
    assert restored["sessions"][0]["name"] == "Приложения"
    assert restored["sessions"][0]["applications"] == [entry.to_dict()]
    assert restored["window_width"] == 1100
    assert restored["window_geometry"] == "dGVzdC1nZW9tZXRyeQ=="
    assert (
        json.loads(path.read_text(encoding="utf-8"))["sessions"][0]["applications"][0][
            "name"
        ]
        == "Tools"
    )


def test_invalid_json_falls_back_to_defaults(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")

    settings = SettingsStore(path).load()

    assert settings["applications"] == []


def test_legacy_settings_are_migrated_to_new_location(tmp_path) -> None:
    current = tmp_path / "AppCircuit" / "settings.json"
    legacy = tmp_path / "Previous App" / "settings.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps(
            {
                "applications": [
                    ApplicationEntry.from_path(r"C:\\Apps\\Migrated.exe").to_dict()
                ],
                "window_width": 640,
                "window_height": 400,
            }
        ),
        encoding="utf-8",
    )
    current.parent.mkdir(parents=True)

    settings = SettingsStore(current, (legacy,)).load()

    assert settings["applications"] == []
    assert settings["sessions"][0]["applications"][0]["name"] == "Apps"
    assert settings["window_width"] == 640
    assert current.is_file()
    assert json.loads(current.read_text(encoding="utf-8"))["sessions"]


def test_duplicate_application_names_use_parent_directories(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "applications": [
                    {
                        "path": r"D:\Telegram-portable\Telegram-29\Telegram.exe",
                        "name": "Telegram",
                    },
                    {
                        "path": r"D:\Telegram-portable\Telegram-73\Telegram.exe",
                        "name": "Telegram",
                    },
                    {
                        "path": r"D:\v2rayN-NeVPN\v2rayN.exe",
                        "name": "v2rayN NeVPN",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    settings = SettingsStore(path).load()

    assert settings["applications"] == []
    assert [item["name"] for item in settings["sessions"][0]["applications"]] == [
        "Telegram-29",
        "Telegram-73",
        "v2rayN NeVPN",
    ]


def test_recent_application_directories_are_normalized(tmp_path) -> None:
    existing_directories = []
    for number in range(6):
        directory = tmp_path / f"Folder {number}"
        directory.mkdir()
        existing_directories.append(directory)
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "recent_application_directories": [
                    str(existing_directories[0]),
                    str(existing_directories[0]),
                    str(tmp_path / "Missing"),
                    *(str(path) for path in existing_directories[1:]),
                ]
            }
        ),
        encoding="utf-8",
    )

    settings = SettingsStore(settings_path).load()

    assert settings["recent_application_directories"] == [
        str(path.resolve()) for path in existing_directories[:5]
    ]


def test_application_core_remembers_five_most_recent_application_directories(
    tmp_path,
) -> None:
    settings_path = tmp_path / "settings.json"
    core = ApplicationCore()
    core.store = SettingsStore(settings_path)
    core.settings = core.store.load()
    application_paths = []
    for number in range(6):
        directory = tmp_path / f"Apps {number}"
        directory.mkdir()
        application_path = directory / f"Program {number}.exe"
        application_path.touch()
        application_paths.append(application_path)

    core.remember_application_directories([str(path) for path in application_paths])
    core.remember_application_directories([str(application_paths[3])])

    expected = [
        application_paths[index].parent.resolve()
        for index in (3, 5, 4, 2, 1)
    ]
    assert core.recent_application_directories == [str(path) for path in expected]
    assert SettingsStore(settings_path).load()["recent_application_directories"] == [
        str(path) for path in expected
    ]
