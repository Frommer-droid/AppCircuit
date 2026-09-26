from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from app.models import ApplicationEntry


@dataclass(slots=True)
class Session:
    id: str
    name: str
    applications: list[ApplicationEntry] = field(default_factory=list)
    export_selected: bool = False

    @classmethod
    def create(cls, name: str) -> Session:
        return cls(id=uuid4().hex, name=name.strip() or "Новая сессия")

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> Session:
        raw_applications = value.get("applications") or []
        applications = [
            ApplicationEntry.from_dict(item) for item in raw_applications
        ]
        return cls(
            id=str(value.get("id") or uuid4().hex),
            name=str(value.get("name") or "Новая сессия"),
            applications=applications,
            export_selected=bool(value.get("export_selected", False)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "applications": [item.to_dict() for item in self.applications],
            "export_selected": self.export_selected,
        }
