#!/usr/bin/env python3
"""Ponto de entrada para cron: roda uma verificação e sai.

Exemplo de crontab (a cada 5 minutos, das 5h às 21h):
    */5 5-21 * * * cd /caminho/do/projeto && .venv/bin/python scripts/check_production.py >> data/cron.log 2>&1
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solarman_alerts.client import SolarmanClient
from solarman_alerts.config import LOG_FILE_PATH, load_config
from solarman_alerts.notifiers.email import EmailNotifier
from solarman_alerts.production_monitor import check_once
from solarman_alerts.state import AppState


def main() -> int:
    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_FILE_PATH), logging.StreamHandler()],
    )

    config = load_config()

    # Setup incompleto (ainda faltam secrets/variables) não é uma falha de
    # execução de verdade — não deve contar como run quebrado (isso dispara
    # e-mail de falha do GitHub Actions a cada execução agendada). Só depois
    # que tudo estiver configurado é que um erro aqui deve "estourar" e virar
    # o alerta de falha (ex.: sessão expirada).
    if not config.has_email_configured or not (config.has_credentials or config.bootstrap_refresh_token):
        logging.warning(
            "Setup incompleto (faltam credenciais/refresh token e/ou SMTP) - "
            "pulando esta execução sem marcar como falha. Veja README.md."
        )
        return 0

    notifier = EmailNotifier(config)
    state = AppState.load()

    with SolarmanClient(config) as client:
        check_once(config, client, notifier, state)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
