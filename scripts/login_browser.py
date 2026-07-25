#!/usr/bin/env python3
"""Abre um browser visível para logar manualmente em home.solarmanpv.com.

Útil quando o login automático (usuário/senha) esbarra em captcha ou
verificação em duas etapas. A sessão obtida fica salva em
.secrets/storage_state.json e os tokens em data/tokens.json, para serem
reaproveitados pelos outros scripts até expirarem.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solarman_alerts.auth import interactive_browser_login, save_tokens
from solarman_alerts.config import load_config


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    tokens = interactive_browser_login(config)
    save_tokens(tokens)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
