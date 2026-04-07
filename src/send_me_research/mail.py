from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Iterable, Optional


class Mailer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender

    def send_digest(
        self,
        *,
        recipients: Iterable[str],
        subject: str,
        html_body: str,
    ) -> None:
        recipients = self._normalize_recipients(recipients)
        for recipient in recipients:
            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = self.sender
            message["To"] = recipient
            message.set_content("This digest is best viewed in an HTML-capable email client.")
            message.add_alternative(html_body, subtype="html")
            self._send(message)

    def send_text(
        self,
        *,
        recipients: Iterable[str],
        subject: str,
        body: str,
    ) -> None:
        recipients = self._normalize_recipients(recipients)
        for recipient in recipients:
            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = self.sender
            message["To"] = recipient
            message.set_content(body)
            self._send(message)

    def _send(self, message: EmailMessage) -> None:
        with smtplib.SMTP_SSL(self.host, self.port) as smtp:
            smtp.login(self.username, self.password)
            smtp.send_message(message)

    def _normalize_recipients(self, recipients: Iterable[str]) -> list[str]:
        return [recipient.strip() for recipient in recipients if recipient and recipient.strip()]
