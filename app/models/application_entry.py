from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(slots=True)
class ApplicationEntry:
    id: str
    name: str
    path: str
    process_name: str
    enabled: bool = True
    action: str = "launch"
    is_pause: bool = False
    duration: int = 1

    @staticmethod
    def default_name_for_path(path: str | Path) -> str:
        executable = Path(path)
        if executable.suffix.casefold() != ".exe":
            return executable.name
        source = executable.parent.name.strip() or executable.stem
        return source.replace("_", " ").strip()

    @classmethod
    def from_path(cls, path: str) -> ApplicationEntry:
        executable = Path(path)
        return cls(
            id=uuid4().hex,
            name=cls.default_name_for_path(executable),
            path=str(executable),
            process_name=executable.name,
            action="launch" if executable.suffix.casefold() == ".exe" else "open",
        )

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> ApplicationEntry:
        path = str(value.get("path", ""))
        fallback = cls.from_path(path)
        is_pause = bool(value.get("is_pause", False))
        action = str(value.get("action") or fallback.action)
        if not is_pause and Path(path).suffix.casefold() != ".exe":
            action = "open"
        return cls(
            id=str(value.get("id") or fallback.id),
            name=str(value.get("name") or fallback.name),
            path=path,
            process_name=str(value.get("process_name") or fallback.process_name),
            enabled=bool(value.get("enabled", True)),
            action=action,
            is_pause=is_pause,
            duration=int(value.get("duration", 1) or 1),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
