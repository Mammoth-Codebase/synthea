"""Rewrite Synthea's FHIR R4 output so it reads as South African data.

The generator already produces South African names, addresses, providers and payers.
This step handles what Synthea hard codes for the United States:

* the Social Security Number becomes a valid South African identity number,
* the Massachusetts driver's licence identifier is removed,
* passports use the South African format,
* practitioner NPI identifiers become HPCSA style registration numbers,
* telephone numbers use South African mobile prefixes,
* money is converted from USD to ZAR,
* common chemistry results are converted to SI units.

All rewriting is deterministic for a given input so re-running the step is idempotent.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from synthea_za.config import PostProcessOptions
from synthea_za.sa_id import (hpcsa_registration, south_african_id, south_african_mobile,
                              south_african_passport)
from synthea_za.units import convert_quantity

V2_0203 = "http://terminology.hl7.org/CodeSystem/v2-0203"
US_SSN_SYSTEM = "http://hl7.org/fhir/sid/us-ssn"
US_NPI_SYSTEM = "http://hl7.org/fhir/sid/us-npi"
MA_DRIVERS_LICENCE_SYSTEM = "urn:oid:2.16.840.1.113883.4.3.25"
SYNTHEA_MRN_SYSTEM = "http://hospital.smarthealthit.org"
BIRTHPLACE_EXTENSION = "http://hl7.org/fhir/StructureDefinition/patient-birthPlace"
US_PHONE = re.compile(r"^\(?\d{3}\)?[- ]?\d{3}-\d{4}$")


@dataclass
class PostProcessStats:
    bundles: int = 0
    patients: int = 0
    identifiers_rewritten: int = 0
    phones_rewritten: int = 0
    money_converted: int = 0
    observations_converted: int = 0
    practitioners_rewritten: int = 0
    files: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "bundles": self.bundles,
            "patients": self.patients,
            "identifiers_rewritten": self.identifiers_rewritten,
            "phones_rewritten": self.phones_rewritten,
            "money_converted": self.money_converted,
            "observations_converted": self.observations_converted,
            "practitioners_rewritten": self.practitioners_rewritten,
        }


def _identifier(system: str, value: str, code: str, display: str) -> Dict[str, Any]:
    return {
        "type": {"coding": [{"system": V2_0203, "code": code, "display": display}],
                 "text": display},
        "system": system,
        "value": value,
    }


def _patient_birth_country(patient: Dict[str, Any]) -> Optional[str]:
    for extension in patient.get("extension", []):
        if extension.get("url") == BIRTHPLACE_EXTENSION:
            return extension.get("valueAddress", {}).get("country")
    return None


def rewrite_patient_identifiers(patient: Dict[str, Any], options: PostProcessOptions,
                                used_ids: Set[str], stats: PostProcessStats) -> None:
    identifiers: List[Dict[str, Any]] = patient.get("identifier", [])
    patient_id = patient.get("id", "")
    kept: List[Dict[str, Any]] = []
    has_national_id = False
    for identifier in identifiers:
        system = identifier.get("system", "")
        codes = {c.get("code") for c in identifier.get("type", {}).get("coding", [])}
        if "NNZAF" in codes:
            has_national_id = True  # already processed: keep as is
            used_ids.add(str(identifier.get("value", "")))
        if system == US_SSN_SYSTEM or "SS" in codes:
            continue  # replaced by the national identity number below
        if options.drop_drivers_licence and (system == MA_DRIVERS_LICENCE_SYSTEM or "DL" in codes):
            continue
        if "PPN" in codes:
            identifier["system"] = options.passport_system
            identifier["value"] = south_african_passport(patient_id)
            stats.identifiers_rewritten += 1
        if options.mrn_system and (system == SYNTHEA_MRN_SYSTEM or "MR" in codes):
            identifier["system"] = options.mrn_system
        kept.append(identifier)

    if options.national_id and not has_national_id and patient.get("birthDate"):
        birth = date.fromisoformat(patient["birthDate"][:10])
        gender = patient.get("gender", "unknown")
        citizen = (_patient_birth_country(patient) or "ZA") == "ZA"
        national_id = south_african_id(birth, gender, patient_id, citizen=citizen, used=used_ids)
        national = _identifier(options.national_id_system, national_id, "NNZAF",
                               "National Person Identifier (South Africa)")
        national["use"] = "official"
        # place it directly after the medical record number
        insert_at = 0
        for index, identifier in enumerate(kept):
            codes = {c.get("code") for c in identifier.get("type", {}).get("coding", [])}
            if "MR" in codes:
                insert_at = index + 1
        kept.insert(insert_at, national)
        stats.identifiers_rewritten += 1
    patient["identifier"] = kept


def rewrite_telecoms(resource: Dict[str, Any], seed: str, stats: PostProcessStats) -> None:
    for index, telecom in enumerate(resource.get("telecom", [])):
        if telecom.get("system") == "phone" and US_PHONE.match(str(telecom.get("value", ""))):
            telecom["value"] = south_african_mobile(f"{seed}:{index}")
            stats.phones_rewritten += 1


def rewrite_practitioner(resource: Dict[str, Any], options: PostProcessOptions,
                         stats: PostProcessStats) -> None:
    changed = False
    for identifier in resource.get("identifier", []):
        if identifier.get("system") == US_NPI_SYSTEM:
            identifier["system"] = options.practitioner_system
            identifier["value"] = hpcsa_registration(str(identifier.get("value", resource.get("id"))))
            identifier["type"] = {
                "coding": [{"system": V2_0203, "code": "PRN", "display": "Provider number"}],
                "text": "HPCSA registration number",
            }
            changed = True
    if changed:
        stats.practitioners_rewritten += 1


def convert_money(node: Any, options: PostProcessOptions, stats: PostProcessStats) -> None:
    """Recursively convert every Money element from USD to the configured currency."""
    if isinstance(node, dict):
        if node.get("currency") == "USD" and "value" in node and options.currency:
            node["value"] = round(float(node["value"]) * options.zar_per_usd, 2)
            node["currency"] = options.currency
            stats.money_converted += 1
        for value in node.values():
            convert_money(value, options, stats)
    elif isinstance(node, list):
        for value in node:
            convert_money(value, options, stats)


def _loinc_code(codeable: Dict[str, Any]) -> Optional[str]:
    for coding in codeable.get("coding", []):
        if coding.get("system") == "http://loinc.org":
            return coding.get("code")
    return None


def _convert_quantity_in_place(code: Optional[str], quantity: Dict[str, Any]) -> bool:
    if code is None or "value" not in quantity:
        return False
    unit = quantity.get("unit") or quantity.get("code")
    converted = convert_quantity(code, float(quantity["value"]), str(unit))
    if converted is None:
        return False
    value, target_unit = converted
    quantity["value"] = value
    quantity["unit"] = target_unit
    if "code" in quantity:
        quantity["code"] = target_unit
    return True


def convert_observation_units(observation: Dict[str, Any], stats: PostProcessStats) -> None:
    code = _loinc_code(observation.get("code", {}))
    if "valueQuantity" in observation and _convert_quantity_in_place(code, observation["valueQuantity"]):
        stats.observations_converted += 1
    for component in observation.get("component", []):
        component_code = _loinc_code(component.get("code", {}))
        if "valueQuantity" in component and _convert_quantity_in_place(component_code, component["valueQuantity"]):
            stats.observations_converted += 1
    for rng in observation.get("referenceRange", []):
        for bound in ("low", "high"):
            if bound in rng:
                _convert_quantity_in_place(code, rng[bound])


def add_meta_tag(resource: Dict[str, Any], tag: str) -> None:
    meta = resource.setdefault("meta", {})
    tags = meta.setdefault("tag", [])
    if not any(t.get("code") == tag for t in tags):
        tags.append({"system": "https://github.com/synthetichealth/synthea", "code": tag,
                     "display": "Synthetic data generated by synthea-za"})


def transform_bundle(bundle: Dict[str, Any], options: PostProcessOptions,
                     used_ids: Set[str], stats: PostProcessStats) -> Dict[str, Any]:
    stats.bundles += 1
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        resource_type = resource.get("resourceType")
        seed = f"{resource_type}:{resource.get('id', '')}"
        if resource_type == "Patient":
            stats.patients += 1
            if options.national_id or options.drop_drivers_licence:
                rewrite_patient_identifiers(resource, options, used_ids, stats)
            if options.phones:
                rewrite_telecoms(resource, seed, stats)
        elif resource_type == "Practitioner":
            rewrite_practitioner(resource, options, stats)
            if options.phones:
                rewrite_telecoms(resource, seed, stats)
        elif resource_type in ("Organization", "Location", "RelatedPerson"):
            if options.phones:
                rewrite_telecoms(resource, seed, stats)
        elif resource_type == "Observation" and options.si_units:
            convert_observation_units(resource, stats)
        if options.meta_tag:
            add_meta_tag(resource, options.meta_tag)
    if options.currency:
        convert_money(bundle, options, stats)
    return bundle


def is_patient_bundle(path: Path) -> bool:
    name = path.name
    return not (name.startswith("hospitalInformation") or name.startswith("practitionerInformation"))


def process_files(files: Iterable[Tuple[Path, Path]], options: PostProcessOptions,
                  used_ids: Optional[Set[str]] = None,
                  stats: Optional[PostProcessStats] = None) -> PostProcessStats:
    """Transform each ``(source, target)`` pair of bundle files."""
    stats = stats or PostProcessStats()
    used_ids = used_ids if used_ids is not None else set()
    for source, target in files:
        with source.open("r", encoding="utf-8") as handle:
            bundle = json.load(handle)
        if bundle.get("resourceType") == "Bundle":
            transform_bundle(bundle, options, used_ids, stats)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            json.dump(bundle, handle, indent=2, ensure_ascii=False)
        stats.files.append(str(target))
    return stats


def process_directory(raw_fhir_dir: Path, out_fhir_dir: Path, options: PostProcessOptions,
                      label: Optional[str] = None, used_ids: Optional[Set[str]] = None,
                      stats: Optional[PostProcessStats] = None) -> PostProcessStats:
    """Transform every bundle under ``raw_fhir_dir`` into ``out_fhir_dir``.

    Organisation and practitioner bundles are renamed with ``label`` (normally the
    province code) so that several provincial runs can share one output folder.
    """
    pairs: List[Tuple[Path, Path]] = []
    for source in sorted(raw_fhir_dir.glob("*.json")):
        name = source.name
        if not is_patient_bundle(source) and label:
            stem = "hospitalInformation" if name.startswith("hospitalInformation") else "practitionerInformation"
            name = f"{stem}_{label}.json"
        pairs.append((source, out_fhir_dir / name))
    return process_files(pairs, options, used_ids, stats)


def copy_other_outputs(raw_dir: Path, out_dir: Path, label: str) -> None:
    """Copy non-FHIR exports (csv, metadata) from a raw run into the output folder."""
    for sub in ("csv", "metadata", "notes"):
        source = raw_dir / sub
        if source.is_dir():
            target = out_dir / sub / label
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
