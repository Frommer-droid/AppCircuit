"""Импорт и экспорт сессий без пользовательских настроек приложения."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from app.models import Session

FORMAT_NAME = "appcircuit.sessions"
FORMAT_VERSION = 1


def export_sessions(path: Path, sessions: list[Session]) -> None:
    payload = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "sessions": [
            {key: value for key, value in session.to_dict().items() if key != "export_selected"}
            for session in sessions
        ],
    }
    destination = Path(path)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def import_sessions(path: Path) -> list[Session]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("format") != FORMAT_NAME:
        raise ValueError("Это не файл экспорта сессий AppCircuit")
    if type(payload.get("version")) is not int or payload["version"] != FORMAT_VERSION:
        raise ValueError("Неподдерживаемая версия файла сессий")
    raw_sessions = payload.get("sessions")
    if not isinstance(raw_sessions, list) or not raw_sessions:
        raise ValueError("В файле нет сессий")

    sessions: list[Session] = []
    seen_names: set[str] = set()
    for number, raw_session in enumerate(raw_sessions, 1):
        if not isinstance(raw_session, dict):
            raise ValueError(f"Сессия {number}: неверный формат")
        name = raw_session.get("name")
        steps = raw_session.get("applications")
        if not isinstance(name, str) or not name.strip() or not isinstance(steps, list):
            raise ValueError(f"Сессия {number}: отсутствует имя или список шагов")
        name_key = name.strip().casefold()
        if name_key in seen_names:
            raise ValueError(f"Сессия {number}: повторяется имя «{name.strip()}»")
        seen_names.add(name_key)
        for step_number, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                raise ValueError(f"Сессия {number}, шаг {step_number}: неверный формат")
            if not isinstance(step.get("name"), str) or type(step.get("enabled")) is not bool:
                raise ValueError(f"Сессия {number}, шаг {step_number}: неверные свойства")
            is_pause = step.get("is_pause")
            if type(is_pause) is not bool:
                raise ValueError(f"Сессия {number}, шаг {step_number}: неверный тип шага")
            if is_pause:
                duration = step.get("duration")
                if (
                    step.get("action") != "pause"
                    or type(duration) is not int
                    or not 1 <= duration <= 10
                ):
                    raise ValueError(f"Сессия {number}, шаг {step_number}: неверная пауза")
            else:
                file_path = step.get("path")
                action = step.get("action")
                if not isinstance(file_path, str) or not file_path.strip():
                    raise ValueError(f"Сессия {number}, шаг {step_number}: нет пути")
                allowed_actions = (
                    {"launch", "stop"}
                    if Path(file_path).suffix.casefold() == ".exe"
                    else {"open"}
                )
                if not isinstance(action, str) or action not in allowed_actions:
                    raise ValueError(f"Сессия {number}, шаг {step_number}: неверное действие")
        try:
            session = Session.from_dict(raw_session)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Сессия {number}: повреждённые данные") from exc
        session.id = uuid4().hex
        session.export_selected = False
        for step in session.applications:
            step.id = uuid4().hex
        sessions.append(session)
    return sessions
