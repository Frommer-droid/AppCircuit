from pathlib import Path

from app.models import ApplicationEntry


def test_application_entry_is_created_from_executable_path() -> None:
    entry = ApplicationEntry.from_path(r"D:\Apps\My_Tool\launcher.exe")

    assert entry.name == "My Tool"
    assert entry.process_name == "launcher.exe"
    assert Path(entry.path).name == "launcher.exe"
    assert entry.enabled is True


def test_application_entry_preserves_custom_name_from_settings() -> None:
    entry = ApplicationEntry.from_dict(
        {
            "path": r"D:\Apps\Telegram-29\Telegram.exe",
            "name": "Личный Telegram",
        }
    )

    assert entry.name == "Личный Telegram"


def test_file_entry_uses_filename_and_open_action() -> None:
    entry = ApplicationEntry.from_path(r"D:\Documents\Quarterly report.pdf")

    assert entry.name == "Quarterly report.pdf"
    assert entry.action == "open"
    assert ApplicationEntry.from_dict(entry.to_dict()).action == "open"


def test_legacy_non_executable_entry_is_opened() -> None:
    entry = ApplicationEntry.from_dict(
        {"path": r"D:\Documents\notes.txt", "action": "launch"}
    )

    assert entry.action == "open"
