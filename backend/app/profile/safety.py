import re
from typing import Optional, Tuple
from app.schemas.form import FormField

PROHIBITED_KEY_PATTERNS = [
    r"pass(word)?",
    r"pwd",
    r"passcode",
    r"confirm.*pass",
    r"new.*pass",
    r"pin",
    r"secret",
    r"credit.*card",
    r"card.*number",
    r"debit.*card",
    r"cvv",
    r"cvc",
    r"security.*code",
    r"exp(ir(y|ation))?.*(date|month|year)",
    r"otp",
    r"auth.*code",
    r"verif(y|ication).*code",
    r"2fa",
    r"mfa",
    r"token",
    r"api[_\s-]?key",
    r"access[_\s-]?token",
    r"session[_\s-]?token",
    r"auth[_\s-]?token",
    r"bearer",
    r"ssn",
    r"social[_\s-]?sec",
    r"captcha",
    r"security[_\s-]?answer",
    r"security[_\s-]?question"
]

JWT_REGEX = re.compile(r"^eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$")
API_KEY_REGEX = re.compile(r"^(?:sk-[A-Za-z0-9-_]{10,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z-_]{35})$")
CREDIT_CARD_REGEX = re.compile(r"^(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|6(?:011|5[0-9]{2})[0-9]{12}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11})$")


def _matches_prohibited_patterns(text: str) -> bool:
    if not text:
        return False
    clean = re.sub(r"[\s_-]+", " ", text.lower().strip())
    for pattern in PROHIBITED_KEY_PATTERNS:
        if re.search(pattern, clean):
            return True
        if re.search(pattern, text.lower().strip()):
            return True
    return False


def is_sensitive_field(field: FormField) -> bool:
    """
    Evaluates FormField metadata from M1 DOM scanner to identify sensitive/secret fields.
    """
    if field.type.lower() == "password":
        return True

    text_signals = [
        field.name,
        field.label,
        field.placeholder,
        field.autocomplete or "",
        field.aria.label if field.aria else "",
        field.id
    ]

    for signal in text_signals:
        if signal and _matches_prohibited_patterns(signal):
            return True

    return False


def is_prohibited_candidate(canonical_key: str, value: str) -> Tuple[bool, Optional[str]]:
    """
    Deterministic safety evaluation for proposed profile fields.
    Returns (is_prohibited: bool, reason: Optional[str]).
    """
    if not canonical_key or not canonical_key.strip():
        return True, "EMPTY_CANONICAL_KEY"

    clean_key = canonical_key.lower().strip()

    # 1. Prohibited key names
    if _matches_prohibited_patterns(clean_key):
        return True, f"PROHIBITED_KEY_PATTERN: '{canonical_key}' contains prohibited sensitive pattern"

    str_val = str(value).strip() if value is not None else ""

    # 2. Value pattern checks
    # Token / JWT
    if JWT_REGEX.match(str_val):
        return True, "PROHIBITED_VALUE: Looks like a JWT/bearer token"

    # API key
    if API_KEY_REGEX.match(str_val):
        return True, "PROHIBITED_VALUE: Looks like an API key"

    # Credit card numbers (stripped of spaces and hyphens)
    digits_only = re.sub(r"[\s-]+", "", str_val)
    if digits_only.isdigit() and len(digits_only) in range(13, 20):
        if CREDIT_CARD_REGEX.match(digits_only) or _matches_luhn(digits_only):
            return True, "PROHIBITED_VALUE: Matches credit/debit card format"

    # CVV / CVC check
    if clean_key in ("cvv", "cvc", "security_code") and digits_only.isdigit() and len(digits_only) in (3, 4):
        return True, "PROHIBITED_VALUE: CVV/CVC code"

    # OTP / Auth code check
    if any(k in clean_key for k in ("otp", "auth_code", "verification")) and digits_only.isdigit() and len(digits_only) in range(4, 9):
        return True, "PROHIBITED_VALUE: OTP/Authentication code"

    return False, None


def _matches_luhn(number: str) -> bool:
    """Luhn algorithm verification for credit card number detection."""
    try:
        r = [int(ch) for ch in reversed(number)]
        return (sum(r[0::2]) + sum(sum(divmod(d * 2, 10)) for d in r[1::2])) % 10 == 0
    except Exception:
        return False
