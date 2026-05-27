from __future__ import annotations

import re

# ANSI colors for terminal output
_GREEN = '\033[92m'
_YELLOW = '\033[93m'
_RED = '\033[91m'
_RESET = '\033[0m'

# Confidence boost when normalized value passes validation for field type.
# Caps at 1.0.
_VALIDATION_BOOST = 0.15


def _log_result(field_name: str, original: str, normalized: str, confidence: float | None = None) -> None:
    """Log normalization result with color: yellow=changed, green=OK, red=low confidence."""
    conf_str = f" [conf: {confidence:.2f}]" if confidence is not None else ""

    if confidence is not None and confidence < 0.7:
        color = _RED
        prefix = "[LOW CONF]"
    elif original != normalized:
        color = _YELLOW
        prefix = "[NORMALIZED]"
    else:
        color = _GREEN
        prefix = "[OK]"

    print(f"{color}{prefix} {field_name}: '{original}' → '{normalized}'{conf_str}{_RESET}")


# ---------------------------------------------------------------------------
# Rules registry: (keyword_regex, normalize_function, validate_function, display_name)
# ---------------------------------------------------------------------------
_RULES: list[tuple[re.Pattern, callable, callable | None, str]] = []


def _rule(name: str, keywords_re: re.Pattern, validator: callable | None = None):
    """Decorator to register a normalization rule with optional validator."""
    def decorator(fn):
        _RULES.append((keywords_re, fn, validator, name))
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Validators — return True if normalized value looks correct for the field type
# ---------------------------------------------------------------------------
def _valid_dob(value: str) -> bool:
    m = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', value)
    if not m:
        return False
    d, mo = int(m.group(1)), int(m.group(2))
    return 1 <= d <= 31 and 1 <= mo <= 12


def _valid_phone(value: str) -> bool:
    digits = re.sub(r'[^0-9+]', '', value)
    return len(digits) >= 10


def _valid_nin(value: str) -> bool:
    # UK NIN: 2 letters, 6 digits, 1 letter
    return bool(re.fullmatch(r'[A-Z]{2}\d{6}[A-Z]', value))


_UK_POSTCODE_RE = re.compile(r'^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$')


def _valid_postcode(value: str) -> bool:
    return bool(_UK_POSTCODE_RE.match(value))


def _valid_amount(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


# Known cities/countries for semantic validation
from utils.known_places import KNOWN_PLACES


def _valid_place(value: str) -> bool:
    return value.lower().strip() in KNOWN_PLACES


@_rule('DOB', re.compile(r'(?i)(d\.?o\.?b|date[\s_]*of[\s_]*birth|birth[\s_]*date|\bdate\b)'), _valid_dob)
def _normalize_dob(value: str) -> str:
    # "27 1080" → "27/10/80"
    value = re.sub(r'\b(\d{2})\s(\d{2})(\d{2})\b', r'\1/\2/\3', value)
    # "01 660" → "01/06/60" (DD space D+YY, single-digit month lost its leading zero)
    value = re.sub(r'\b(\d{2})\s(\d)(\d{2})\b', r'\1/0\2/\3', value)
    # "27 10 80" or "27 10 1980" → "27/10/80"
    value = re.sub(r'\b(\d{1,2})\s(\d{1,2})\s(\d{2,4})\b', r'\1/\2/\3', value)
    # 5 digits no separators "01660" → "01/06/60" (single-digit month)
    value = re.sub(r'\b(\d{2})(\d)(\d{2})\b', r'\1/0\2/\3', value)
    # 6 digits no separators "111280" → "11/12/80"
    value = re.sub(r'\b(\d{2})(\d{2})(\d{2})\b', r'\1/\2/\3', value)
    # 8 digits no separators "27101980" → "27/10/1980" then truncate
    value = re.sub(r'\b(\d{2})(\d{2})(\d{4})\b', r'\1/\2/\3', value)
    # Truncate 4-digit year to 2-digit: "27/10/1980" → "27/10/80"
    value = re.sub(r'\b(\d{2}/\d{2}/)(\d{2})\d{2}\b', r'\1\2', value)
    return value


@_rule('Phone', re.compile(r'(?i)(phone|tel|telephone|mobile|contact[\s_]*number|mob)'), _valid_phone)
def _normalize_phone(value: str) -> str:
    return re.sub(r'[\s\-]', '', value)


@_rule('NIN', re.compile(r'(?i)(n\.?i\.?n|ni[\s_]*number|national[\s_]*insurance|insurance[\s_]*number)'), _valid_nin)
def _normalize_nin(value: str) -> str:
    return re.sub(r'\s', '', value).upper()


@_rule('Postcode', re.compile(r'(?i)(post[\s_]*code|postal[\s_]*code|zip|postcode)'), _valid_postcode)
def _normalize_postcode(value: str) -> str:
    # UK postcode: A9 9AA, A99 9AA, A9A 9AA, AA9 9AA, AA99 9AA, AA9A 9AA
    # Positions are strict: letters vs digits are fixed, so we can fix OCR errors.

    # OCR substitution maps
    _to_digit = str.maketrans('OoIiLlSsZzBb', '001111552288')
    _to_alpha = str.maketrans('01258', 'OIZsb')

    def _fix_ocr(raw: str) -> str:
        """Fix OCR mis-reads based on known letter/digit positions in UK postcodes."""
        # Work on uppercase stripped value
        raw = raw.upper()
        n = len(raw)
        if n < 5 or n > 7:
            return raw

        # Inward code is always last 3 chars: digit + 2 letters
        inward = raw[-3:]
        outward = raw[:-3]

        # Fix inward: position 0 must be digit, positions 1-2 must be letters
        fixed_inward = (
            inward[0].translate(_to_digit) +
            inward[1].translate(_to_alpha) +
            inward[2].translate(_to_alpha)
        )

        # Fix outward: first 1-2 chars are letters, then a digit, then optional digit/letter
        fixed_outward = ''
        for i, ch in enumerate(outward):
            if i < len(outward) - 1:
                # All chars before the last one in outward are letters (area code)
                # except the last which is always a digit (district)
                fixed_outward += ch.translate(_to_alpha)
            else:
                # Last char of outward is always a digit
                fixed_outward += ch.translate(_to_digit)

        # Handle formats where outward has 4 chars (AA9A): last is letter/digit - leave as-is
        # More precise: if outward is 3+ chars, char at index -2 is the required digit
        if len(outward) >= 3:
            fixed_outward = ''
            for i, ch in enumerate(outward):
                if i < len(outward) - 2:
                    # Area letters
                    fixed_outward += ch.translate(_to_alpha)
                elif i == len(outward) - 2:
                    # District digit (always a digit)
                    fixed_outward += ch.translate(_to_digit)
                else:
                    # Sub-district: could be digit or letter — leave as-is
                    fixed_outward += ch
        elif len(outward) == 2:
            # Format A9: first is letter, second is digit
            fixed_outward = outward[0].translate(_to_alpha) + outward[1].translate(_to_digit)

        return fixed_outward + ' ' + fixed_inward

    # Strip and attempt extraction
    raw = re.sub(r'[^A-Za-z0-9]', '', value).upper()
    if 5 <= len(raw) <= 7:
        result = _fix_ocr(raw)
        if _UK_POSTCODE_RE.match(result):
            return result

    # Fallback: try regex on original value
    match = re.search(
        r'([A-Za-z]{1,2}\d[A-Za-z\d]?)\s*(\d[A-Za-z]{2})',
        value,
    )
    if match:
        return (match.group(1) + ' ' + match.group(2)).upper()

    # Last resort: format with space before last 3
    if len(raw) >= 5:
        return raw[:-3] + ' ' + raw[-3:]
    return raw


@_rule('Amount', re.compile(r'(?i)(amount|total|sum|balance|payment|salary|wage|income|price|cost|fee|asset|value|worth|equity|capital|net)'), _valid_amount)
def _normalize_amount(value: str) -> str:
    value = re.sub(r'[£$€]', '', value).strip()
    # Convert word multipliers to numeric: "1million" → "1000000"
    _multipliers = {
        'k': 1_000, 'thousand': 1_000,
        'm': 1_000_000, 'million': 1_000_000, 'mil': 1_000_000,
        'b': 1_000_000_000, 'billion': 1_000_000_000,
    }
    for word, mult in _multipliers.items():
        m = re.match(rf'^([\d,.]+)\s*{word}$', value, re.IGNORECASE)
        if m:
            try:
                num = float(m.group(1).replace(',', ''))
                result = int(num * mult) if (num * mult) == int(num * mult) else num * mult
                return str(result)
            except ValueError:
                pass
    value = re.sub(r'[\s,]', '', value)
    return value


@_rule('Passport/ID', re.compile(r'(?i)(passport|document[\s_]*no|id[\s_]*number|identity|travel[\s_]*doc)'))
def _normalize_passport(value: str) -> str:
    return re.sub(r'\s', '', value).upper()


def _valid_email(value: str) -> bool:
    return bool(re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value))


