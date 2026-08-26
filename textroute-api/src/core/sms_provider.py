"""SMS provider seam — application code never talks to Twilio/etc. directly."""

from __future__ import annotations

import logging
import os
from typing import Protocol
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)


class SmsProvider(Protocol):
    def send_sms(
        self,
        *,
        from_number: str,
        to_number: str,
        body: str,
    ) -> str:
        """Send an SMS. Returns the provider message id."""


class LoggingSmsProvider:
    """Dev/test provider: log the send and return a synthetic id."""

    def send_sms(
        self,
        *,
        from_number: str,
        to_number: str,
        body: str,
    ) -> str:
        provider_id = f"log_{uuid4().hex[:16]}"
        logger.info(
            "sms_provider_send",
            extra={
                "provider": "logging",
                "from_number": from_number,
                "to_number": to_number,
                "body_preview": body[:80],
                "provider_message_id": provider_id,
            },
        )
        print(
            f"[LoggingSmsProvider] from={from_number} to={to_number} "
            f"id={provider_id} body={body!r}"
        )
        return provider_id


class HttpSmsProvider:
    """POST JSON to a webhook URL (e.g. local bridge / mock provider).

    Expected response JSON may include ``provider_message_id`` / ``sid``;
    otherwise a synthetic id is generated.
    """

    def __init__(self, url: str, timeout_seconds: float = 10.0):
        self.url = url
        self.timeout_seconds = timeout_seconds

    def send_sms(
        self,
        *,
        from_number: str,
        to_number: str,
        body: str,
    ) -> str:
        response = httpx.post(
            self.url,
            json={
                "from": from_number,
                "to": to_number,
                "body": body,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        provider_id = f"http_{uuid4().hex[:16]}"
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            provider_id = str(
                payload.get("provider_message_id")
                or payload.get("sid")
                or payload.get("id")
                or provider_id
            )
        logger.info(
            "sms_provider_send",
            extra={
                "provider": "http",
                "url": self.url,
                "provider_message_id": provider_id,
            },
        )
        return provider_id


class SmsProviderError(Exception):
    """Raised when the provider fails to send."""


def get_sms_provider() -> SmsProvider:
    """Factory from env: ``SMS_PROVIDER=logging|http``."""
    kind = (os.getenv("SMS_PROVIDER") or "logging").strip().lower()
    if kind == "http":
        url = os.getenv("SMS_PROVIDER_URL")
        if not url:
            raise RuntimeError(
                "SMS_PROVIDER=http requires SMS_PROVIDER_URL to be set."
            )
        return HttpSmsProvider(url)
    if kind == "logging":
        return LoggingSmsProvider()
    raise RuntimeError(f"Unknown SMS_PROVIDER={kind!r}; use 'logging' or 'http'.")
