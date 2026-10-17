from synthea_za.units import convert_quantity


def test_known_conversions():
    assert convert_quantity("2339-0", 100.0, "mg/dL") == (5.6, "mmol/L")
    assert convert_quantity("2093-3", 200.0, "mg/dL") == (5.17, "mmol/L")
    assert convert_quantity("2160-0", 1.0, "mg/dL") == (88.0, "umol/L")
    assert convert_quantity("3094-0", 14.0, "mg/dL") == (5.0, "mmol/L")
    assert convert_quantity("6299-2", 14.0, "mg/dL") is None  # blood urea nitrogen is no longer relabelled


def test_unknown_code_or_unit_is_untouched():
    assert convert_quantity("2339-0", 5.0, "mmol/L") is None
    assert convert_quantity("8302-2", 170.0, "cm") is None


def test_converted_codes():
    from synthea_za.units import converted_code
    assert converted_code("2339-0") == ("15074-8", "Glucose [Moles/volume] in Blood")
    assert converted_code("1751-7") is None  # albumin keeps its mass concentration code
    assert converted_code("8302-2") is None
    assert convert_quantity("1751-7", 4.2, "g/dL") == (42.0, "g/L")
