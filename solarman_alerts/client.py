from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from .auth import TokenSet, get_valid_tokens
from .config import Config

logger = logging.getLogger(__name__)

# Endpoints reverse-engineered do bundle JS público de home.solarmanpv.com.
# Não são documentados oficialmente e podem mudar sem aviso.
STATION_SEARCH_PATH = "/maintain-s/operating/station/search"
STATION_INFO_PATH = "/maintain-s/operating/station/information/{station_id}"

# Nomes de campo candidatos para potência instantânea (W), na ordem em que
# tentamos extrair. Ajuste/complete depois de rodar scripts/dump_station_data.py
# e inspecionar o JSON real retornado pela sua conta.
POWER_FIELD_CANDIDATES = (
    "generationPower",
    "currentPower",
    "power",
    "realPower",
    "outputPower",
)

STATION_LIST_FIELD_CANDIDATES = ("stationList", "list", "records", "data")


@dataclass
class Station:
    id: str
    name: str
    raw: dict[str, Any]


class SolarmanApiError(RuntimeError):
    pass


class SolarmanClient:
    def __init__(self, config: Config):
        self._config = config
        self._tokens: TokenSet | None = None
        self._http = httpx.Client(base_url=config.base_url, timeout=20)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "SolarmanClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _ensure_tokens(self) -> TokenSet:
        if self._tokens is None or self._tokens.is_expired():
            self._tokens = get_valid_tokens(self._config)
        return self._tokens

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        tokens = self._ensure_tokens()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {tokens.access_token}"
        response = self._http.request(method, path, headers=headers, **kwargs)
        if response.status_code == 401:
            logger.info("Recebido 401, renovando sessão e tentando novamente...")
            self._tokens = get_valid_tokens(self._config)
            headers["Authorization"] = f"Bearer {self._tokens.access_token}"
            response = self._http.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise SolarmanApiError(f"{method} {path} -> HTTP {response.status_code}: {response.text[:300]}")
        return response.json()

    def list_stations(self) -> list[Station]:
        payload = self._request("POST", STATION_SEARCH_PATH, json={"page": 1, "size": 100})
        items = payload
        for key in STATION_LIST_FIELD_CANDIDATES:
            if isinstance(payload, dict) and key in payload:
                items = payload[key]
                break
        if isinstance(items, dict) and "data" in items:
            items = items["data"]
        if not isinstance(items, list):
            raise SolarmanApiError(f"Formato inesperado na listagem de usinas: {payload!r}")

        stations = []
        for item in items:
            station_id = str(item.get("id") or item.get("stationId") or item.get("code") or "")
            name = str(item.get("name") or item.get("stationName") or station_id)
            stations.append(Station(id=station_id, name=name, raw=item))
        return stations

    def get_station_info(self, station_id: str) -> dict[str, Any]:
        return self._request("GET", STATION_INFO_PATH.format(station_id=station_id))

    def get_station_power_w(self, station_id: str) -> float | None:
        info = self.get_station_info(station_id)
        payload = info.get("data", info) if isinstance(info, dict) else info
        for field in POWER_FIELD_CANDIDATES:
            if isinstance(payload, dict) and field in payload and payload[field] is not None:
                try:
                    return float(payload[field])
                except (TypeError, ValueError):
                    continue
        logger.warning(
            "Não encontrei um campo de potência conhecido na resposta da usina %s. "
            "Rode scripts/dump_station_data.py para inspecionar o JSON e atualizar "
            "POWER_FIELD_CANDIDATES em client.py. Payload: %s",
            station_id,
            payload,
        )
        return None
