import json
from pathlib import Path

import pytest

from app.core.application import ApplicationCore
from app.core.settings_store import SettingsStore
from app.models import ApplicationEntry


def make_core(tmp_path: Path) -> ApplicationCore:
    core = ApplicationCore()
    core.store = SettingsStore(tmp_path / "settings.json")
    core.settings = core.store.load()
    return core


def test_export_checked_sessions_and_replace_matching_name(tmp_path) -> None:
    source = make_core(tmp_path / "source")
    source.store.settings_file.parent.mkdir()
    session = source.add_session("Работа")
    program = ApplicationEntry.from_path(r"C:\Apps\Editor\editor.exe")
    program.action = "stop"
    document = ApplicationEntry.from_path(r"C:\Docs\plan.pdf")
    document.enabled = False
    pause = ApplicationEntry(
        id="pause-id", name="Пауза", path="", process_name="",
        action="pause", is_pause=True, duration=4,
    )
    session.applications = [program, pause, document]
    session.export_selected = True
    source.update_session(session)
    source.add_session("Не отмечена")
    exported = tmp_path / "sessions.json"

    assert source.export_sessions(exported) == 1
    payload = json.loads(exported.read_text(encoding="utf-8"))
    assert set(payload) == {"format", "version", "sessions"}
    assert len(payload["sessions"]) == 1
    assert "export_selected" not in payload["sessions"][0]
    assert payload["sessions"][0]["applications"][1]["duration"] == 4

    destination = make_core(tmp_path / "destination")
    destination.store.settings_file.parent.mkdir()
    original = destination.add_session("работа")
    original.export_selected = True
    original.applications = [ApplicationEntry.from_path(r"C:\Apps\Old\old.exe")]
    destination.update_session(original)
    untouched = destination.add_session("Личная")
    imported = destination.import_sessions(exported)

    assert len(destination.sessions) == 2
    assert imported[0].name == "Работа"
    assert imported[0].id == original.id
    assert imported[0].export_selected is True
    assert [step.id for step in imported[0].applications] != [
        step.id for step in session.applications
    ]
    assert [step.action for step in imported[0].applications] == ["stop", "pause", "open"]
    assert imported[0].applications[1].duration == 4
    assert imported[0].applications[2].enabled is False
    assert destination.import_sessions(exported)[0].id == original.id
    assert [item.name for item in destination.sessions] == ["Работа", "Личная"]
    assert destination.get_session(untouched.id).to_dict() == untouched.to_dict()
    assert len(SettingsStore(destination.store.settings_file).load()["sessions"]) == 2


def test_import_adds_name_that_does_not_exist(tmp_path) -> None:
    source = make_core(tmp_path)
    source.add_session("Новая")
    exported = tmp_path / "sessions.json"
    from app.core.session_transfer import export_sessions

    export_sessions(exported, source.sessions)
    destination = make_core(tmp_path / "other")
    destination.store.settings_file.parent.mkdir()
    existing = destination.add_session("Старая")

    imported = destination.import_sessions(exported)

    assert [session.name for session in destination.sessions] == ["Старая", "Новая"]
    assert destination.get_session(existing.id).name == "Старая"
    assert imported[0].export_selected is False


def test_export_without_checked_sessions_does_not_write_file(tmp_path) -> None:
    core = make_core(tmp_path)
    core.add_session("Не отмечена")
    target = tmp_path / "sessions.json"

    with pytest.raises(ValueError, match="Отметьте галочками"):
        core.export_sessions(target)

    assert not target.exists()


def test_invalid_import_leaves_current_sessions_untouched(tmp_path) -> None:
    core = make_core(tmp_path)
    original = core.add_session("Моя сессия")
    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        json.dumps({
            "format": "appcircuit.sessions", "version": 1,
            "sessions": [
                {"name": "Первая", "applications": []},
                {"name": "Вторая", "applications": [
                    {"name": "Ошибка", "enabled": True, "is_pause": False,
                     "path": r"C:\Docs\file.txt", "action": "stop"},
                ]},
            ],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="неверное действие"):
        core.import_sessions(invalid)

    assert [session.id for session in core.sessions] == [original.id]
    assert [session["id"] for session in SettingsStore(core.store.settings_file).load()["sessions"]] == [original.id]


def test_import_rejects_unrelated_json(tmp_path) -> None:
    core = make_core(tmp_path)
    unrelated = tmp_path / "settings.json"
    unrelated.write_text('{"sessions": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="не файл экспорта"):
        core.import_sessions(unrelated)


def test_ambiguous_local_name_does_not_overwrite_any_session(tmp_path) -> None:
    source = make_core(tmp_path)
    source.add_session("Работа")
    exported = tmp_path / "sessions.json"
    from app.core.session_transfer import export_sessions

    export_sessions(exported, source.sessions)
    destination = make_core(tmp_path / "other")
    destination.store.settings_file.parent.mkdir()
    first = destination.add_session("Работа")
    second = destination.add_session("РАБОТА")

    with pytest.raises(ValueError, match="несколько"):
        destination.import_sessions(exported)

    assert [session.id for session in destination.sessions] == [first.id, second.id]


def test_duplicate_names_in_file_are_rejected(tmp_path) -> None:
    core = make_core(tmp_path)
    exported = tmp_path / "sessions.json"
    exported.write_text(
        json.dumps({
            "format": "appcircuit.sessions", "version": 1,
            "sessions": [
                {"name": "Работа", "applications": []},
                {"name": "работа", "applications": []},
            ],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="повторяется имя"):
        core.import_sessions(exported)

    assert core.sessions == []
