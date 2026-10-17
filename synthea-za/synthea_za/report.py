"""Summarise a generated corpus: demographics, chronic disease prevalence and volumes."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from synthea_za.postprocess import is_patient_bundle

AGE_BANDS = [(0, 4), (5, 14), (15, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 74), (75, 200)]

# Conditions highlighted in the report, matched on the condition display text.
TRACKED_CONDITIONS = {
    "HIV": ["human immunodeficiency virus infection", "acquired immune deficiency syndrome"],
    "Tuberculosis": ["tuberculosis"],
    "Hypertension": ["hypertension"],
    "Diabetes": ["diabetes mellitus type 2", "diabetes mellitus type 1", "diabetes"],
    "Prediabetes": ["prediabetes"],
    "Obesity": ["body mass index 30+", "obesity", "obese"],
    "Asthma": ["asthma"],
    "COPD": ["pulmonary emphysema", "chronic obstructive bronchitis", "copd"],
    "Chronic kidney disease": ["chronic kidney disease"],
    "Coronary heart disease": ["coronary heart disease", "ischemic heart disease"],
    "Stroke": ["stroke"],
    "Heart failure": ["heart failure"],
    "Depression": ["major depressive disorder", "depress"],
    "Epilepsy": ["epilepsy", "seizure disorder"],
    "COVID-19": ["covid-19"],
}


def _age_band(age: int) -> str:
    for low, high in AGE_BANDS:
        if low <= age <= high:
            return f"{low}-{high}" if high < 200 else f"{low}+"
    return "unknown"


def _age(birth: str, reference: date, death: Optional[str]) -> int:
    born = date.fromisoformat(birth[:10])
    end = date.fromisoformat(death[:10]) if death else reference
    return end.year - born.year - ((end.month, end.day) < (born.month, born.day))


def _display(codeable: Dict[str, Any]) -> str:
    for coding in codeable.get("coding", []):
        if coding.get("display"):
            return coding["display"]
    return codeable.get("text", "")


def summarise(fhir_dir: Path, reference: Optional[date] = None) -> Dict[str, Any]:
    reference = reference or date.today()
    patients = 0
    alive = 0
    sex: Counter = Counter()
    bands: Counter = Counter()
    provinces: Counter = Counter()
    languages: Counter = Counter()
    payers: Counter = Counter()
    resource_counts: Counter = Counter()
    active_conditions: Counter = Counter()
    tracked: Counter = Counter()
    encounters_per_patient: List[int] = []
    ids: Counter = Counter()
    organisations = 0
    practitioners = 0
    for path in sorted(fhir_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            bundle = json.load(handle)
        entries = bundle.get("entry", [])
        if not is_patient_bundle(path):
            for entry in entries:
                kind = entry.get("resource", {}).get("resourceType")
                organisations += kind == "Organization"
                practitioners += kind == "Practitioner"
            continue
        patient = next((e["resource"] for e in entries if e["resource"].get("resourceType") == "Patient"), None)
        if patient is None:
            continue
        patients += 1
        deceased = patient.get("deceasedDateTime")
        alive += deceased is None
        sex[patient.get("gender", "unknown")] += 1
        bands[_age_band(_age(patient["birthDate"], reference, deceased))] += 1
        for address in patient.get("address", []):
            provinces[address.get("state", "unknown")] += 1
            break
        for communication in patient.get("communication", []):
            languages[_display(communication.get("language", {}))] += 1
        for identifier in patient.get("identifier", []):
            codes = {c.get("code") for c in identifier.get("type", {}).get("coding", [])}
            if "NNZAF" in codes:
                ids[identifier["value"]] += 1
        encounters = 0
        seen_tracked = set()
        latest_payer: Optional[str] = None
        for entry in entries:
            resource = entry["resource"]
            kind = resource.get("resourceType")
            resource_counts[kind] += 1
            if kind == "Encounter":
                encounters += 1
            elif kind == "Condition":
                display = _display(resource.get("code", {})).lower()
                clinical = resource.get("clinicalStatus", {}).get("coding", [{}])[0].get("code")
                if clinical == "active":
                    active_conditions[_display(resource.get("code", {}))] += 1
                for name, needles in TRACKED_CONDITIONS.items():
                    if any(n in display for n in needles):
                        seen_tracked.add(name)
            elif kind == "ExplanationOfBenefit":
                for insurance in resource.get("insurance", []):
                    latest_payer = insurance.get("coverage", {}).get("display") or latest_payer
        for name in seen_tracked:
            tracked[name] += 1
        if latest_payer:
            payers[latest_payer] += 1
        encounters_per_patient.append(encounters)
    duplicate_ids = sum(1 for count in ids.values() if count > 1)
    return {
        "reference_date": reference.isoformat(),
        "patients": patients,
        "alive": alive,
        "deceased": patients - alive,
        "sex": dict(sex),
        "age_bands": {band: bands[band] for band in [f"{l}-{h}" if h < 200 else f"{l}+" for l, h in AGE_BANDS]},
        "provinces": dict(provinces.most_common()),
        "languages": dict(languages.most_common()),
        "most_recent_payer": dict(payers.most_common()),
        "organisations": organisations,
        "practitioners": practitioners,
        "resources": dict(resource_counts.most_common()),
        "tracked_conditions": {name: {"patients": tracked[name],
                                      "percent": round(100.0 * tracked[name] / patients, 1) if patients else 0}
                               for name in TRACKED_CONDITIONS},
        "top_active_conditions": dict(active_conditions.most_common(25)),
        "encounters_per_patient": {
            "mean": round(sum(encounters_per_patient) / len(encounters_per_patient), 1) if encounters_per_patient else 0,
            "max": max(encounters_per_patient) if encounters_per_patient else 0,
        },
        "duplicate_national_ids": duplicate_ids,
    }


def render_markdown(summary: Dict[str, Any]) -> str:
    lines = ["# synthea-za corpus summary", ""]
    lines.append(f"Reference date: {summary['reference_date']}  ")
    lines.append(f"Patients: {summary['patients']} (alive {summary['alive']}, deceased {summary['deceased']})  ")
    lines.append(f"Organisations: {summary['organisations']}, practitioners: {summary['practitioners']}")
    lines.append("")

    def table(title: str, rows: Iterable, headers=("Key", "Count")) -> None:
        lines.append(f"## {title}")
        lines.append("")
        lines.append(f"| {headers[0]} | {headers[1]} |")
        lines.append("| --- | --- |")
        for key, value in rows:
            lines.append(f"| {key} | {value} |")
        lines.append("")

    table("Sex", summary["sex"].items())
    table("Age bands", summary["age_bands"].items(), ("Age band", "Patients"))
    table("Provinces", summary["provinces"].items(), ("Province", "Patients"))
    table("Home language", summary["languages"].items(), ("Language", "Patients"))
    table("Most recent payer", summary["most_recent_payer"].items(), ("Payer", "Patients"))
    table("Tracked conditions (ever diagnosed)",
          ((name, f"{v['patients']} ({v['percent']}%)") for name, v in summary["tracked_conditions"].items()),
          ("Condition", "Patients"))
    table("Top active conditions", summary["top_active_conditions"].items(), ("Condition", "Patients"))
    table("Resources", summary["resources"].items(), ("Resource type", "Count"))
    lines.append(f"Encounters per patient: mean {summary['encounters_per_patient']['mean']}, "
                 f"max {summary['encounters_per_patient']['max']}  ")
    lines.append(f"Duplicate national ID numbers: {summary['duplicate_national_ids']}")
    lines.append("")
    return "\n".join(lines)
