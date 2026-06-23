"""
Injects per-request globals into every template:
  - current user's cart item count
  - active language code + label
  - full language list (for the switcher)
  - translation strings for the active language
"""
import json
from pathlib import Path

from django.conf import settings


_LANG_CACHE: dict = {}


def _load_lang(code: str) -> dict:
    if code in _LANG_CACHE:
        return _LANG_CACHE[code]
    path = Path(settings.BASE_DIR) / 'locale' / f'{code}.json'
    if not path.exists():
        path = Path(settings.BASE_DIR) / 'locale' / 'en.json'
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    _LANG_CACHE[code] = data
    return data


def spc_globals(request):
    # Cart count
    cart_count = 0
    if request.user.is_authenticated:
        try:
            from payments.models import Cart
            cart = Cart.objects.filter(user=request.user).first()
            cart_count = cart.item_count if cart else 0
        except Exception:
            pass

    # Language
    lang_code = 'en'
    if request.user.is_authenticated:
        lang_code = getattr(request.user, 'language_preference', 'en')
    else:
        lang_code = request.session.get('lang', 'en')

    lang_map = dict(settings.LANGUAGES)
    translations = _load_lang(lang_code)

    return {
        'CART_COUNT':    cart_count,
        'LANG_CODE':     lang_code,
        'LANG_LABEL':    lang_map.get(lang_code, 'English'),
        'LANGUAGES':     settings.LANGUAGES,
        'T':             translations,
        'PAYSTACK_KEY':  settings.PAYSTACK_PUBLIC_KEY,
    }
