from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.session_executable import (
    FOOTER_MAGIC,
    PAYLOAD_MAGIC,
    RUNNER_TEMPLATE,
    create_session_executable,
    serialize_session,
    suggested_executable_name,
)
from app.models import ApplicationEntry, Session


def _read_text(payload: bytes, offset: int) -> tuple[str, int]:
    size = struct.unpack_from("<I", payload, offset)[0]
    offset += 4
    return payload[offset : offset + size].decode("utf-8"), offset + size


def test_serialization_uses_selected_session_steps_in_order() -> None:
    session = Session.create('Работа: "утро"')
    session.applications = [
        ApplicationEntry.from_path(r"C:\Tools\program.exe"),
        ApplicationEntry(
            id="pause", name="Пауза", path="", process_name="", action="pause",
            is_pause=True, duration=3,
        ),
        ApplicationEntry.from_path(r"C:\Docs\plan.pdf"),
    ]
    session.applications[0].action = "stop"
    session.applications[2].enabled = False
    session.export_selected = False

    payload = serialize_session(session)
    assert payload.startswith(PAYLOAD_MAGIC)
    name, offset = _read_text(payload, len(PAYLOAD_MAGIC))
    count = struct.unpack_from("<I", payload, offset)[0]
    assert name == session.name
    assert count == 2
    assert payload[offset + 4] == 2  # stop
    _, offset = _read_text(payload, offset + 4 + 5)
    _, offset = _read_text(payload, offset)
    assert payload[offset] == 4  # pause
    assert suggested_executable_name(session) == "Работа_ _утро_.exe"


def test_executable_contains_snapshot_and_uses_requested_location(tmp_path: Path) -> None:
    session = Session.create("Быстрый запуск")
    session.applications = [
        ApplicationEntry(
            id="pause", name="Пауза", path="", process_name="", action="pause",
            is_pause=True, duration=1,
        )
    ]
    payload = serialize_session(session)
    target = create_session_executable(session, tmp_path / "Anywhere")
    content = target.read_bytes()
    assert target.name == "Anywhere.exe"
    assert content.startswith(RUNNER_TEMPLATE.read_bytes())
    assert content[-len(FOOTER_MAGIC) :] == FOOTER_MAGIC
    assert struct.unpack_from("<I", content, -len(FOOTER_MAGIC) - 4)[0] == len(payload)
    assert content[-len(FOOTER_MAGIC) - 4 - len(payload) : -len(FOOTER_MAGIC) - 4] == payload
    session.name = "Изменено после создания"
    assert payload in target.read_bytes()


@pytest.mark.skipif(sys.platform != "win32", reason="Автономный EXE предназначен для Windows")
def test_generated_executable_runs_without_appcircuit(tmp_path: Path) -> None:
    session = Session.create("Проверка")
    session.applications = [
        ApplicationEntry(
            id="pause", name="Пауза", path="", process_name="", action="pause",
            is_pause=True, duration=1,
        )
    ]
    target = create_session_executable(session, tmp_path / "session.exe")
    smoke = subprocess.run([str(target), "--smoke-test"], timeout=15, check=False)
    applied = subprocess.run([str(target)], timeout=15, check=False)
    assert smoke.returncode == 0
    assert applied.returncode == 0


def test_empty_session_does_not_create_executable(tmp_path: Path) -> None:
    session = Session.create("Пустая")
    target = tmp_path / "empty.exe"
    with pytest.raises(ValueError, match="нет включённых шагов"):
        create_session_executable(session, target)
    assert not target.exists()
