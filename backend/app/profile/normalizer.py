import re
from typing import Optional
from app.schemas.form import FormField

# Mapping rules: canonical_key -> list of regex patterns / token synonyms
CANONICAL_FIELD_RULES = {
    "first_name": [
        r"^(first[_\s-]?name|fname|given[_\s-]?name|forename)$",
        r"\b(first name|given name|fname)\b"
    ],
    "last_name": [
        r"^(last[_\s-]?name|lname|surname|family[_\s-]?name)$",
        r"\b(last name|surname|family name|lname)\b"
    ],
    "full_name": [
        r"^(full[_\s-]?name|your[_\s-]?name|name|display[_\s-]?name)$",
        r"\b(full name|your name|contact name)\b"
    ],
    "email": [
        r"^(email|e[_-]?mail([_\s-]?address)?)$",
        r"\b(email|e-mail|email address)\b"
    ],
    "phone": [
        r"^(phone([_\s-]?number)?|telephone|mobile([_\s-]?number)?|tel|cell([_\s-]?phone)?)$",
        r"\b(phone number|mobile number|telephone|cell phone|phone)\b"
    ],
    "address": [
        r"^(street([_\s-]?address)?|address([_\s-]?line[_\s-]?1)?|residential[_\s-]?address)$",
        r"\b(street address|address line 1|home address|billing address)\b"
    ],
    "city": [
        r"^(city|town|locality)$",
        r"\b(city|town)\b"
    ],
    "state": [
        r"^(state|province|region)$",
        r"\b(state|province|region)\b"
    ],
    "postal_code": [
        r"^(zip([_\s-]?code)?|postal([_\s-]?code)?|pincode|pin[_\s-]?code)$",
        r"\b(zip code|postal code|pin code|zipcode)\b"
    ],
    "country": [
        r"^(country|nation)$",
        r"\b(country|nation)\b"
    ],
    "date_of_birth": [
        r"^(date[_\s-]?of[_\s-]?birth|dob|birth[_\s-]?date|birthday)$",
        r"\b(date of birth|dob|birth date|birthday)\b"
    ],
    "gender": [
        r"^(gender|sex)$",
        r"\b(gender|sex)\b"
    ],
    "company": [
        r"^(company([_\s-]?name)?|organization|employer|workplace)$",
        r"\b(company|organization|employer)\b"
    ],
    "job_title": [
        r"^(job[_\s-]?title|designation|occupation|role|title)$",
        r"\b(job title|designation|occupation)\b"
    ]
}

AUTOCOMPLETE_MAP = {
    "given-name": "first_name",
    "family-name": "last_name",
    "name": "full_name",
    "email": "email",
    "tel": "phone",
    "tel-national": "phone",
    "tel-country-code": "phone",
    "street-address": "address",
    "address-line1": "address",
    "address-level2": "city",
    "address-level1": "state",
    "postal-code": "postal_code",
    "country": "country",
    "country-name": "country",
    "bday": "date_of_birth",
    "bday-day": "date_of_birth",
    "sex": "gender",
    "organization": "company",
    "organization-title": "job_title"
}


def normalize_key_string(text: str) -> Optional[str]:
    """
    Normalizes a free-form field name or label string into a canonical profile key.
    """
    if not text:
        return None

    clean = text.lower().strip()
    clean_punct = re.sub(r"[^\w\s-]", "", clean)

    # 1. Exact canonical key check
    if clean_punct in CANONICAL_FIELD_RULES:
        return clean_punct

    # 2. Rule-based regex matching
    for canon_key, patterns in CANONICAL_FIELD_RULES.items():
        for pat in patterns:
            if re.search(pat, clean_punct, re.IGNORECASE):
                return canon_key

    return None


def normalize_form_field(field: FormField) -> Optional[str]:
    """
    Analyzes all rich DOM signals from M1 FormField to determine canonical profile key.
    Signals checked in priority order:
    1. HTML autocomplete attribute
    2. HTML input type (e.g. email, tel)
    3. Label text
    4. Field name
    5. Placeholder text
    6. ARIA label
    7. Field ID
    """
    # 1. Autocomplete attribute
    if field.autocomplete:
        auto = field.autocomplete.lower().strip()
        for prefix in ("billing ", "shipping "):
            if auto.startswith(prefix):
                auto = auto[len(prefix):]
        if auto in AUTOCOMPLETE_MAP:
            return AUTOCOMPLETE_MAP[auto]

    # 2. HTML Type
    if field.type == "email":
        return "email"
    elif field.type == "tel":
        return "phone"

    # 3. Text signals in prioritized order
    signals = [
        field.label,
        field.name,
        field.placeholder,
        field.aria.label if field.aria else "",
        field.id
    ]

    for sig in signals:
        if sig:
            canon = normalize_key_string(sig)
            if canon:
                return canon

    return None
