"""Configuration objects and reference tables for the generator."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
PROJECT_DIR = PACKAGE_DIR.parent
# The synthea-za project lives inside a Synthea checkout; the Gradle build is one level up.
SYNTHEA_ROOT = PROJECT_DIR.parent
DEFAULT_JAR = SYNTHEA_ROOT / "build" / "libs" / "synthea-with-dependencies.jar"


@dataclass(frozen=True)
class Province:
    """A South African province as used in the geography files."""

    name: str
    code: str
    population: int  # Census 2022 count, used to allocate patients across provinces


# Statistics South Africa, Census 2022 provincial population counts.
PROVINCES: List[Province] = [
    Province("Gauteng", "GP", 15_099_422),
    Province("KwaZulu-Natal", "KZN", 12_423_907),
    Province("Western Cape", "WC", 7_433_020),
    Province("Eastern Cape", "EC", 7_230_204),
    Province("Limpopo", "LP", 6_572_721),
    Province("Mpumalanga", "MP", 5_143_324),
    Province("North West", "NW", 3_804_548),
    Province("Free State", "FS", 2_964_412),
    Province("Northern Cape", "NC", 1_355_629),
]
PROVINCE_BY_NAME: Dict[str, Province] = {p.name.lower(): p for p in PROVINCES}
PROVINCE_BY_CODE: Dict[str, Province] = {p.code.lower(): p for p in PROVINCES}


def find_province(value: str) -> Province:
    """Resolve a province from its name or code, case insensitively."""
    key = value.strip().lower()
    if key in PROVINCE_BY_NAME:
        return PROVINCE_BY_NAME[key]
    if key in PROVINCE_BY_CODE:
        return PROVINCE_BY_CODE[key]
    # tolerate spelling variants such as "kwazulu natal" or "northwest"
    squashed = key.replace("-", "").replace(" ", "")
    for province in PROVINCES:
        if province.name.lower().replace("-", "").replace(" ", "") == squashed:
            return province
    raise ValueError(
        f"Unknown province '{value}'. Known provinces: "
        + ", ".join(f"{p.name} ({p.code})" for p in PROVINCES)
    )


def allocate_patients(total: int, provinces: Optional[List[Province]] = None) -> Dict[str, int]:
    """Split a patient count across provinces in proportion to population.

    Uses the largest remainder method so the allocation always sums to ``total``.
    Provinces that receive zero patients are omitted from the result.
    """
    provinces = provinces or PROVINCES
    if total <= 0:
        return {}
    population = sum(p.population for p in provinces)
    quotas = {p.name: total * p.population / population for p in provinces}
    allocation = {name: int(q) for name, q in quotas.items()}
    remaining = total - sum(allocation.values())
    for name, _ in sorted(quotas.items(), key=lambda kv: kv[1] - int(kv[1]), reverse=True):
        if remaining <= 0:
            break
        allocation[name] += 1
        remaining -= 1
    return {name: count for name, count in allocation.items() if count > 0}


@dataclass
class PostProcessOptions:
    """Switches for the FHIR bundle post-processing step."""

    national_id: bool = True
    national_id_system: str = "http://www.dha.gov.za/identity-number"
    passport_system: str = "http://hl7.org/fhir/sid/passport-ZAF"
    practitioner_system: str = "http://www.hpcsa.co.za/registration-number"
    mrn_system: Optional[str] = None  # None keeps Synthea's default MRN system
    phones: bool = True
    currency: Optional[str] = "ZAR"
    zar_per_usd: float = 18.0
    si_units: bool = True
    drop_drivers_licence: bool = True
    meta_tag: Optional[str] = None


@dataclass
class GenerationConfig:
    """Everything needed for one ``generate`` run."""

    patients: int
    output_dir: Path
    seed: int = 1
    clinician_seed: Optional[int] = None
    provinces: List[Province] = field(default_factory=lambda: list(PROVINCES))
    city: Optional[str] = None
    years_of_history: int = 10
    reference_date: Optional[str] = None  # YYYYMMDD, defaults to today inside Synthea
    end_date: Optional[str] = None
    age_range: Optional[str] = None  # e.g. "18-65"
    gender: Optional[str] = None  # "M" or "F"
    only_alive: bool = False
    jar: Path = DEFAULT_JAR
    java: str = os.environ.get("JAVA", "java")
    java_opts: List[str] = field(default_factory=list)
    build_if_missing: bool = True
    keep_raw: bool = False
    jobs: int = 1
    clinical_notes: bool = False
    csv_export: bool = False
    extra_properties: Dict[str, str] = field(default_factory=dict)
    synthea_args: List[str] = field(default_factory=list)
    postprocess: PostProcessOptions = field(default_factory=PostProcessOptions)
    work_dir: Optional[Path] = None

    @property
    def raw_dir(self) -> Path:
        return (self.work_dir or (self.output_dir / ".work")) / "raw"

    @property
    def overlay_dir(self) -> Path:
        return (self.work_dir or (self.output_dir / ".work")) / "overlay"
