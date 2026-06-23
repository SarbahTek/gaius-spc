"""
Paystack API wrapper.
Docs: https://paystack.com/docs/api/
"""
import requests
from django.conf import settings


PAYSTACK_BASE = "https://api.paystack.co"


def _headers():
    return {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type":  "application/json",
    }


def initialize_transaction(email: str, amount_ghs: float, reference: str, callback_url: str) -> dict:
    """
    Initialise a Paystack transaction.
    amount is in GHS — Paystack expects pesewas (×100).
    Returns the full Paystack response dict.
    """
    payload = {
        "email":        email,
        "amount":       int(float(amount_ghs) * 100),   # convert GHS → pesewas
        "reference":    reference,
        "callback_url": callback_url,
        "currency":     "GHS",
    }
    resp = requests.post(f"{PAYSTACK_BASE}/transaction/initialize", json=payload, headers=_headers())
    resp.raise_for_status()
    return resp.json()


def verify_transaction(reference: str) -> dict:
    """
    Verify a completed transaction.
    Returns the full Paystack response dict.
    """
    resp = requests.get(f"{PAYSTACK_BASE}/transaction/verify/{reference}", headers=_headers())
    resp.raise_for_status()
    return resp.json()
