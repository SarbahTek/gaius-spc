"""
OTP generation, delivery and verification.

A single entry point (`issue`) creates a code and delivers it over the right
channel (email for email_verify, SMS for phone_*). `verify` checks a submitted
code with expiry + attempt limiting.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import OtpCode
from . import sms


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _expiry_minutes() -> int:
    return int(getattr(settings, "OTP_EXPIRY_MINUTES", 10))


def _max_attempts() -> int:
    return int(getattr(settings, "OTP_MAX_ATTEMPTS", 5))


def issue(identifier: str, purpose: str, channel: str = OtpCode.CHANNEL_EMAIL) -> OtpCode:
    """Create and deliver a fresh code. Invalidates any prior active codes."""
    OtpCode.objects.filter(
        identifier=identifier, purpose=purpose, is_used=False
    ).update(is_used=True)

    code = _generate_code()
    otp = OtpCode.objects.create(
        identifier=identifier,
        purpose=purpose,
        channel=channel,
        code=code,
        expires_at=timezone.now() + timedelta(minutes=_expiry_minutes()),
    )
    _deliver(otp)
    return otp


def _deliver(otp: OtpCode) -> None:
    minutes = _expiry_minutes()
    if otp.channel == OtpCode.CHANNEL_SMS:
        sms.send_sms(
            otp.identifier,
            f"Your SPC Campus code is {otp.code}. It expires in {minutes} minutes.",
        )
    else:
        subject = "Your SPC Campus verification code"
        body = (
            f"Welcome to SPC Campus!\n\n"
            f"Your verification code is: {otp.code}\n\n"
            f"It expires in {minutes} minutes. If you didn't request this, ignore this email."
        )
        # In DEBUG the console email backend prints this so it's testable locally.
        send_mail(
            subject, body,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@spccampus.com"),
            [otp.identifier],
            fail_silently=True,
        )


def verify(identifier: str, purpose: str, code: str) -> tuple[bool, str | None]:
    """
    Returns (ok, error_message). On success the code is consumed.
    """
    otp = (OtpCode.objects
           .filter(identifier=identifier, purpose=purpose, is_used=False)
           .order_by("-created_at")
           .first())

    if not otp:
        return False, "No active code found. Please request a new one."
    if otp.is_expired():
        return False, "This code has expired. Please request a new one."
    if otp.attempts >= _max_attempts():
        otp.is_used = True
        otp.save(update_fields=["is_used"])
        return False, "Too many attempts. Please request a new code."

    if otp.code != str(code).strip():
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        remaining = _max_attempts() - otp.attempts
        return False, f"Incorrect code. {remaining} attempt(s) left."

    otp.is_used = True
    otp.save(update_fields=["is_used"])
    return True, None
