from __future__ import annotations

from abc import ABC, abstractmethod


class Notifier(ABC):
    """Interface comum para canais de alerta (e-mail hoje; WhatsApp/Telegram depois)."""

    @abstractmethod
    def send(self, subject: str, body: str) -> None:
        ...
