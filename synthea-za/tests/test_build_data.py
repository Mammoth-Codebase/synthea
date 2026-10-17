import csv

from synthea_za import build_data
from synthea_za.validate import _parse_simple_yaml_lists


def write_csv(path, header, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def test_build_names_merges_pools_and_derives_black_sub_pools(tmp_path):
    source = tmp_path / "names"
    source.mkdir()
    (source / "english.yml").write_text(
        "english:\n  M: [James]\n  F: [Sarah]\n  family: [Smith]\n"
        "  asian:\n    M: [Rajesh]\n    F: [Priya]\n    family: [Naidoo]\n")
    (source / "zulu.yml").write_text("zulu:\n  M: [Sipho]\n  F: [Nomvula]\n  family: [Dlamini]\n")
    (source / "sesotho.yml").write_text("sesotho:\n  M: [Thabo]\n  F: [Lerato]\n  family: [Mokoena]\n")
    (source / "street.yml").write_text("street:\n  name: [Vilakazi]\n  type: [Street]\n  secondary: [Unit]\n")
    target = tmp_path / "names.yml"
    build_data.build_names(source, target)
    data = _parse_simple_yaml_lists(target.read_text())
    assert data["english"]["M"] == ["James"]
    assert set(data["english"]["black"]["family"]) == {"Dlamini", "Mokoena"}
    assert data["hindi"]["family"] == ["Naidoo"]  # Indian languages reuse the Indian pool
    assert data["street"]["name"] == ["Vilakazi"]


def test_build_providers_renumbers_ids(tmp_path):
    source = tmp_path / "providers"
    source.mkdir()
    header = ["id", "name", "address", "city", "state", "zip", "phone", "ownership", "emergency", "lat", "lon"]
    write_csv(source / "GP_hospitals.csv", header,
              [["GP-H-1", "Soweto Hospital", "Road", "Soweto", "Gauteng", "1864", "011 933 8000", "Government", "Yes", "-26.26", "27.94"]])
    write_csv(source / "WC_hospitals.csv", header,
              [["WC-H-1", "Groote Schuur Hospital", "Main Road", "Observatory", "Western Cape", "7925", "021 404 9111", "Government", "Yes", "-33.94", "18.46"]])
    target = tmp_path / "out"
    counts = build_data.build_providers(source, target)
    assert counts == {"hospitals": 2}
    with (target / "hospitals.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert [r["id"] for r in rows] == ["100", "101"]
    assert rows[1]["name"] == "Groote Schuur Hospital"
