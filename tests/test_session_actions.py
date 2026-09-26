from app.core.application import ApplicationCore
from app.core.settings_store import SettingsStore
from app.models import ApplicationEntry, Session
from app.services.process_service import ActionReport


def test_session_applies_program_file_and_pause_in_order(monkeypatch, tmp_path) -> None:
    core = ApplicationCore()
    core.store = SettingsStore(tmp_path / "settings.json")
    core.settings = core.store.load()
    session = Session.create("Работа")
    program = ApplicationEntry.from_path(str(tmp_path / "editor.exe"))
    document = ApplicationEntry.from_path(str(tmp_path / "notes.txt"))
    pause = ApplicationEntry.from_path("")
    pause.is_pause = True
    pause.duration = 2
    session.applications = [program, pause, document]
    calls = []

    def launch(items):
        calls.append(("launch", items[0].name))
        return ActionReport("Запуск", succeeded=[items[0].name])

    def open_files(items):
        calls.append(("open", items[0].name))
        return ActionReport("Открытие", succeeded=[items[0].name])

    monkeypatch.setattr(core.processes, "launch", launch)
    monkeypatch.setattr(core.processes, "open_files", open_files)
    monkeypatch.setattr("time.sleep", lambda seconds: calls.append(("pause", seconds)))

    report = core.run_session_action(session)

    assert calls == [
        ("launch", program.name),
        ("pause", 2),
        ("open", document.name),
    ]
    assert report.succeeded == [program.name, document.name]
