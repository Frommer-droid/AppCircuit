from pathlib import Path
from subprocess import CompletedProcess

from app.models import ApplicationEntry
from app.services.process_service import ProcessService


def entry(path: Path, process_name: str | None = None) -> ApplicationEntry:
    item = ApplicationEntry.from_path(str(path))
    item.name = Path(path).stem
    if process_name is not None:
        item.process_name = process_name
    return item


def test_launch_reports_missing_file(tmp_path) -> None:
    report = ProcessService().launch([entry(tmp_path / "missing.exe")])

    assert not report.succeeded
    assert "файл не найден" in report.failed[0]


def test_open_files_uses_system_association_in_order(monkeypatch, tmp_path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.pdf"
    first.touch()
    second.touch()
    opened = []
    monkeypatch.setattr(
        "app.services.process_service.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )

    report = ProcessService().open_files([entry(first), entry(second)])

    assert [Path(path) for path in opened] == [first, second]
    assert report.succeeded == ["first", "second"]


def test_open_files_reports_missing_file_and_failed_association(
    monkeypatch, tmp_path
) -> None:
    present = tmp_path / "unsupported.xyz"
    present.touch()
    monkeypatch.setattr(
        "app.services.process_service.QDesktopServices.openUrl",
        lambda _url: False,
    )

    report = ProcessService().open_files([entry(tmp_path / "missing.txt"), entry(present)])

    assert "файл не найден" in report.failed[0]
    assert "не удалось открыть" in report.failed[1]


def test_launch_uses_executable_directory(monkeypatch, tmp_path) -> None:
    executable = tmp_path / "Demo App.exe"
    executable.touch()
    calls = []
    monkeypatch.setattr(
        ProcessService,
        "_running_process_ids_by_path",
        staticmethod(dict),
    )
    monkeypatch.setattr("app.services.process_service.subprocess.Popen", lambda *a, **kw: calls.append((a, kw)))

    report = ProcessService().launch([entry(executable)])

    assert report.succeeded == ["Demo App"]
    assert calls[0][0][0] == [str(executable)]
    assert calls[0][1]["cwd"] == str(tmp_path)


def test_launch_skips_exact_executable_that_is_already_running(
    monkeypatch, tmp_path
) -> None:
    executable = tmp_path / "Demo App.exe"
    executable.touch()
    calls = []
    monkeypatch.setattr(
        ProcessService,
        "_running_process_ids_by_path",
        staticmethod(
            lambda: {
                ProcessService._normalize_executable_path(executable): {101}
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.process_service.subprocess.Popen",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    report = ProcessService().launch([entry(executable, "DEMO APP.EXE")])

    assert report.skipped == ["Demo App"]
    assert not report.succeeded
    assert not report.failed
    assert not calls


def test_launch_starts_same_process_name_from_different_directory(
    monkeypatch, tmp_path
) -> None:
    running_executable = tmp_path / "portable-one" / "Telegram.exe"
    selected_executable = tmp_path / "portable-two" / "Telegram.exe"
    selected_executable.parent.mkdir()
    selected_executable.touch()
    calls = []
    monkeypatch.setattr(
        ProcessService,
        "_running_process_ids_by_path",
        staticmethod(
            lambda: {
                ProcessService._normalize_executable_path(running_executable): {101}
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.process_service.subprocess.Popen",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    report = ProcessService().launch([entry(selected_executable)])

    assert report.succeeded == ["Telegram"]
    assert not report.skipped
    assert len(calls) == 1


def test_launch_starts_same_process_name_from_two_directories_in_one_batch(
    monkeypatch, tmp_path
) -> None:
    first_path = tmp_path / "one" / "shared.exe"
    second_path = tmp_path / "two" / "shared.exe"
    first_path.parent.mkdir()
    second_path.parent.mkdir()
    first_path.touch()
    second_path.touch()
    calls = []
    monkeypatch.setattr(
        ProcessService,
        "_running_process_ids_by_path",
        staticmethod(dict),
    )
    monkeypatch.setattr(
        "app.services.process_service.subprocess.Popen",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    first = entry(first_path, "shared.exe")
    second = entry(second_path, "SHARED.exe")
    report = ProcessService().launch([first, second])

    assert report.succeeded == ["shared", "shared"]
    assert not report.skipped
    assert len(calls) == 2


def test_launch_does_not_start_same_executable_twice_in_one_batch(
    monkeypatch, tmp_path
) -> None:
    executable = tmp_path / "shared.exe"
    executable.touch()
    calls = []
    monkeypatch.setattr(
        ProcessService,
        "_running_process_ids_by_path",
        staticmethod(dict),
    )
    monkeypatch.setattr(
        "app.services.process_service.subprocess.Popen",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    report = ProcessService().launch([entry(executable), entry(executable)])

    assert report.succeeded == ["shared"]
    assert report.skipped == ["shared"]
    assert len(calls) == 1


def test_stop_uses_pid_for_exact_executable_path(monkeypatch, tmp_path) -> None:
    selected = tmp_path / "portable-one" / "Telegram.exe"
    other = tmp_path / "portable-two" / "Telegram.exe"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        ProcessService,
        "_running_process_ids_by_path",
        staticmethod(
            lambda: {
                ProcessService._normalize_executable_path(selected): {101},
                ProcessService._normalize_executable_path(other): {202},
            }
        ),
    )
    monkeypatch.setattr("app.services.process_service.subprocess.run", fake_run)

    report = ProcessService().stop([entry(selected)])

    assert calls == [["taskkill", "/PID", "101", "/F", "/T"]]
    assert report.succeeded == ["Telegram"]
    assert not report.skipped


def test_stop_terminates_all_pids_for_same_executable(monkeypatch, tmp_path) -> None:
    executable = tmp_path / "Browser.exe"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        ProcessService,
        "_running_process_ids_by_path",
        staticmethod(
            lambda: {
                ProcessService._normalize_executable_path(executable): {302, 301}
            }
        ),
    )
    monkeypatch.setattr("app.services.process_service.subprocess.run", fake_run)

    report = ProcessService().stop([entry(executable)])

    assert calls == [
        ["taskkill", "/PID", "301", "/F", "/T"],
        ["taskkill", "/PID", "302", "/F", "/T"],
    ]
    assert report.succeeded == ["Browser"]


def test_stop_does_not_stop_same_executable_twice_in_one_batch(
    monkeypatch, tmp_path
) -> None:
    executable = tmp_path / "shared.exe"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        ProcessService,
        "_running_process_ids_by_path",
        staticmethod(
            lambda: {
                ProcessService._normalize_executable_path(executable): {101}
            }
        ),
    )
    monkeypatch.setattr("app.services.process_service.subprocess.run", fake_run)

    report = ProcessService().stop([entry(executable), entry(executable)])

    assert len(calls) == 1
    assert report.succeeded == ["shared"]
    assert report.skipped == ["shared"]


def test_stop_skips_executable_that_is_not_running(monkeypatch, tmp_path) -> None:
    calls = []
    monkeypatch.setattr(
        ProcessService,
        "_running_process_ids_by_path",
        staticmethod(dict),
    )
    monkeypatch.setattr(
        "app.services.process_service.subprocess.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    report = ProcessService().stop([entry(tmp_path / "missing.exe")])

    assert report.skipped == ["missing"]
    assert not report.succeeded
    assert not report.failed
    assert not calls
