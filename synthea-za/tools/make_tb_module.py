"""Generate the South African tuberculosis module for Synthea (synthea-za).

South Africa carries one of the heaviest tuberculosis burdens in the world (WHO estimated
incidence about 1 000 per 100 000 at the 2008 peak, falling to roughly 430 per 100 000 by
2023), with about half of all TB patients also living with HIV. Synthea has no built in TB
module, so this script writes one as a generic module JSON file.

Model outline (annual cycle from birth):
* an annual risk of active TB disease that depends on calendar year (epidemic curve),
  on HIV status (people with diagnosed HIV carry a much higher risk, lower when they are on
  continuous ART) and on age;
* symptoms, a primary care visit, Xpert MTB/RIF testing, chest X-ray and diagnosis of
  pulmonary tuberculosis (a small share extrapulmonary, a small share rifampicin resistant);
* six months of standard treatment (two months of RHZE then four months of RH) with
  follow-up visits and sputum monitoring, or a bedaquiline based regimen for drug resistant
  disease, plus cotrimoxazole for HIV co-infected patients;
* outcomes: cure, death, loss to follow up (with later recurrence) and relapse;
* TB preventive therapy for people on ART.

Codes are kept in the CODES table so they can be corrected in one place. Run from the
``synthea-za`` directory:

    python tools/make_tb_module.py
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "synthea_za" / "data" / "local_modules" / "tuberculosis.json"

# ----------------------------------------------------------------------------- codes
CODES = {
    # SNOMED CT conditions (verified against SNOMED browsers and value sets)
    "pulmonary_tb": ("SNOMED-CT", "154283005", "Pulmonary tuberculosis (disorder)"),
    "extrapulmonary_tb": ("SNOMED-CT", "10893003", "Tuberculous adenitis (disorder)"),
    "rr_tb": ("SNOMED-CT", "415345001", "Rifampicin resistant tuberculosis (disorder)"),
    "mdr_tb": ("SNOMED-CT", "423092005", "Multidrug resistant tuberculosis (disorder)"),
    "latent_tb": ("SNOMED-CT", "11999007", "Latent tuberculosis (finding)"),
    # SNOMED CT procedures
    "tb_screening": ("SNOMED-CT", "171126009", "Tuberculosis screening (procedure)"),
    "sputum_collection": ("SNOMED-CT", "37705003", "Collection of sputum (procedure)"),
    "chest_xray": ("SNOMED-CT", "399208008", "Plain chest X-ray (procedure)"),
    "dot": ("SNOMED-CT", "182882002", "Drug intake observed (procedure)"),
    "hiv_counselling": ("SNOMED-CT", "313077009", "Human immunodeficiency virus counseling (procedure)"),
    "tb_careplan": ("SNOMED-CT", "736376001", "Infectious disease care plan (record artifact)"),
    "referral": ("SNOMED-CT", "183851006", "Referral to clinic (procedure)"),
    # LOINC laboratory
    "xpert_report": ("LOINC", "85362-2", "Mycobacterium tuberculosis complex DNA [Presence] in Sputum or Bronchial by NAA with probe detection"),
    "xpert_mtb": ("LOINC", "85362-2", "Mycobacterium tuberculosis complex DNA [Presence] in Sputum or Bronchial by NAA with probe detection"),
    "xpert_rif": ("LOINC", "89372-7", "Mycobacterium tuberculosis complex rpoB gene rifAMPin resistance mutation [Presence] by Molecular method"),
    "afb_smear": ("LOINC", "11477-7", "Microscopic observation [Identifier] in Sputum by Acid fast stain"),
    "tb_culture": ("LOINC", "539-7", "Mycobacterium sp identified in Sputum by Organism specific culture"),
    # value codes
    "detected": ("SNOMED-CT", "260373001", "Detected (qualifier value)"),
    "not_detected": ("SNOMED-CT", "260415000", "Not detected (qualifier value)"),
    # RxNorm medications (semantic clinical drugs). South Africa dispenses fixed dose
    # combinations (RHZE, RH) but RxNorm has no normalised products for them, so the single
    # ingredient tablets are recorded.
    "rifampin": ("RxNorm", "198202", "rifampin 300 MG Oral Capsule"),
    "isoniazid": ("RxNorm", "197832", "isoniazid 300 MG Oral Tablet"),
    "pyrazinamide": ("RxNorm", "198181", "pyrazinamide 500 MG Oral Tablet"),
    "ethambutol": ("RxNorm", "995607", "ethambutol hydrochloride 400 MG Oral Tablet"),
    "pyridoxine": ("RxNorm", "1100457", "pyridoxine hydrochloride 25 MG Oral Tablet"),
    "bedaquiline": ("RxNorm", "1364509", "bedaquiline 100 MG Oral Tablet"),
    "linezolid": ("RxNorm", "311347", "linezolid 600 MG Oral Tablet"),
    "levofloxacin": ("RxNorm", "199885", "levofloxacin 500 MG Oral Tablet"),
    "moxifloxacin": ("RxNorm", "311787", "moxifloxacin 400 MG Oral Tablet"),
    "pretomanid": ("RxNorm", "2198370", "pretomanid 200 MG Oral Tablet"),
    "cotrimoxazole": ("RxNorm", "198335", "sulfamethoxazole 800 MG / trimethoprim 160 MG Oral Tablet"),
    "rifapentine": ("RxNorm", "242671", "rifapentine 150 MG Oral Tablet"),
}


def code(key):
    system, value, display = CODES[key]
    return {"system": system, "code": value, "display": display}


def med(key, nxt, amount=1, frequency=1, duration_months=None, reason="tb_condition", attribute=None,
        chronic=False, period=1, period_unit="days"):
    state = {"type": "MedicationOrder", "codes": [code(key)], "reason": reason,
             "prescription": {"dosage": {"amount": amount, "frequency": frequency, "period": period, "unit": period_unit},
                              "duration": {"quantity": duration_months or 1, "unit": "months"},
                              "refills": 0},
             "direct_transition": nxt}
    if attribute:
        state["assign_to_attribute"] = attribute
    if chronic:
        state["chronic"] = True
    return state


def med_end(key, nxt, attribute=None):
    state = {"type": "MedicationEnd", "direct_transition": nxt}
    if attribute:
        state["referenced_by_attribute"] = attribute
    else:
        state["codes"] = [code(key)]
    return state


def delay(nxt, quantity=None, unit="months", low=None, high=None):
    state = {"type": "Delay", "direct_transition": nxt}
    if quantity is not None:
        state["exact"] = {"quantity": quantity, "unit": unit}
    else:
        state["range"] = {"low": low, "high": high, "unit": unit}
    return state


def encounter(nxt, reason=None, encounter_class="ambulatory", wellness=False):
    state = {"type": "Encounter", "encounter_class": encounter_class,
             "codes": [{"system": "SNOMED-CT", "code": "185347001", "display": "Encounter for problem (procedure)"}],
             "direct_transition": nxt}
    if reason:
        state["reason"] = reason
    return state


def procedure(key, nxt, reason=None, minutes=(10, 20)):
    state = {"type": "Procedure", "codes": [code(key)],
             "distribution": {"kind": "UNIFORM", "parameters": {"low": minutes[0], "high": minutes[1]}},
             "unit": "minutes", "direct_transition": nxt}
    if reason:
        state["reason"] = reason
    return state


def xpert_report(nxt, positive, rif_resistant=False):
    return {"type": "DiagnosticReport", "codes": [code("xpert_report")],
            "observations": [
                {"category": "laboratory", "unit": "{nominal}", "codes": [code("xpert_mtb")],
                 "value_code": code("detected" if positive else "not_detected")},
                {"category": "laboratory", "unit": "{nominal}", "codes": [code("xpert_rif")],
                 "value_code": code("detected" if rif_resistant else "not_detected")},
            ],
            "direct_transition": nxt}


def sputum_monitoring(nxt, positive=False):
    return {"type": "DiagnosticReport", "codes": [code("afb_smear")],
            "observations": [
                {"category": "laboratory", "unit": "{nominal}", "codes": [code("afb_smear")],
                 "value_code": code("detected" if positive else "not_detected")},
            ],
            "direct_transition": nxt}


# Annual probability of developing active TB for a person without diagnosed HIV, by period.
# The incidence curve follows the WHO estimates (about 300 per 100 000 in 1990, a peak near
# 1 000 per 100 000 around 2008 and roughly 430 per 100 000 by 2023), with people living with
# HIV carrying most of the excess; the general population rate here is the HIV negative share.
GENERAL_RISK = [
    (1990, 0.0022), (1995, 0.0027), (2000, 0.0031), (2005, 0.0034), (2010, 0.0033),
    (2015, 0.0028), (2020, 0.0023), (2030, 0.0019),
]
# Annual probability for people with diagnosed HIV: much higher, and lower on continuous ART.
HIV_RISK_UNTREATED = 0.060
HIV_RISK_ON_ART = 0.018
HIV_RISK_ON_TPT = 0.010
TPT_UPTAKE = 0.25  # yearly chance that someone on ART who has not had TPT starts it
CHILD_FACTOR = 0.45  # children under 15 compared with adults


def risk_states():
    """Yearly risk check: branch on HIV status, then on calendar period."""
    states = {}
    states["TB Risk Check"] = {"type": "Simple", "conditional_transition": [
        {"transition": "HIV Risk Check", "condition": {"condition_type": "Attribute", "attribute": "hiv_diagnosis", "operator": "is not nil"}},
        {"transition": "General Risk Check"}]}
    states["HIV Risk Check"] = {"type": "Simple", "complex_transition": [
        {"condition": {"condition_type": "Attribute", "attribute": "tb_preventive_therapy", "operator": "==", "value": True},
         "distributions": [{"distribution": HIV_RISK_ON_TPT, "transition": "Onset Active TB"},
                           {"distribution": 1 - HIV_RISK_ON_TPT, "transition": "Wait A Year"}]},
        {"condition": {"condition_type": "Attribute", "attribute": "hiv_continuous_art", "operator": "==", "value": True},
         "distributions": [{"distribution": HIV_RISK_ON_ART, "transition": "Onset Active TB"},
                           {"distribution": TPT_UPTAKE, "transition": "TPT Check"},
                           {"distribution": 1 - HIV_RISK_ON_ART - TPT_UPTAKE, "transition": "Wait A Year"}]},
        {"distributions": [{"distribution": HIV_RISK_UNTREATED, "transition": "Onset Active TB"},
                           {"distribution": 1 - HIV_RISK_UNTREATED, "transition": "Wait A Year"}]}]}
    # TB preventive therapy: isoniazid for a year from 2010, weekly isoniazid and rifapentine
    # (3HP) for twelve weeks from 2021, offered at a routine HIV visit
    states["TPT Check"] = {"type": "Simple", "conditional_transition": [
        {"transition": "TPT Visit", "condition": {"condition_type": "Date", "operator": ">=", "year": 2010}},
        {"transition": "Wait A Year"}]}
    states["TPT Visit"] = encounter("TPT Regimen", reason=None)
    states["TPT Regimen"] = {"type": "Simple", "conditional_transition": [
        {"transition": "TPT Rifapentine", "condition": {"condition_type": "Date", "operator": ">=", "year": 2021}},
        {"transition": "TPT Isoniazid Twelve Months"}]}
    states["TPT Rifapentine"] = med("rifapentine", "TPT Isoniazid Weekly", amount=6, frequency=1, duration_months=3, reason="hiv_diagnosis", attribute="tb_tpt_med_1", period=1, period_unit="weeks")
    states["TPT Isoniazid Weekly"] = med("isoniazid", "Set TPT", amount=3, frequency=1, duration_months=3, reason="hiv_diagnosis", attribute="tb_tpt_med_2", period=1, period_unit="weeks")
    states["TPT Isoniazid Twelve Months"] = med("isoniazid", "Set TPT", amount=1, frequency=1, duration_months=12, reason="hiv_diagnosis", attribute="tb_tpt_med_2")
    states["Set TPT"] = {"type": "SetAttribute", "attribute": "tb_preventive_therapy", "value": True, "direct_transition": "End TPT Visit"}
    states["End TPT Visit"] = {"type": "EncounterEnd", "direct_transition": "TPT Course"}
    states["TPT Course"] = {"type": "Simple", "conditional_transition": [
        {"transition": "TPT Three Months", "condition": {"condition_type": "Date", "operator": ">=", "year": 2021}},
        {"transition": "TPT Twelve Months"}]}
    states["TPT Three Months"] = delay("End TPT Rifapentine", quantity=3)
    states["TPT Twelve Months"] = delay("End TPT Rifapentine", quantity=12)
    states["End TPT Rifapentine"] = {"type": "MedicationEnd", "codes": [code("rifapentine")], "direct_transition": "End TPT Isoniazid"}
    states["End TPT Isoniazid"] = {"type": "MedicationEnd", "codes": [code("isoniazid")], "direct_transition": "TB Risk Check"}
    # calendar periods for the general population
    conditional = []
    periods = sorted(GENERAL_RISK, reverse=True)
    for year, risk in periods:
        name = f"General Risk {year}"
        conditional.append({"transition": name, "condition": {"condition_type": "Date", "operator": ">=", "year": year}})
        child = risk * CHILD_FACTOR
        states[name] = {"type": "Simple", "complex_transition": [
            {"condition": {"condition_type": "Age", "operator": "<", "quantity": 15, "unit": "years"},
             "distributions": [{"distribution": child, "transition": "Onset Active TB"},
                               {"distribution": 1 - child, "transition": "Wait A Year"}]},
            {"distributions": [{"distribution": risk, "transition": "Onset Active TB"},
                               {"distribution": 1 - risk, "transition": "Wait A Year"}]}]}
    conditional.append({"transition": "Wait A Year"})
    states["General Risk Check"] = {"type": "Simple", "conditional_transition": conditional}
    states["Wait A Year"] = {"type": "Delay", "exact": {"quantity": 1, "unit": "years"}, "direct_transition": "Recurrence Risk Check"}
    # people who had TB before carry a higher risk for several years
    states["Recurrence Risk Check"] = {"type": "Simple", "complex_transition": [
        {"condition": {"condition_type": "Attribute", "attribute": "tb_history", "operator": "==", "value": True},
         "distributions": [{"distribution": 0.03, "transition": "Onset Active TB"}, {"distribution": 0.97, "transition": "TB Risk Check"}]},
        {"transition": "TB Risk Check"}]}
    return states


def build():
    states = {
        "Initial": {"type": "Initial", "direct_transition": "Wait A Year"},
        "Terminal": {"type": "Terminal"},
    }
    states.update(risk_states())

    # ------------------------------------------------------------------ onset and diagnosis
    states["Onset Active TB"] = {"type": "Simple", "distributed_transition": [
        {"distribution": 0.86, "transition": "Pulmonary TB Onset"},
        {"distribution": 0.14, "transition": "Extrapulmonary TB Onset"}]}
    states["Pulmonary TB Onset"] = {"type": "ConditionOnset", "codes": [code("pulmonary_tb")],
                                    "assign_to_attribute": "tb_condition", "target_encounter": "TB Diagnosis Visit",
                                    "direct_transition": "Cough Symptom"}
    states["Extrapulmonary TB Onset"] = {"type": "ConditionOnset", "codes": [code("extrapulmonary_tb")],
                                         "assign_to_attribute": "tb_condition", "target_encounter": "TB Diagnosis Visit",
                                         "direct_transition": "Set Extrapulmonary"}
    states["Set Extrapulmonary"] = {"type": "SetAttribute", "attribute": "tb_extrapulmonary", "value": True, "direct_transition": "Cough Symptom"}
    states["Cough Symptom"] = {"type": "Symptom", "symptom": "Cough", "cause": "Tuberculosis",
                               "range": {"low": 40, "high": 90}, "direct_transition": "Fever Symptom"}
    states["Fever Symptom"] = {"type": "Symptom", "symptom": "Fever", "cause": "Tuberculosis",
                               "range": {"low": 20, "high": 60}, "direct_transition": "Weight Loss Symptom"}
    states["Weight Loss Symptom"] = {"type": "Symptom", "symptom": "Weight Loss", "cause": "Tuberculosis",
                                     "range": {"low": 20, "high": 70}, "direct_transition": "Night Sweats Symptom"}
    states["Night Sweats Symptom"] = {"type": "Symptom", "symptom": "Night Sweats", "cause": "Tuberculosis",
                                      "range": {"low": 20, "high": 70}, "direct_transition": "Delay Before Care Seeking"}
    # people take weeks to months to present; a minority die undiagnosed
    states["Delay Before Care Seeking"] = {"type": "Delay", "range": {"low": 2, "high": 12, "unit": "weeks"},
                                           "direct_transition": "Undiagnosed Outcome"}
    states["Undiagnosed Outcome"] = {"type": "Simple", "distributed_transition": [
        {"distribution": 0.03, "transition": "Death Before Diagnosis"},
        {"distribution": 0.97, "transition": "TB Diagnosis Visit"}]}
    states["Death Before Diagnosis"] = {"type": "Death", "referenced_by_attribute": "tb_condition",
                                        "range": {"low": 1, "high": 8, "unit": "weeks"}, "direct_transition": "Terminal"}
    states["TB Diagnosis Visit"] = encounter("TB Symptom Screen", reason="tb_condition")
    states["TB Symptom Screen"] = procedure("tb_screening", "Sputum Collection", reason="tb_condition", minutes=(5, 10))
    states["Sputum Collection"] = procedure("sputum_collection", "Resistance Check", reason="tb_condition", minutes=(5, 10))
    states["Resistance Check"] = {"type": "Simple", "distributed_transition": [
        {"distribution": 0.035, "transition": "Xpert Rifampicin Resistant"},
        {"distribution": 0.965, "transition": "Xpert Positive"}]}
    states["Xpert Positive"] = xpert_report("Chest X-ray", positive=True)
    states["Xpert Rifampicin Resistant"] = xpert_report("MDR Onset", positive=True, rif_resistant=True)
    states["MDR Onset"] = {"type": "ConditionOnset", "codes": [code("rr_tb")], "assign_to_attribute": "tb_mdr_condition",
                           "target_encounter": "TB Diagnosis Visit", "direct_transition": "Chest X-ray"}
    states["Chest X-ray"] = procedure("chest_xray", "HIV Status Check", reason="tb_condition", minutes=(10, 20))
    # everyone diagnosed with TB is offered an HIV test; use the existing screening submodule
    states["HIV Status Check"] = {"type": "Simple", "conditional_transition": [
        {"transition": "TB Care Plan", "condition": {"condition_type": "Attribute", "attribute": "hiv_diagnosis", "operator": "is not nil"}},
        {"transition": "HIV Screening"}]}
    states["HIV Screening"] = {"type": "CallSubmodule", "submodule": "hiv/hiv_screening", "direct_transition": "TB Care Plan"}
    states["TB Care Plan"] = {"type": "CarePlanStart", "codes": [code("tb_careplan")], "reason": "tb_condition",
                              "assign_to_attribute": "tb_careplan",
                              "activities": [code("dot"), {"system": "SNOMED-CT", "code": "226234005", "display": "Healthy diet (finding)"}],
                              "direct_transition": "Regimen Choice"}
    states["Regimen Choice"] = {"type": "Simple", "conditional_transition": [
        {"transition": "MDR Regimen Start", "condition": {"condition_type": "Attribute", "attribute": "tb_mdr_condition", "operator": "is not nil"}},
        {"transition": "Intensive Phase Start"}]}

    # ------------------------------------------------------------------ drug sensitive treatment
    states["Intensive Phase Start"] = {"type": "Simple", "direct_transition": "Rifampin Separate"}
    states["Rifampin Separate"] = med("rifampin", "Isoniazid Separate", amount=2, frequency=1, duration_months=2, attribute="tb_rifampin_med")
    states["Isoniazid Separate"] = med("isoniazid", "Pyrazinamide Separate", amount=1, frequency=1, duration_months=2, attribute="tb_isoniazid_med")
    states["Pyrazinamide Separate"] = med("pyrazinamide", "Ethambutol Separate", amount=3, frequency=1, duration_months=2, attribute="tb_pyrazinamide_med")
    states["Ethambutol Separate"] = med("ethambutol", "Pyridoxine", amount=3, frequency=1, duration_months=2, attribute="tb_ethambutol_med")
    states["Pyridoxine"] = med("pyridoxine", "Cotrimoxazole Check", amount=1, frequency=1, duration_months=6, attribute="tb_pyridoxine_med")
    states["Cotrimoxazole Check"] = {"type": "Simple", "conditional_transition": [
        {"transition": "Cotrimoxazole", "condition": {"condition_type": "Attribute", "attribute": "hiv_diagnosis", "operator": "is not nil"}},
        {"transition": "End Diagnosis Visit"}]}
    states["Cotrimoxazole"] = med("cotrimoxazole", "End Diagnosis Visit", amount=1, frequency=1, duration_months=6, attribute="tb_cotrimoxazole_med")
    states["End Diagnosis Visit"] = {"type": "EncounterEnd", "direct_transition": "Intensive Phase"}
    states["Intensive Phase"] = delay("Two Month Visit", quantity=2)
    states["Two Month Visit"] = encounter("Two Month Sputum", reason="tb_condition")
    states["Two Month Sputum"] = sputum_monitoring("End Intensive Medications", positive=False)
    states["End Intensive Medications"] = {"type": "Simple", "direct_transition": "End Rifampin Separate"}
    states["End Rifampin Separate"] = med_end("rifampin", "End Isoniazid Separate", attribute="tb_rifampin_med")
    states["End Isoniazid Separate"] = med_end("isoniazid", "End Pyrazinamide Separate", attribute="tb_isoniazid_med")
    states["End Pyrazinamide Separate"] = med_end("pyrazinamide", "End Ethambutol Separate", attribute="tb_pyrazinamide_med")
    states["End Ethambutol Separate"] = med_end("ethambutol", "Continuation Phase Start", attribute="tb_ethambutol_med")
    states["Continuation Phase Start"] = {"type": "Simple", "direct_transition": "Rifampin Continuation"}
    states["Rifampin Continuation"] = med("rifampin", "Isoniazid Continuation", amount=2, frequency=1, duration_months=4, attribute="tb_rifampin_med")
    states["Isoniazid Continuation"] = med("isoniazid", "End Two Month Visit", amount=1, frequency=1, duration_months=4, attribute="tb_isoniazid_med")
    states["End Two Month Visit"] = {"type": "EncounterEnd", "direct_transition": "Continuation Phase"}
    states["Continuation Phase"] = delay("Treatment Outcome", quantity=4)
    states["Treatment Outcome"] = {"type": "Simple", "complex_transition": [
        {"condition": {"condition_type": "Attribute", "attribute": "hiv_diagnosis", "operator": "is not nil"},
         "distributions": [{"distribution": 0.74, "transition": "End of Treatment Visit"},
                           {"distribution": 0.10, "transition": "Death During Treatment"},
                           {"distribution": 0.14, "transition": "Lost To Follow Up"},
                           {"distribution": 0.02, "transition": "Treatment Failure"}]},
        {"distributions": [{"distribution": 0.82, "transition": "End of Treatment Visit"},
                           {"distribution": 0.045, "transition": "Death During Treatment"},
                           {"distribution": 0.12, "transition": "Lost To Follow Up"},
                           {"distribution": 0.015, "transition": "Treatment Failure"}]}]}
    states["Death During Treatment"] = {"type": "Death", "referenced_by_attribute": "tb_condition",
                                        "range": {"low": 0, "high": 60, "unit": "days"}, "direct_transition": "Terminal"}
    states["Lost To Follow Up"] = {"type": "Simple", "direct_transition": "Stop Continuation Medications"}
    states["Treatment Failure"] = {"type": "Simple", "direct_transition": "Stop Continuation Medications"}
    states["Stop Continuation Medications"] = {"type": "Simple", "direct_transition": "Stop Rifampin"}
    states["Stop Rifampin"] = med_end("rifampin", "Stop Isoniazid", attribute="tb_rifampin_med")
    states["Stop Isoniazid"] = med_end("isoniazid", "Stop Pyridoxine", attribute="tb_isoniazid_med")
    states["Stop Pyridoxine"] = med_end("pyridoxine", "Stop Cotrimoxazole Check", attribute="tb_pyridoxine_med")
    states["Stop Cotrimoxazole Check"] = {"type": "Simple", "conditional_transition": [
        {"transition": "Stop Cotrimoxazole", "condition": {"condition_type": "Attribute", "attribute": "tb_cotrimoxazole_med", "operator": "is not nil"}},
        {"transition": "Set TB History After Loss"}]}
    states["Stop Cotrimoxazole"] = med_end("cotrimoxazole", "Set TB History After Loss", attribute="tb_cotrimoxazole_med")
    # disease persists untreated for a while, then either resolves, kills or recurs
    states["Set TB History After Loss"] = {"type": "SetAttribute", "attribute": "tb_history", "value": True, "direct_transition": "Untreated Interval"}
    states["Untreated Interval"] = delay("Untreated Outcome", low=3, high=12)
    states["Untreated Outcome"] = {"type": "Simple", "distributed_transition": [
        {"distribution": 0.55, "transition": "Return To Care"},
        {"distribution": 0.25, "transition": "Death Untreated"},
        {"distribution": 0.20, "transition": "Condition Resolves Untreated"}]}
    states["Death Untreated"] = {"type": "Death", "referenced_by_attribute": "tb_condition",
                                 "range": {"low": 0, "high": 90, "unit": "days"}, "direct_transition": "Terminal"}
    states["Condition Resolves Untreated"] = {"type": "ConditionEnd", "referenced_by_attribute": "tb_condition", "direct_transition": "Clear MDR"}
    states["Return To Care"] = encounter("Return Sputum", reason="tb_condition")
    states["Return Sputum"] = xpert_report("Retreatment Resistance Check", positive=True)
    states["Retreatment Resistance Check"] = {"type": "Simple", "complex_transition": [
        {"condition": {"condition_type": "Attribute", "attribute": "tb_mdr_condition", "operator": "is not nil"},
         "transition": "MDR Regimen Start"},
        {"distributions": [{"distribution": 0.08, "transition": "Retreatment MDR Onset"},
                           {"distribution": 0.92, "transition": "Retreatment Regimen"}]}]}
    states["Retreatment MDR Onset"] = {"type": "ConditionOnset", "codes": [code("rr_tb")], "assign_to_attribute": "tb_mdr_condition",
                                       "target_encounter": "Return To Care", "direct_transition": "MDR Regimen Start"}
    states["Retreatment Regimen"] = {"type": "Simple", "direct_transition": "Intensive Phase Start"}

    states["End of Treatment Visit"] = encounter("End of Treatment Sputum", reason="tb_condition")
    states["End of Treatment Sputum"] = sputum_monitoring("Cured Stop Medications", positive=False)
    states["Cured Stop Medications"] = {"type": "Simple", "direct_transition": "Cured Stop Rifampin"}
    states["Cured Stop Rifampin"] = med_end("rifampin", "Cured Stop Isoniazid", attribute="tb_rifampin_med")
    states["Cured Stop Isoniazid"] = med_end("isoniazid", "Cured Stop Pyridoxine", attribute="tb_isoniazid_med")
    states["Cured Stop Pyridoxine"] = med_end("pyridoxine", "Cured Stop Cotrimoxazole Check", attribute="tb_pyridoxine_med")
    states["Cured Stop Cotrimoxazole Check"] = {"type": "Simple", "conditional_transition": [
        {"transition": "Cured Stop Cotrimoxazole", "condition": {"condition_type": "Attribute", "attribute": "tb_cotrimoxazole_med", "operator": "is not nil"}},
        {"transition": "TB Cured"}]}
    states["Cured Stop Cotrimoxazole"] = med_end("cotrimoxazole", "TB Cured", attribute="tb_cotrimoxazole_med")
    states["TB Cured"] = {"type": "ConditionEnd", "referenced_by_attribute": "tb_condition", "direct_transition": "End Care Plan"}
    states["End Care Plan"] = {"type": "CarePlanEnd", "referenced_by_attribute": "tb_careplan", "direct_transition": "Clear MDR"}
    states["Clear MDR"] = {"type": "Simple", "conditional_transition": [
        {"transition": "End MDR Condition", "condition": {"condition_type": "Attribute", "attribute": "tb_mdr_condition", "operator": "is not nil"}},
        {"transition": "Set TB History"}]}
    states["End MDR Condition"] = {"type": "ConditionEnd", "referenced_by_attribute": "tb_mdr_condition", "direct_transition": "Clear MDR Attribute"}
    states["Clear MDR Attribute"] = {"type": "SetAttribute", "attribute": "tb_mdr_condition", "direct_transition": "Set TB History"}
    states["Set TB History"] = {"type": "SetAttribute", "attribute": "tb_history", "value": True, "direct_transition": "End Treatment Visit"}
    states["End Treatment Visit"] = {"type": "EncounterEnd", "direct_transition": "Wait A Year"}

    # ------------------------------------------------------------------ drug resistant treatment
    states["MDR Regimen Start"] = {"type": "Simple", "conditional_transition": [
        {"transition": "Bedaquiline Short", "condition": {"condition_type": "Date", "operator": ">=", "year": 2023}},
        {"transition": "Bedaquiline Long", "condition": {"condition_type": "Date", "operator": ">=", "year": 2018}},
        {"transition": "Levofloxacin Long"}]}
    # BPaLL (bedaquiline, pretomanid, linezolid, levofloxacin) six months from 2023
    states["Bedaquiline Short"] = med("bedaquiline", "Pretomanid Short", amount=1, frequency=1, duration_months=6, attribute="tb_mdr_med_1")
    states["Pretomanid Short"] = med("pretomanid", "Linezolid Short", amount=1, frequency=1, duration_months=6, attribute="tb_mdr_med_2")
    states["Linezolid Short"] = med("linezolid", "Levofloxacin Short", amount=1, frequency=1, duration_months=6, attribute="tb_mdr_med_3")
    states["Levofloxacin Short"] = med("levofloxacin", "MDR Visit End", amount=1, frequency=1, duration_months=6, attribute="tb_mdr_med_4")
    # bedaquiline based nine to eleven month regimen 2018 to 2022
    states["Bedaquiline Long"] = med("bedaquiline", "Linezolid Long", amount=1, frequency=1, duration_months=9, attribute="tb_mdr_med_1")
    states["Linezolid Long"] = med("linezolid", "Levofloxacin After Bedaquiline", amount=1, frequency=1, duration_months=9, attribute="tb_mdr_med_3")
    states["Levofloxacin After Bedaquiline"] = med("levofloxacin", "MDR Visit End", amount=1, frequency=1, duration_months=9, attribute="tb_mdr_med_4")
    # injectable era (before 2018): fluoroquinolone plus companion drugs, recorded as levofloxacin and ethambutol
    states["Levofloxacin Long"] = med("levofloxacin", "Ethambutol Long", amount=1, frequency=1, duration_months=18, attribute="tb_mdr_med_4")
    states["Ethambutol Long"] = med("ethambutol", "MDR Visit End", amount=3, frequency=1, duration_months=18, attribute="tb_mdr_med_2")
    states["MDR Visit End"] = {"type": "EncounterEnd", "direct_transition": "MDR Treatment Course"}
    states["MDR Treatment Course"] = {"type": "Simple", "conditional_transition": [
        {"transition": "MDR Six Months", "condition": {"condition_type": "Date", "operator": ">=", "year": 2023}},
        {"transition": "MDR Nine Months", "condition": {"condition_type": "Date", "operator": ">=", "year": 2018}},
        {"transition": "MDR Eighteen Months"}]}
    states["MDR Six Months"] = delay("MDR Outcome", quantity=6)
    states["MDR Nine Months"] = delay("MDR Outcome", quantity=9)
    states["MDR Eighteen Months"] = delay("MDR Outcome", quantity=18)
    states["MDR Outcome"] = {"type": "Simple", "distributed_transition": [
        {"distribution": 0.70, "transition": "MDR Completion Visit"},
        {"distribution": 0.15, "transition": "Death During Treatment"},
        {"distribution": 0.15, "transition": "MDR Lost"}]}
    states["MDR Lost"] = {"type": "Simple", "direct_transition": "Stop MDR Medications Lost"}
    states["MDR Completion Visit"] = encounter("MDR Completion Sputum", reason="tb_condition")
    states["MDR Completion Sputum"] = sputum_monitoring("Stop MDR Medications", positive=False)
    # the regimens differ by era, so the drugs are ended by code: ending a medication that
    # was never prescribed is a no-op in Synthea, ending one by a missing attribute is not
    mdr_drugs = ["bedaquiline", "pretomanid", "linezolid", "levofloxacin", "ethambutol"]
    for prefix, nxt in (("Stop MDR Medications", "TB Cured"), ("Stop MDR Medications Lost", "Set TB History After Loss")):
        chain = [f"{prefix} {drug}" for drug in mdr_drugs]
        states[prefix] = {"type": "Simple", "direct_transition": chain[0]}
        for index, name in enumerate(chain):
            target = chain[index + 1] if index + 1 < len(chain) else nxt
            states[name] = {"type": "MedicationEnd", "codes": [code(mdr_drugs[index])], "direct_transition": target}

    module = {
        "name": "Tuberculosis",
        "remarks": [
            "South African tuberculosis module (synthea-za).",
            "Models the annual risk of active tuberculosis with the national epidemic curve, the very high risk among people living with HIV (lower on continuous ART), Xpert MTB/RIF based diagnosis, chest radiography, six months of standard first line treatment (RHZE then RH fixed dose combinations from 2012), cotrimoxazole prophylaxis for HIV co-infected patients, drug resistant disease treated with bedaquiline based regimens (BPaLL from 2023), loss to follow up, death and recurrence.",
            "Generated by synthea-za/tools/make_tb_module.py; edit the generator rather than this file.",
        ],
        "states": states,
    }
    return module


def check(module):
    targets = set()

    def collect(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("transition", "direct_transition") and isinstance(v, str):
                    targets.add(v)
                collect(v)
        elif isinstance(o, list):
            for v in o:
                collect(v)

    collect(module["states"])
    missing = targets - set(module["states"])
    if missing:
        raise SystemExit(f"transitions to undefined states: {sorted(missing)}")
    for name, state in module["states"].items():
        for key in ("distributed_transition",):
            if key in state:
                total = sum(d["distribution"] for d in state[key])
                if abs(total - 1) > 1e-6:
                    raise SystemExit(f"{name}: distributions sum to {total}")
        for branch in state.get("complex_transition", []):
            if "distributions" in branch:
                total = sum(d["distribution"] for d in branch["distributions"])
                if abs(total - 1) > 1e-6:
                    raise SystemExit(f"{name}: complex distributions sum to {total}")
    placeholders = [k for k, v in CODES.items() if v[1] == "0"]
    if placeholders:
        print(f"warning: placeholder codes still present for {placeholders}")


def main():
    module = build()
    check(module)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(module, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} with {len(module['states'])} states")


if __name__ == "__main__":
    main()