@_rule('Email', re.compile(r'(?i)(e[-_\s]?mail|email[\s_]*address)'), _valid_email)
def _normalize_email(value: str) -> str:
    # Email cannot contain spaces
    return re.sub(r'\s', '', value).lower()


@_rule('Place', re.compile(r'(?i)(city|town|country|nationality|county|region|state|place[\s_]*of[\s_]*birth)'), _valid_place)
def _normalize_place(value: str) -> str:
    return value.strip()


@_rule('Signature', re.compile(r'(?i)(signature|signed|sign[\s_]*here)'))
def _normalize_signature(value: str) -> str:
    # OCR text from signatures is unreliable; just indicate presence
    return 'Signed' if value.strip() else ''


# ---------------------------------------------------------------------------
# Main entry point — normalize extracted fields dict
# ---------------------------------------------------------------------------
def normalize_fields(
    fields: dict,
    word_confidence_map: dict[str, float] | None = None,
) -> dict:
    """Normalize values in LLM-extracted fields dict based on key matching.
    If word_confidence_map is provided, adds confidence scores to output.
    """
    from utils.doc_intelligence import get_value_confidence

    result = {}
    for key, value in fields.items():
        if isinstance(value, dict):
            result[key] = normalize_fields(value, word_confidence_map)
            continue
        if isinstance(value, list):
            result[key] = [
                normalize_fields(item, word_confidence_map) if isinstance(item, dict) else item
                for item in value
            ]
            continue
        if not isinstance(value, str):
            result[key] = value
            continue

        # Calculate base confidence from OCR words
        confidence = None
        if word_confidence_map:
            confidence = get_value_confidence(value, word_confidence_map)

        # Apply normalization rules
        matched = False
        for keywords_re, normalize_fn, validator, name in _RULES:
            if keywords_re.search(key):
                original = value
                normalized = normalize_fn(value)

                # Adjust confidence based on validation result
                if confidence is not None and validator:
                    if validator(normalized):
                        confidence = round(min(confidence + _VALIDATION_BOOST, 1.0), 2)
                    else:
                        confidence = round(max(confidence - _VALIDATION_BOOST * 2, 0.0), 2)

                _log_result(name, original, normalized, confidence)

                result[key] = {"value": normalized, "confidence": confidence} if confidence is not None else normalized
                matched = True
                break

        if not matched:
            if confidence is not None:
                result[key] = {"value": value, "confidence": confidence}
            else:
                result[key] = value

    return result
