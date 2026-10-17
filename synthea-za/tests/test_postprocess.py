import copy
import json

from synthea_za.config import PostProcessOptions
from synthea_za.postprocess import PostProcessStats, transform_bundle
from synthea_za.sa_id import luhn_valid

V2 = "http://terminology.hl7.org/CodeSystem/v2-0203"


def make_bundle():
    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {"resource": {
                "resourceType": "Patient", "id": "p1", "gender": "female", "birthDate": "1975-03-04",
                "extension": [{"url": "http://hl7.org/fhir/StructureDefinition/patient-birthPlace",
                               "valueAddress": {"city": "Soweto", "state": "Gauteng", "country": "ZA"}}],
                "identifier": [
                    {"system": "https://github.com/synthetichealth/synthea", "value": "p1"},
                    {"type": {"coding": [{"system": V2, "code": "MR"}]}, "system": "http://hospital.smarthealthit.org", "value": "p1"},
                    {"type": {"coding": [{"system": V2, "code": "SS"}]}, "system": "http://hl7.org/fhir/sid/us-ssn", "value": "999-12-3456"},
                    {"type": {"coding": [{"system": V2, "code": "DL"}]}, "system": "urn:oid:2.16.840.1.113883.4.3.25", "value": "S99912345"},
                    {"type": {"coding": [{"system": V2, "code": "PPN"}]}, "system": "http://hl7.org/fhir/sid/passport-ZAF", "value": "X12345678X"},
                ],
                "telecom": [{"system": "phone", "value": "555-123-4567", "use": "home"}],
            }},
            {"resource": {"resourceType": "Observation", "id": "o1",
                          "code": {"coding": [{"system": "http://loinc.org", "code": "2339-0"}]},
                          "valueQuantity": {"value": 90.0, "unit": "mg/dL", "system": "http://unitsofmeasure.org", "code": "mg/dL"}}},
            {"resource": {"resourceType": "Observation", "id": "o2",
                          "code": {"coding": [{"system": "http://loinc.org", "code": "8302-2"}]},
                          "valueQuantity": {"value": 170.0, "unit": "cm", "code": "cm"}}},
            {"resource": {"resourceType": "Claim", "id": "c1", "total": {"value": 100.0, "currency": "USD"},
                          "item": [{"net": {"value": 10.5, "currency": "USD"}}]}},
            {"resource": {"resourceType": "Practitioner", "id": "pr1",
                          "identifier": [{"system": "http://hl7.org/fhir/sid/us-npi", "value": "9999999896"}]}},
        ],
    }


def test_transform_bundle_rewrites_identifiers_phones_money_and_units():
    bundle = make_bundle()
    stats = PostProcessStats()
    transform_bundle(bundle, PostProcessOptions(), set(), stats)
    patient = bundle["entry"][0]["resource"]
    codes = [c["code"] for i in patient["identifier"] for c in i.get("type", {}).get("coding", [])]
    assert "SS" not in codes and "DL" not in codes
    assert codes.index("MR") + 1 == codes.index("NNZAF")
    national = next(i for i in patient["identifier"] if "NNZAF" in str(i))
    assert national["value"].startswith("750304") and luhn_valid(national["value"])
    assert int(national["value"][6:10]) < 5000  # female
    passport = next(i for i in patient["identifier"] if "PPN" in str(i))
    assert passport["value"][0] == "A" and passport["value"][1:].isdigit()
    assert patient["telecom"][0]["value"].startswith("0") and " " in patient["telecom"][0]["value"]
    glucose = bundle["entry"][1]["resource"]["valueQuantity"]
    assert glucose["unit"] == "mmol/L" and glucose["value"] == 5.0
    height = bundle["entry"][2]["resource"]["valueQuantity"]
    assert height["unit"] == "cm" and height["value"] == 170.0
    claim = bundle["entry"][3]["resource"]
    assert claim["total"] == {"value": 1800.0, "currency": "ZAR"}
    assert claim["item"][0]["net"]["currency"] == "ZAR"
    practitioner = bundle["entry"][4]["resource"]
    assert practitioner["identifier"][0]["system"].startswith("http://www.hpcsa.co.za")
    assert practitioner["identifier"][0]["value"].startswith("MP ")
    assert stats.patients == 1 and stats.money_converted == 2 and stats.observations_converted == 1


def test_transform_is_idempotent_and_options_can_disable_steps():
    bundle = make_bundle()
    stats = PostProcessStats()
    transform_bundle(bundle, PostProcessOptions(), set(), stats)
    first = copy.deepcopy(bundle)
    transform_bundle(bundle, PostProcessOptions(), set(), PostProcessStats())
    assert json.dumps(first, sort_keys=True) == json.dumps(bundle, sort_keys=True)

    untouched = make_bundle()
    options = PostProcessOptions(national_id=False, drop_drivers_licence=False, phones=False,
                                 currency=None, si_units=False)
    transform_bundle(untouched, options, set(), PostProcessStats())
    patient = untouched["entry"][0]["resource"]
    assert any("us-ssn" in i.get("system", "") for i in patient["identifier"])
    assert patient["telecom"][0]["value"] == "555-123-4567"
    assert untouched["entry"][3]["resource"]["total"]["currency"] == "USD"
    assert untouched["entry"][1]["resource"]["valueQuantity"]["unit"] == "mg/dL"


def test_meta_tag_is_added_once():
    bundle = make_bundle()
    options = PostProcessOptions(meta_tag="synthetic")
    transform_bundle(bundle, options, set(), PostProcessStats())
    transform_bundle(bundle, options, set(), PostProcessStats())
    tags = bundle["entry"][0]["resource"]["meta"]["tag"]
    assert len(tags) == 1 and tags[0]["code"] == "synthetic"


def test_died_before_filter(tmp_path):
    from datetime import date
    from synthea_za.postprocess import died_before, process_files
    bundle = make_bundle()
    assert not died_before(bundle, date(2016, 1, 1))
    bundle["entry"][0]["resource"]["deceasedDateTime"] = "2001-05-06T10:00:00+02:00"
    assert died_before(bundle, date(2016, 1, 1))
    assert not died_before(bundle, date(2000, 1, 1))
    source = tmp_path / "old.json"
    source.write_text(json.dumps(bundle))
    target = tmp_path / "out" / "old.json"
    stats = process_files([(source, target)], PostProcessOptions(), set(), None,
                          skip=lambda b: died_before(b, date(2016, 1, 1)))
    assert stats.skipped_deceased == 1 and not target.exists()
