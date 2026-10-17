from datetime import date

from synthea_za.sa_id import (hpcsa_registration, luhn_check_digit, luhn_valid, south_african_id,
                              south_african_mobile, south_african_passport)


def test_luhn_matches_known_identity_number():
    # 800101 5009 08 7 is a widely published example of a valid South African ID number
    assert luhn_check_digit("800101500908") == 7
    assert luhn_valid("8001015009087")
    assert not luhn_valid("8001015009088")


def test_identity_number_structure_and_determinism():
    number = south_african_id(date(1989, 11, 6), "male", "seed-a")
    assert len(number) == 13 and number.isdigit()
    assert number.startswith("891106")
    assert 5000 <= int(number[6:10]) <= 9999  # male sequence
    assert number[10] == "0" and number[11] == "8"
    assert luhn_valid(number)
    assert number == south_african_id(date(1989, 11, 6), "male", "seed-a")
    female = south_african_id(date(2001, 2, 28), "female", "seed-b", citizen=False)
    assert 0 <= int(female[6:10]) <= 4999
    assert female[10] == "1"
    assert luhn_valid(female)


def test_identity_numbers_are_unique_within_a_set():
    used = set()
    numbers = {south_african_id(date(1990, 1, 1), "F", "same-seed", used=used) for _ in range(5)}
    assert len(numbers) == 5
    assert all(luhn_valid(n) for n in numbers)


def test_passport_phone_and_registration_formats():
    assert south_african_passport("x").startswith("A") and len(south_african_passport("x")) == 9
    phone = south_african_mobile("x")
    parts = phone.split(" ")
    assert len(parts) == 3 and parts[0][0] == "0" and all(p.isdigit() for p in parts)
    assert hpcsa_registration("x").startswith("MP ")
