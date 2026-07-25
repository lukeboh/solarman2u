from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from ..config import Config
from .base import Notifier

logger = logging.getLogger(__name__)


class EmailNotifier(Notifier):
    def __init__(self, config: Config):
        if not config.has_email_configured:
            raise ValueError("SMTP/e-mail não configurado (SMTP_HOST, ALERT_EMAIL_FROM, ALERT_EMAIL_TO).")
        self._config = config

    def send(self, subject: str, body: str) -> None:
        config = self._config
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = config.email_from
        message["To"] = ", ".join(config.email_to)
        message.set_content(body)

        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20) as smtp:
            if config.smtp_use_tls:
                smtp.starttls()
            if config.smtp_username:
                smtp.login(config.smtp_username, config.smtp_password)
            smtp.send_message(message)
        logger.info("E-mail de alerta enviado: %s", subject)
