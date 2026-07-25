from __future__ import annotations

import logging
from datetime import datetime, time as dt_time

from .client import SolarmanClient, Station
from .config import Config
from .notifiers.base import Notifier
from .state import AppState, StationDayState

logger = logging.getLogger(__name__)


def _now_local(config: Config) -> datetime:
    return datetime.now(config.timezone)


def _parse_hhmm(value: str) -> dt_time:
    hour, minute = value.split(":")
    return dt_time(int(hour), int(minute))


def _resolve_stations(client: SolarmanClient, config: Config) -> list[Station]:
    stations = client.list_stations()
    if config.station_ids:
        wanted = set(config.station_ids)
        stations = [s for s in stations if s.id in wanted]
    return stations


def check_once(config: Config, client: SolarmanClient, notifier: Notifier, state: AppState) -> None:
    now = _now_local(config)
    end_not_before = _parse_hhmm(config.end_not_before)

    stations = _resolve_stations(client, config)
    if not stations:
        logger.warning("Nenhuma usina encontrada/selecionada para monitorar.")
        return

    for station in stations:
        power_w = client.get_station_power_w(station.id)
        if power_w is None:
            continue

        day_state = state.station_state(station.id)
        _evaluate_station(config, notifier, station, day_state, power_w, now, end_not_before)

    state.save()


def _evaluate_station(
    config: Config,
    notifier: Notifier,
    station: Station,
    day_state: StationDayState,
    power_w: float,
    now: datetime,
    end_not_before: dt_time,
) -> None:
    if not day_state.start_alert_sent:
        if power_w >= config.start_threshold_w:
            day_state.started_at = now.isoformat()
            day_state.start_alert_sent = True
            _send(
                notifier,
                subject=f"[Solarman] {station.name}: geração iniciada",
                body=(
                    f"A usina '{station.name}' começou a gerar energia hoje às "
                    f"{now.strftime('%H:%M')} (potência atual: {power_w:.0f} W)."
                ),
            )
        return

    if day_state.end_alert_sent:
        return

    if now.time() < end_not_before:
        return

    if power_w <= config.end_threshold_w:
        day_state.below_threshold_streak += 1
    else:
        day_state.below_threshold_streak = 0

    if day_state.below_threshold_streak >= config.end_confirmations:
        day_state.ended_at = now.isoformat()
        day_state.end_alert_sent = True
        started_label = "?"
        if day_state.started_at:
            started_label = datetime.fromisoformat(day_state.started_at).strftime("%H:%M")
        _send(
            notifier,
            subject=f"[Solarman] {station.name}: geração encerrada",
            body=(
                f"A usina '{station.name}' parou de gerar energia hoje por volta de "
                f"{now.strftime('%H:%M')} (início às {started_label})."
            ),
        )


def _send(notifier: Notifier, subject: str, body: str) -> None:
    try:
        notifier.send(subject, body)
    except Exception:
        logger.exception("Falha ao enviar alerta '%s'", subject)
