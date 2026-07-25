#!/usr/bin/env python3
"""Ajuda a descobrir os nomes reais dos campos de potência/energia da sua conta.

Roda a listagem de usinas e imprime o JSON bruto de station/information para
cada uma, para você comparar com POWER_FIELD_CANDIDATES em
solarman_alerts/client.py e ajustar se necessário.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solarman_alerts.client import SolarmanClient
from solarman_alerts.config import load_config


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    config = load_config()

    with SolarmanClient(config) as client:
        stations = client.list_stations()
        print(f"Encontradas {len(stations)} usina(s):\n")
        for station in stations:
            print(f"- id={station.id!r} name={station.name!r}")

        for station in stations:
            print(f"\n=== station/information para {station.id} ({station.name}) ===")
            info = client.get_station_info(station.id)
            print(json.dumps(info, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
