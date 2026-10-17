import pytest

from synthea_za.config import PROVINCES, allocate_patients, find_province


def test_allocation_sums_to_total_and_follows_population():
    allocation = allocate_patients(1000)
    assert sum(allocation.values()) == 1000
    assert allocation["Gauteng"] > allocation["KwaZulu-Natal"] > allocation["Northern Cape"]
    assert allocate_patients(0) == {}
    small = allocate_patients(3)
    assert sum(small.values()) == 3 and set(small) <= {p.name for p in PROVINCES}


def test_find_province_accepts_names_and_codes():
    assert find_province("gauteng").code == "GP"
    assert find_province("KZN").name == "KwaZulu-Natal"
    assert find_province("kwazulu natal").code == "KZN"
    with pytest.raises(ValueError):
        find_province("Narnia")
