from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .config import STATE_FILE_PATH


@dataclass
class StationDayState:
    day: str
    started_at: str | None = None
    ended_at: str | None = None
    start_alert_sent: bool = False
    end_alert_sent: bool = False
    below_threshold_streak: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "start_alert_sent": self.start_alert_sent,
            "end_alert_sent": self.end_alert_sent,
            "below_threshold_streak": self.below_threshold_streak,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StationDayState":
        return cls(**data)


@dataclass
class AppState:
    stations: dict[str, StationDayState] = field(default_factory=dict)

    def station_state(self, station_id: str) -> StationDayState:
        today = date.today().isoformat()
        current = self.stations.get(station_id)
        if current is None or current.day != today:
            current = StationDayState(day=today)
            self.stations[station_id] = current
        return current

    def save(self) -> None:
        STATE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {"stations": {sid: st.to_dict() for sid, st in self.stations.items()}}
        STATE_FILE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    @classmethod
    def load(cls) -> "AppState":
        if not STATE_FILE_PATH.exists():
            return cls()
        try:
            data = json.loads(STATE_FILE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return cls()
        stations = {
            sid: StationDayState.from_dict(st) for sid, st in data.get("stations", {}).items()
        }
        return cls(stations=stations)
