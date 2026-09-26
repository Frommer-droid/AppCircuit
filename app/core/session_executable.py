"""Создание автономного Windows EXE из снимка одной сессии."""

from __future__ import annotations

import re
import shutil
import struct
from pathlib import Path
from uuid import uuid4

from app.core.app_config import resource_path
from app.models import Session

PAYLOAD_MAGIC = b"ACS1DATA"
FOOTER_MAGIC = b"APPcircuit-SESS!"
MAX_PAYLOAD_SIZE = 1024 * 1024
RUNNER_TEMPLATE = resource_path("assets", "runner", "AppCircuitSession.exe")
ACTION_CODES = {"launch": 1, "stop": 2, "open": 3, "pause": 4}


def suggested_executable_name(session: Session) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", session.name).strip(" .")
    return f"{name or 'Сессия'}.exe"


def _encoded_text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<I", len(encoded)) + encoded


def serialize_session(session: Session) -> bytes:
    enabled = [step for step in session.applications if step.enabled]
    if not enabled:
        raise ValueError("В выбранной сессии нет включённых шагов")
    payload = bytearray(PAYLOAD_MAGIC)
    payload.extend(_encoded_text(session.name))
    payload.extend(struct.pack("<I", len(enabled)))
    for step in enabled:
        action = "pause" if step.is_pause else step.action
        if action not in ACTION_CODES:
            raise ValueError(f"Неподдерживаемое действие: {action}")
        if action == "pause":
            if not 1 <= step.duration <= 10:
                raise ValueError("Пауза должна быть от 1 до 10 секунд")
        elif not step.path or not Path(step.path).is_absolute():
            raise ValueError(f"Для шага «{step.name}» нужен абсолютный путь")
        payload.extend(struct.pack("<BI", ACTION_CODES[action], step.duration if step.is_pause else 0))
        payload.extend(_encoded_text(step.name))
        payload.extend(_encoded_text(step.path if not step.is_pause else ""))
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise ValueError("Сессия слишком велика для автономного EXE")
    return bytes(payload)


def create_session_executable(
    session: Session,
    destination: Path,
    runner_template: Path = RUNNER_TEMPLATE,
) -> Path:
    target = Path(destination)
    if target.suffix.casefold() != ".exe":
        target = target.with_name(target.name + ".exe")
    if not runner_template.is_file():
        raise FileNotFoundError("Шаблон автономного запуска не найден в AppCircuit")
    payload = serialize_session(session)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        with runner_template.open("rb") as source, temporary.open("wb") as output:
            shutil.copyfileobj(source, output)
            output.write(payload)
            output.write(struct.pack("<I", len(payload)))
            output.write(FOOTER_MAGIC)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
