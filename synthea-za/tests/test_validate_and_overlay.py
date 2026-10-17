import csv

from synthea_za.config import DATA_DIR, GenerationConfig
from synthea_za.overlay import build_overlay
from synthea_za.validate import (ValidationResult, _parse_simple_yaml_lists, check_providers_csv,
                                 validate_data_dir, validate_names)


def test_yaml_parser_handles_nested_pools():
    text = ("english:\n  M: [John, Peter]\n  F: [Mary]\n  family: [Smith]\n"
            "  asian: {M: [Raj], F: [Priya], family: [Naidoo]}\nstreet:\n  type: [Street,\n    Road]\n")
    data = _parse_simple_yaml_lists(text)
    assert data["english"]["M"] == ["John", "Peter"]
    assert data["english"]["asian"]["family"] == ["Naidoo"]
    assert data["street"]["type"] == ["Street", "Road"]


def test_names_validation_rejects_digits_and_symbols(tmp_path):
    path = tmp_path / "names.yml"
    path.write_text("zulu:\n  M: [Sipho, Thabo1]\n  F: [Nomvula, Lerato]\n  family: [Dlamini, Mo'koena]\n")
    result = ValidationResult()
    validate_names(path, result, minimum=1, require_english=False)
    messages = " ".join(str(i) for i in result.errors)
    assert "Thabo1" in messages and "Mo'koena" in messages


def test_provider_validation_checks_coordinates_and_province(tmp_path):
    path = tmp_path / "GP_hospitals.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "name", "address", "city", "state", "zip", "phone", "ownership", "emergency", "lat", "lon"])
        writer.writerow(["1", "Soweto Hospital", "Chris Hani Road", "Soweto", "Gauteng", "1864", "011 933 8000", "Government", "Yes", "-26.26", "27.94"])
        writer.writerow(["2", "Bad Hospital 2", "Road", "Nowhere", "Texas", "123", "555", "Government", "Maybe", "40.0", "-70.0"])
    result = ValidationResult()
    check_providers_csv(path, result)
    messages = " ".join(str(i) for i in result.errors)
    assert "Soweto Hospital" not in messages
    assert "Bad Hospital 2" in messages and "Texas" in messages and "outside South Africa" in messages


def test_packaged_data_is_valid():
    result = validate_data_dir(DATA_DIR)
    assert result.ok, "\n".join(str(i) for i in result.errors)


def test_overlay_contains_required_resources(tmp_path):
    config = GenerationConfig(patients=1, output_dir=tmp_path, years_of_history=7,
                              extra_properties={"generate.middle_names": "0.1"})
    overlay = build_overlay(config)
    assert (overlay.overlay_dir / "names.yml").is_file()
    assert (overlay.overlay_dir / "geography" / "demographics.csv").is_file()
    assert (overlay.overlay_dir / "providers" / "hospitals.csv").is_file()
    text = overlay.properties_file.read_text()
    assert "exporter.years_of_history = 7" in text
    assert "generate.middle_names = 0.1" in text
    assert "exporter.fhir.use_us_core_ig = false" in text
    if overlay.module_overrides_file:
        assert "module_override = " in text


def test_module_overrides_keys_are_escaped_for_java_properties():
    """Java's Properties parser splits keys at unescaped colons and spaces."""
    text = (DATA_DIR / "module_overrides.properties").read_text()
    keys = [line.split(" = ")[0] for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")]
    assert keys, "no overrides defined"
    for key in keys:
        assert "\\:\\:" in key, key
        unescaped = key.replace("\\:", "").replace("\\ ", "").replace("\\=", "")
        assert ":" not in unescaped and " " not in unescaped, key


def test_jar_is_stale_ignores_generated_version_file(tmp_path):
    import os
    import time
    from synthea_za.runner import jar_is_stale
    sources = tmp_path / "src" / "main"
    (sources / "java").mkdir(parents=True)
    (sources / "resources").mkdir()
    old = time.time() - 100
    source = sources / "java" / "Foo.java"
    source.write_text("class Foo {}")
    os.utime(source, (old, old))
    jar = tmp_path / "synthea.jar"
    jar.write_bytes(b"jar")
    os.utime(jar, (old + 10, old + 10))
    assert jar_is_stale(jar, sources) is False
    version = sources / "resources" / "version.txt"
    version.write_text("v1")  # written by every Gradle run, must not count
    assert jar_is_stale(jar, sources) is False
    source.write_text("class Foo { int x; }")  # now newer than the jar
    assert jar_is_stale(jar, sources) is True
    assert jar_is_stale(tmp_path / "missing.jar", sources) is False
