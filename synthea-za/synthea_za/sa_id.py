"""South African identifier helpers: ID numbers, passports, telephone numbers."""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Optional, Set


def luhn_check_digit(digits: str) -> int:
    """Return the Luhn check digit for a string of digits (without the check digit)."""
    total = 0
    # process from the right, doubling every second digit starting with the right-most
    for index, char in enumerate(reversed(digits)):
        number = int(char)
        if index % 2 == 0:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return (10 - (total % 10)) % 10


def luhn_valid(number: str) -> bool:
    """True when the full number (including its check digit) passes the Luhn check."""
    if not number.isdigit() or len(number) < 2:
        return False
    return luhn_check_digit(number[:-1]) == int(number[-1])


def _stable_int(*parts: str, modulus: int) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulus


def south_african_id(
    birth_date: date,
    gender: str,
    seed: str,
    citizen: bool = True,
    used: Optional[Set[str]] = None,
) -> str:
    """Build a valid 13 digit South African identity number.

    Format: YYMMDD SSSS C A Z where SSSS is a gender sequence (0000-4999 female,
    5000-9999 male), C is citizenship (0 citizen, 1 permanent resident), A is 8 and
    Z is the Luhn check digit. The sequence is derived deterministically from ``seed``
    so that repeated runs produce the same number for the same patient. When ``used``
    is supplied the sequence is advanced until the number is unique within that set.
    """
    yymmdd = birth_date.strftime("%y%m%d")
    female = str(gender).lower().startswith("f")
    base = 0 if female else 5000
    sequence = base + _stable_int(seed, "sequence", modulus=5000)
    citizenship = "0" if citizen else "1"
    for _ in range(5000):
        body = f"{yymmdd}{sequence:04d}{citizenship}8"
        number = body + str(luhn_check_digit(body))
        if used is None or number not in used:
            if used is not None:
                used.add(number)
            return number
        sequence = base + ((sequence - base + 1) % 5000)
    raise RuntimeError("Unable to allocate a unique South African ID number")


def south_african_passport(seed: str) -> str:
    """A passport number in the South African format: one letter followed by 8 digits."""
    number = _stable_int(seed, "passport", modulus=90_000_000) + 10_000_000
    return f"A{number:08d}"


MOBILE_PREFIXES = [
    "060", "061", "062", "063", "064", "065", "066", "067", "068", "069",
    "071", "072", "073", "074", "076", "078", "079",
    "081", "082", "083", "084",
]


def south_african_mobile(seed: str) -> str:
    """A mobile number in the national format, for example ``072 345 6789``."""
    prefix = MOBILE_PREFIXES[_stable_int(seed, "prefix", modulus=len(MOBILE_PREFIXES))]
    rest = _stable_int(seed, "number", modulus=10_000_000)
    digits = f"{rest:07d}"
    return f"{prefix} {digits[:3]} {digits[3:]}"


def hpcsa_registration(seed: str, category: str = "MP") -> str:
    """A practitioner registration number in the HPCSA style, e.g. ``MP 0456789``."""
    number = _stable_int(seed, "hpcsa", modulus=9_000_000) + 100_000
    return f"{category} {number:07d}"
