"""Validators for the South African reference data shipped with the package.

The checks enforce the project rules: names contain only letters, spaces and hyphens
(no digits or symbols), coordinates fall inside South Africa, provinces and codes are
consistent across files, and probability columns sum to one.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from synthea_za.config import DATA_DIR, PROVINCES

NAME_PATTERN = re.compile(r"^[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\- ]*$")
FACILITY_PATTERN = re.compile(r"^[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\- ]*$")
# South Africa's bounding box (including the Prince Edward Islands is unnecessary here)
LAT_RANGE = (-35.0, -22.0)
LON_RANGE = (16.0, 33.5)
PROVINCE_NAMES = {p.name for p in PROVINCES}
PROVINCE_CODES = {p.code for p in PROVINCES}

DEMOGRAPHICS_COLUMNS = (
    "ID,COUNTY,NAME,STNAME,POPESTIMATE2015,CTYNAME,TOT_POP,TOT_MALE,TOT_FEMALE,WHITE,HISPANIC,"
    "BLACK,ASIAN,NATIVE,OTHER,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,00..10,10..15,"
    "15..25,25..35,35..50,50..75,75..100,100..150,150..200,200..999,LESS_THAN_HS,HS_DEGREE,"
    "SOME_COLLEGE,BS_DEGREE").split(",")
AGE_COLUMNS = [str(i) for i in range(1, 19)]
INCOME_COLUMNS = ["00..10", "10..15", "15..25", "25..35", "35..50", "50..75", "75..100",
                  "100..150", "150..200", "200..999"]
EDUCATION_COLUMNS = ["LESS_THAN_HS", "HS_DEGREE", "SOME_COLLEGE", "BS_DEGREE"]
RACE_COLUMNS = ["WHITE", "BLACK", "ASIAN", "NATIVE", "OTHER"]
PROVIDER_COLUMNS = ["id", "name", "address", "city", "state", "zip", "phone", "ownership",
                    "emergency", "lat", "lon"]
REQUIRED_PROVIDER_FILES = {"hospitals.csv", "primary_care.csv", "urgent_care.csv"}


@dataclass
class Issue:
    level: str  # "error" or "warning"
    file: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper()}: {self.file}: {self.message}"


@dataclass
class ValidationResult:
    issues: List[Issue] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)

    def error(self, file: str, message: str) -> None:
        self.issues.append(Issue("error", file, message))

    def warning(self, file: str, message: str) -> None:
        self.issues.append(Issue("warning", file, message))

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _check_sum(result: ValidationResult, file: str, label: str, values: Iterable[str],
               tolerance: float = 0.01) -> None:
    numbers = []
    for value in values:
        if not _is_number(value):
            result.error(file, f"{label}: non-numeric value '{value}'")
            return
        numbers.append(float(value))
    if any(n < 0 for n in numbers):
        result.error(file, f"{label}: negative value")
    total = sum(numbers)
    if abs(total - 1.0) > tolerance:
        result.error(file, f"{label}: values sum to {total:.4f}, expected 1.0")


def _check_coordinates(result: ValidationResult, file: str, label: str, lat: str, lon: str) -> None:
    if not (_is_number(lat) and _is_number(lon)):
        result.error(file, f"{label}: non-numeric coordinates '{lat}', '{lon}'")
        return
    latitude, longitude = float(lat), float(lon)
    if not (LAT_RANGE[0] <= latitude <= LAT_RANGE[1]) or not (LON_RANGE[0] <= longitude <= LON_RANGE[1]):
        result.error(file, f"{label}: coordinates ({latitude}, {longitude}) are outside South Africa")


# ---------------------------------------------------------------------------
# names.yml
# ---------------------------------------------------------------------------

def _parse_simple_yaml_lists(text: str) -> Dict[str, Dict[str, object]]:
    """Parse the restricted YAML used by names.yml without a YAML dependency.

    Supports nested mappings (two space indentation) whose leaves are flow style lists
    ``[a, b, c]`` possibly continued over several lines.
    """
    root: Dict[str, object] = {}
    stack: List[tuple] = [(-1, root)]
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index]
        index += 1
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        content = raw.strip()
        if ":" not in content:
            raise ValueError(f"Cannot parse line: {raw!r}")
        key, _, rest = content.partition(":")
        key = key.strip()
        rest = rest.strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if rest == "":
            child: Dict[str, object] = {}
            parent[key] = child
            stack.append((indent, child))
        elif rest.startswith("["):
            buffer = rest
            while not buffer.rstrip().endswith("]"):
                if index >= len(lines):
                    raise ValueError(f"Unterminated list for key {key}")
                buffer += " " + lines[index].strip()
                index += 1
            inner = buffer.strip()[1:-1]
            items = [item.strip().strip("'\"") for item in inner.split(",")]
            parent[key] = [item for item in items if item]
        elif rest.startswith("{"):
            inner = rest.strip()[1:-1]
            child = {}
            for part in inner.split("]"):
                part = part.strip().strip(",").strip()
                if not part:
                    continue
                sub_key, _, sub_rest = part.partition(":")
                items = [i.strip().strip("'\"") for i in sub_rest.strip().lstrip("[").split(",")]
                child[sub_key.strip()] = [i for i in items if i]
            parent[key] = child
        else:
            parent[key] = rest
    return root  # type: ignore[return-value]


def _check_name_list(result: ValidationResult, file: str, label: str, names: object,
                     minimum: int) -> None:
    if not isinstance(names, list):
        result.error(file, f"{label}: expected a list")
        return
    seen: Set[str] = set()
    for name in names:
        if not NAME_PATTERN.match(name):
            result.error(file, f"{label}: '{name}' contains characters other than letters, spaces or hyphens")
        if name.lower() in seen:
            result.warning(file, f"{label}: duplicate name '{name}'")
        seen.add(name.lower())
    if len(names) < minimum:
        result.warning(file, f"{label}: only {len(names)} names, expected at least {minimum}")


def validate_names(path: Path, result: ValidationResult, minimum: int = 40,
                   require_english: bool = True) -> Set[str]:
    file = path.name
    if not path.is_file():
        result.error(file, "missing")
        return set()
    try:
        data = _parse_simple_yaml_lists(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        result.error(file, f"cannot parse: {exc}")
        return set()
    languages: Set[str] = set()
    for key, value in data.items():
        if key == "street":
            for sub in ("type", "secondary"):
                if require_english and sub not in value:  # type: ignore[operator]
                    result.error(file, f"street.{sub} is missing")
            for sub_key, sub_value in value.items():  # type: ignore[union-attr]
                _check_name_list(result, file, f"street.{sub_key}", sub_value, 1)
            continue
        if not isinstance(value, dict):
            result.error(file, f"{key}: expected a mapping of M/F/family lists")
            continue
        languages.add(key)
        for sub_key, sub_value in value.items():
            if sub_key in ("M", "F", "family"):
                _check_name_list(result, file, f"{key}.{sub_key}", sub_value, minimum)
            elif isinstance(sub_value, dict):
                for leaf_key, leaf in sub_value.items():
                    if leaf_key not in ("M", "F", "family"):
                        result.error(file, f"{key}.{sub_key}.{leaf_key}: unexpected key")
                    else:
                        _check_name_list(result, file, f"{key}.{sub_key}.{leaf_key}", leaf, minimum)
            else:
                result.error(file, f"{key}.{sub_key}: unexpected entry")
        for required in ("M", "F", "family"):
            if required not in value:
                result.error(file, f"{key}.{required} is missing")
    if require_english and "english" not in languages:
        result.error(file, "the english pool is required as the fallback")
    result.counts["name_pools"] = len(languages)
    return languages


# ---------------------------------------------------------------------------
# languages.json and language_lookup.json
# ---------------------------------------------------------------------------

def validate_languages(data_dir: Path, result: ValidationResult, name_pools: Set[str]) -> None:
    languages_file = data_dir / "languages.json"
    lookup_file = data_dir / "language_lookup.json"
    used: Set[str] = set()
    if languages_file.is_file():
        data = json.loads(languages_file.read_text(encoding="utf-8"))
        blocks = []
        default = {k: v for k, v in data.items() if k not in ("by_state", "default")}
        default.update(data.get("default", {}))
        blocks.append(("default", default))
        for state, races in data.get("by_state", {}).items():
            if state not in PROVINCE_NAMES:
                result.error(languages_file.name, f"by_state key '{state}' is not a province name")
            blocks.append((state, races))
        for label, races in blocks:
            for race, weights in races.items():
                if race not in ("white", "black", "asian", "native", "other", "hawaiian", "hispanic"):
                    result.error(languages_file.name, f"{label}.{race}: unknown race key")
                total = sum(float(w) for w in weights.values())
                if abs(total - 1.0) > 0.01:
                    result.error(languages_file.name, f"{label}.{race}: weights sum to {total:.3f}")
                used.update(weights.keys())
    else:
        result.error(languages_file.name, "missing")
    for language in sorted(used):
        if language not in name_pools:
            result.warning(languages_file.name,
                           f"language '{language}' has no name pool in names.yml (english fallback)")
    if lookup_file.is_file():
        lookup = json.loads(lookup_file.read_text(encoding="utf-8"))
        for language in sorted(used):
            if language not in lookup:
                result.error(lookup_file.name, f"language '{language}' has no BCP 47 entry")
        for language, entry in lookup.items():
            for key in ("code", "system", "display"):
                if key not in entry:
                    result.error(lookup_file.name, f"{language}: missing '{key}'")
    else:
        result.error(lookup_file.name, "missing")


# ---------------------------------------------------------------------------
# geography
# ---------------------------------------------------------------------------

def check_demographics_csv(path: Path, result: ValidationResult,
                           expected_province: Optional[str] = None) -> Dict[str, Set[str]]:
    """Validate one demographics CSV; returns towns per province."""
    towns: Dict[str, Set[str]] = {}
    file = path.name
    if not path.is_file():
        result.error(file, "missing")
        return towns
    rows = _read_csv(path)
    header = list(rows[0].keys()) if rows else []
    missing = [c for c in DEMOGRAPHICS_COLUMNS if c not in header]
    for column in missing:
        result.error(file, f"missing column {column}")
    if missing or not rows:
        if not rows:
            result.error(file, "no rows")
        return towns
    ids: Set[str] = set()
    names: Set[str] = set()
    for row in rows:
        label = f"{row['NAME']} ({row['STNAME']})"
        if row["STNAME"] not in PROVINCE_NAMES:
            result.error(file, f"{label}: unknown province '{row['STNAME']}'")
        if expected_province and row["STNAME"] != expected_province:
            result.error(file, f"{label}: expected province {expected_province}")
        if not NAME_PATTERN.match(row["NAME"]):
            result.error(file, f"{label}: town name contains digits or symbols")
        if not NAME_PATTERN.match(row["CTYNAME"]):
            result.error(file, f"{label}: district name '{row['CTYNAME']}' contains digits or symbols")
        if row["ID"] in ids:
            result.error(file, f"{label}: duplicate ID {row['ID']}")
        ids.add(row["ID"])
        key = (row["STNAME"], row["NAME"].lower())
        if key in names:
            result.error(file, f"{label}: duplicate town name within the province")
        names.add(key)
        if not row["POPESTIMATE2015"].isdigit() or int(row["POPESTIMATE2015"]) <= 0:
            result.error(file, f"{label}: population must be a positive integer")
        if row["TOT_POP"] != row["POPESTIMATE2015"]:
            result.warning(file, f"{label}: TOT_POP differs from POPESTIMATE2015")
        _check_sum(result, file, f"{label} sex", [row["TOT_MALE"], row["TOT_FEMALE"]])
        _check_sum(result, file, f"{label} population group", [row[c] for c in RACE_COLUMNS])
        if not _is_number(row["HISPANIC"]) or float(row["HISPANIC"]) != 0.0:
            result.error(file, f"{label}: HISPANIC must be 0 for South Africa")
        if _is_number(row["NATIVE"]) and float(row["NATIVE"]) != 0.0:
            result.warning(file, f"{label}: NATIVE is normally 0 for South Africa")
        _check_sum(result, file, f"{label} ages", [row[c] for c in AGE_COLUMNS])
        _check_sum(result, file, f"{label} income", [row[c] for c in INCOME_COLUMNS])
        _check_sum(result, file, f"{label} education", [row[c] for c in EDUCATION_COLUMNS])
        towns.setdefault(row["STNAME"], set()).add(row["NAME"])
    result.counts["towns"] = result.counts.get("towns", 0) + len(rows)
    return towns


def check_zipcodes_csv(path: Path, result: ValidationResult,
                       expected_province: Optional[str] = None) -> Dict[str, Set[str]]:
    """Validate one postal code CSV; returns towns per province."""
    covered: Dict[str, Set[str]] = {}
    file = path.name
    if not path.is_file():
        result.error(file, "missing")
        return covered
    rows = _read_csv(path)
    header = list(rows[0].keys()) if rows else []
    for column in ("USPS", "ST", "NAME", "ZCTA5", "LAT", "LON"):
        if column not in header:
            result.error(file, f"missing column {column}")
            return covered
    seen: Set[tuple] = set()
    for row in rows:
        label = f"{row.get('NAME')} ({row.get('USPS')})"
        if row.get("USPS") not in PROVINCE_NAMES:
            result.error(file, f"{label}: unknown province")
        if expected_province and row.get("USPS") != expected_province:
            result.error(file, f"{label}: expected province {expected_province}")
        code_for_province = {p.name: p.code for p in PROVINCES}.get(row.get("USPS", ""))
        if row.get("ST") != code_for_province:
            result.error(file, f"{label}: province code '{row.get('ST')}' does not match {row.get('USPS')}")
        if not NAME_PATTERN.match(row.get("NAME", "")):
            result.error(file, f"{label}: town name contains digits or symbols")
        code = row.get("ZCTA5", "")
        if not re.fullmatch(r"\d{4}", code):
            result.error(file, f"{label}: postal code '{code}' must be four digits")
        key = (row.get("USPS"), row.get("NAME"), code)
        if key in seen:
            result.error(file, f"{label}: duplicate postal code entry {code}")
        seen.add(key)
        _check_coordinates(result, file, label, row.get("LAT", ""), row.get("LON", ""))
        covered.setdefault(row.get("USPS", ""), set()).add(row.get("NAME", ""))
    result.counts["postal_codes"] = result.counts.get("postal_codes", 0) + len(rows)
    return covered


def check_sdoh_csv(path: Path, result: ValidationResult) -> Set[str]:
    """Validate a social determinants CSV; returns district names."""
    districts: Set[str] = set()
    if not path.is_file():
        result.warning(path.name, "missing (Synthea will use average social determinants)")
        return districts
    for row in _read_csv(path):
        if row.get("STATE") not in PROVINCE_NAMES:
            result.error(path.name, f"unknown province '{row.get('STATE')}'")
        if not NAME_PATTERN.match(row.get("COUNTY", "")):
            result.error(path.name, f"district '{row.get('COUNTY')}' contains digits or symbols")
        for column in ("FOOD_INSECURITY", "SEVERE_HOUSING_COST_BURDEN", "UNEMPLOYED",
                       "NO_VEHICLE_ACCESS", "UNINSURED"):
            value = row.get(column, "")
            if not _is_number(value) or not 0 <= float(value) <= 1:
                result.error(path.name, f"{row.get('COUNTY')}: {column} must be between 0 and 1")
        districts.add(row.get("COUNTY", ""))
    return districts


def check_towns_have_postal_codes(result: ValidationResult, file: str, towns: Dict[str, Set[str]],
                                  covered: Dict[str, Set[str]]) -> None:
    for province, names in towns.items():
        for name in sorted(names - covered.get(province, set())):
            result.error(file, f"{name} ({province}) has no postal code entry")


def validate_geography(data_dir: Path, result: ValidationResult) -> None:
    geo = data_dir / "geography"
    towns = check_demographics_csv(geo / "demographics.csv", result)
    for province in PROVINCES:
        if towns and province.name not in towns:
            result.error("demographics.csv", f"no towns for {province.name}")
    covered = check_zipcodes_csv(geo / "zipcodes.csv", result)
    check_towns_have_postal_codes(result, "zipcodes.csv", towns, covered)

    timezones = geo / "timezones.csv"
    if timezones.is_file():
        found = {row.get("STATE") for row in _read_csv(timezones)}
        for province in PROVINCES:
            if province.name not in found:
                result.error(timezones.name, f"missing {province.name}")
    else:
        result.error(timezones.name, "missing")

    districts = check_sdoh_csv(geo / "sdoh.csv", result)
    if districts and (geo / "demographics.csv").is_file():
        for row in _read_csv(geo / "demographics.csv"):
            if row.get("CTYNAME") and row["CTYNAME"] not in districts:
                result.warning("sdoh.csv", f"district '{row['CTYNAME']}' ({row.get('STNAME')}) has no social determinants row")
                districts.add(row["CTYNAME"])  # report each district once
    for required in ("fipscodes.csv", "foreign_birthplace.json"):
        if not (geo / required).is_file():
            result.error(required, "missing")


# ---------------------------------------------------------------------------
# providers and payers
# ---------------------------------------------------------------------------

def check_providers_csv(path: Path, result: ValidationResult, ids: Optional[Set[str]] = None,
                        expected_province: Optional[str] = None,
                        known_towns: Optional[Dict[str, Set[str]]] = None) -> Dict[str, int]:
    """Validate one provider CSV; returns facility counts per province."""
    counts: Dict[str, int] = {}
    ids = ids if ids is not None else set()
    if not path.is_file():
        result.error(path.name, "missing")
        return counts
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        rows = list(reader)
    missing = [c for c in PROVIDER_COLUMNS if c not in header]
    for column in missing:
        result.error(path.name, f"missing column {column}")
    if missing or not rows:
        if not rows and not missing:
            if path.name in REQUIRED_PROVIDER_FILES:
                result.error(path.name, "no rows")
            else:
                # optional kinds (e.g. veterans.csv) may be header-only so that Synthea
                # loads nothing for them
                result.counts.setdefault("empty_provider_files", 0)
                result.counts["empty_provider_files"] += 1
        return counts
    for row in rows:
        label = f"{row['name']} ({row['city']})"
        if row["id"] in ids:
            result.error(path.name, f"{label}: duplicate id {row['id']}")
        ids.add(row["id"])
        if not FACILITY_PATTERN.match(row["name"]):
            result.error(path.name, f"{label}: facility name contains digits or symbols")
        if not NAME_PATTERN.match(row["city"]):
            result.error(path.name, f"{label}: town name contains digits or symbols")
        if row["state"] not in PROVINCE_NAMES:
            result.error(path.name, f"{label}: unknown province '{row['state']}'")
        if expected_province and row["state"] != expected_province:
            result.error(path.name, f"{label}: expected province {expected_province}")
        if known_towns is not None and row["city"] not in known_towns.get(row["state"], set()):
            result.warning(path.name, f"{label}: town '{row['city']}' is not in the demographics file")
        if not re.fullmatch(r"\d{4}", row["zip"]):
            result.error(path.name, f"{label}: postal code '{row['zip']}' must be four digits")
        if row["ownership"] not in ("Government", "Private", "Non-profit"):
            result.warning(path.name, f"{label}: ownership '{row['ownership']}' is unusual")
        if row["emergency"] not in ("Yes", "No"):
            result.error(path.name, f"{label}: emergency must be Yes or No")
        _check_coordinates(result, path.name, label, row["lat"], row["lon"])
        if not re.fullmatch(r"0\d{2} \d{3} \d{4}|0800 \d{3} \d{3}|0860 \d{3} \d{3}|0861 \d{3} \d{3}", row["phone"]):
            result.warning(path.name, f"{label}: phone '{row['phone']}' is not in 0XX XXX XXXX format")
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    result.counts["facilities"] = result.counts.get("facilities", 0) + len(rows)
    return counts


def validate_providers(data_dir: Path, result: ValidationResult,
                       known_towns: Optional[Dict[str, Set[str]]] = None) -> None:
    providers = data_dir / "providers"
    if not providers.is_dir():
        result.error("providers", "missing directory")
        return
    present = {p.name for p in providers.glob("*.csv")}
    for name in sorted(REQUIRED_PROVIDER_FILES - present):
        result.error(name, "missing provider file")
    ids: Set[str] = set()
    per_kind: Dict[str, Dict[str, int]] = {}
    for path in sorted(providers.glob("*.csv")):
        per_kind[path.stem] = check_providers_csv(path, result, ids, known_towns=known_towns)
    for kind in ("hospitals", "primary_care", "urgent_care"):
        for province in PROVINCES:
            if per_kind.get(kind, {}).get(province.name, 0) == 0:
                result.error(f"{kind}.csv", f"no facilities in {province.name}")


def validate_payers(data_dir: Path, result: ValidationResult) -> None:
    payers = data_dir / "payers"
    companies = payers / "insurance_companies.csv"
    plans = payers / "insurance_plans.csv"
    eligibilities = payers / "insurance_eligibilities.csv"
    missing = [path for path in (companies, plans, eligibilities) if not path.is_file()]
    for path in missing:
        result.error(path.name, "missing")
    if missing:
        return
    company_rows = _read_csv(companies)
    company_ids = set()
    for row in company_rows:
        if row["Ownership"] not in ("Government", "Private"):
            result.error(companies.name, f"{row['Name']}: ownership must be Government or Private")
        if not NAME_PATTERN.match(row["Name"]):
            result.error(companies.name, f"payer name '{row['Name']}' contains digits or symbols")
        company_ids.add(row["Id"].strip())
    policies = {row["Name"].strip() for row in _read_csv(eligibilities)} | {"Generic"}
    has_government_plan = False
    for row in _read_csv(plans):
        if row["Payer Id"].strip() not in company_ids:
            result.error(plans.name, f"plan {row['Plan Id']} references unknown payer {row['Payer Id']}")
        if row["Eligibility Policy"].strip() not in policies:
            result.error(plans.name, f"plan {row['Plan Id']}: unknown eligibility policy '{row['Eligibility Policy']}'")
        company = next((c for c in company_rows if c["Id"].strip() == row["Payer Id"].strip()), None)
        if company and company["Ownership"] == "Government":
            has_government_plan = True
    if not has_government_plan:
        result.error(plans.name, "at least one government plan is required for public sector care")
    result.counts["payers"] = len(company_rows)


def validate_data_dir(data_dir: Path = DATA_DIR) -> ValidationResult:
    result = ValidationResult()
    pools = validate_names(data_dir / "names.yml", result)
    validate_languages(data_dir, result, pools)
    validate_geography(data_dir, result)
    towns = check_demographics_csv(data_dir / "geography" / "demographics.csv", ValidationResult())
    validate_providers(data_dir, result, known_towns=towns)
    validate_payers(data_dir, result)
    for required in ("synthea_za.properties",):
        if not (data_dir / required).is_file():
            result.error(required, "missing")
    return result


PART_KINDS = ("names", "demographics", "zipcodes", "sdoh", "providers")


def validate_part(kind: str, path: Path, province: Optional[str] = None) -> ValidationResult:
    """Validate a single source file of the given kind (used while authoring data)."""
    result = ValidationResult()
    if kind == "names":
        validate_names(path, result, require_english=False)
    elif kind == "demographics":
        check_demographics_csv(path, result, expected_province=province)
    elif kind == "zipcodes":
        check_zipcodes_csv(path, result, expected_province=province)
    elif kind == "sdoh":
        check_sdoh_csv(path, result)
    elif kind == "providers":
        # when the file follows the data_src layout (<CODE>_<kind>.csv next to a geography
        # folder) the province's postal code file supplies the known town names
        known_towns = None
        code = path.name.split("_", 1)[0]
        zipcodes = path.parent.parent / "geography" / f"{code}_zipcodes.csv"
        if zipcodes.is_file():
            known_towns = check_zipcodes_csv(zipcodes, ValidationResult())
        check_providers_csv(path, result, expected_province=province, known_towns=known_towns)
    else:
        result.error(str(path), f"unknown part kind '{kind}' (expected one of {', '.join(PART_KINDS)})")
    return result
