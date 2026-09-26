from __future__ import annotations

from pathlib import Path

from app.core.app_config import LEGACY_SETTINGS_FILES, SETTINGS_FILE
from app.core.session_transfer import export_sessions, import_sessions
from app.core.settings_store import MAX_RECENT_APPLICATION_DIRECTORIES, SettingsStore
from app.models import ApplicationEntry, Session
from app.services.process_service import ActionReport, ProcessService


class ApplicationCore:
    def __init__(self) -> None:
        self.store = SettingsStore(SETTINGS_FILE, LEGACY_SETTINGS_FILES)
        self.settings = self.store.load()
        self.processes = ProcessService()

    @property
    def applications(self) -> list[ApplicationEntry]:
        return [ApplicationEntry.from_dict(item) for item in self.settings["applications"]]

    @property
    def sessions(self) -> list[Session]:
        return [Session.from_dict(item) for item in self.settings["sessions"]]

    def add_session(self, name: str) -> Session:
        session = Session.create(name)
        self.settings["sessions"].append(session.to_dict())
        self.save()
        return session

    def update_session(self, session: Session) -> None:
        sessions = self.settings["sessions"]
        for index, stored in enumerate(sessions):
            if str(stored.get("id")) == session.id:
                sessions[index] = session.to_dict()
                break
        else:
            sessions.append(session.to_dict())
        self.save()

    def remove_session(self, session_id: str) -> None:
        self.settings["sessions"] = [
            item
            for item in self.settings["sessions"]
            if str(item.get("id")) != session_id
        ]
        self.save()

    def get_session(self, session_id: str) -> Session | None:
        for session in self.sessions:
            if session.id == session_id:
                return session
        return None

    def export_sessions(self, path: Path) -> int:
        sessions = [session for session in self.sessions if session.export_selected]
        if not sessions:
            raise ValueError("Отметьте галочками сессии для экспорта")
        export_sessions(path, sessions)
        return len(sessions)

    def import_sessions(self, path: Path) -> list[Session]:
        imported = import_sessions(path)
        stored_sessions = self.sessions
        name_positions: dict[str, list[int]] = {}
        for index, session in enumerate(stored_sessions):
            name_positions.setdefault(session.name.strip().casefold(), []).append(index)
        for session in imported:
            positions = name_positions.get(session.name.strip().casefold(), [])
            if len(positions) > 1:
                raise ValueError(
                    f"Нельзя заменить сессию «{session.name}»: уже есть несколько с таким именем"
                )
            if positions:
                previous = stored_sessions[positions[0]]
                session.id = previous.id
                session.export_selected = previous.export_selected
                stored_sessions[positions[0]] = session
            else:
                name_positions[session.name.strip().casefold()] = [len(stored_sessions)]
                stored_sessions.append(session)
        updated_settings = {
            **self.settings,
            "sessions": [session.to_dict() for session in stored_sessions],
        }
        self.store.save(updated_settings)
        self.settings = updated_settings
        return imported

    def replace_applications(self, applications: list[ApplicationEntry]) -> None:
        self.settings["applications"] = [item.to_dict() for item in applications]
        self.save()

    @property
    def recent_application_directories(self) -> list[str]:
        return list(self.settings["recent_application_directories"])

    def remember_application_directories(self, application_paths: list[str]) -> None:
        recent_directories = self.recent_application_directories
        for application_path in application_paths:
            directory = Path(application_path).parent
            if not directory.is_dir():
                continue
            normalized = str(directory.resolve())
            key = normalized.casefold()
            recent_directories = [
                item for item in recent_directories if str(Path(item)).casefold() != key
            ]
            recent_directories.insert(0, normalized)
        self.settings["recent_application_directories"] = recent_directories[
            :MAX_RECENT_APPLICATION_DIRECTORIES
        ]
        self.save()

    def save(self) -> None:
        self.store.save(self.settings)

    def run_action(self, action: str, applications: list[ApplicationEntry]) -> ActionReport:
        if action == "open":
            return self.processes.open_files(applications)
        if action == "launch":
            return self.processes.launch(applications)
        if action == "stop":
            return self.processes.stop(applications)
        raise ValueError(f"Неизвестное действие: {action}")

    def run_session_action(self, session: Session, action: str | None = None) -> ActionReport:
        enabled = [item for item in session.applications if item.enabled]
        if action is not None:
            targets = [item for item in enabled if item.action == action]
            report = self.run_action(action, targets)
            action_names = {"open": "Открытие", "launch": "Запуск", "stop": "Остановка"}
            report.action = f"{action_names[action]} сессии «{session.name}»"
            return report

        import time

        report = ActionReport(f"Применение сессии «{session.name}»")
        for step in enabled:
            if step.is_pause:
                time.sleep(max(0, int(step.duration)))
                report.skipped.append(f"Пауза {step.duration} с")
                continue
            if step.action == "stop":
                sub = self.processes.stop([step])
            elif step.action == "open":
                sub = self.processes.open_files([step])
            else:
                sub = self.processes.launch([step])
            report.succeeded.extend(sub.succeeded)
            report.skipped.extend(sub.skipped)
            report.failed.extend(sub.failed)
        return report
