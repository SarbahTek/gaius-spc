"""
SMS sending — integration point for a real provider.

The API key / sender are read from settings (populated from environment). They
are intentionally left blank for now; when an SMS provider is chosen, fill in
`_send_via_provider` and set SMS_API_KEY in the environment. Until then,
`send_sms` is a safe no-op that logs the message (and, in DEBUG, prints it so
OTP login can be exercised end-to-end locally).
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(getattr(settings, "SMS_API_KEY", ""))


def send_sms(phone_number: str, message: str) -> bool:
    """
    Send an SMS. Returns True if it was dispatched (or stubbed in dev).

    When no provider is configured we DO NOT fail — we log the message so the
    rest of the flow (e.g. phone-login OTP) keeps working during development.
    """
    if not is_configured():
        logger.info("SMS (stub, no provider configured) → %s: %s", phone_number, message)
        if settings.DEBUG:
            print(f"\n[DEV SMS] to {phone_number}: {message}\n")
        return True

    return _send_via_provider(phone_number, message)


def _send_via_provider(phone_number: str, message: str) -> bool:
    """
    TODO: integrate a real SMS gateway here (e.g. Hubtel, Twilio, Termii).

    Example skeleton:

        import requests
        resp = requests.post(
            settings.SMS_PROVIDER_URL,
            headers={"Authorization": f"Bearer {settings.SMS_API_KEY}"},
            json={
                "from": settings.SMS_SENDER_ID,
                "to":   phone_number,
                "content": message,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return True
    """
    logger.warning("SMS provider configured but _send_via_provider is not implemented yet.")
    return False
