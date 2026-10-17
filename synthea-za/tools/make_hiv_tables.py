"""Generate South African calibration tables for Synthea's HIV modules.

The built in ``hiv_diagnosis`` and ``hiv_care`` modules drive the epidemic from lookup
tables keyed by calendar time, age and sex. This script writes South African versions
of those tables from a small set of epidemiological parameters (Thembisa model outputs,
UNAIDS estimates and the HSRC SABSSM surveys, rounded) so that the simulated population
reproduces the shape of the South African epidemic:

* very few diagnoses before 1990, diagnoses at AIDS stage until public sector ART in 2004,
* a surge of diagnoses with the 2010 to 2015 testing campaigns,
* women diagnosed younger and more often than men,
* mortality among diagnosed people falling from above 15% a year before ART to about 1%,
* most diagnosed people on continuous ART after universal test and treat (2016).

Run from the ``synthea-za`` directory:

    python tools/make_hiv_tables.py

Outputs go to ``synthea_za/data/modules/lookup_tables``; the matching module overrides live
in ``synthea_za/data/local_modules``.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

OUT = Path(__file__).resolve().parents[1] / "synthea_za" / "data" / "modules" / "lookup_tables"

# Synthea lookup tables express time ranges in milliseconds since the epoch. The built in
# tables start each year a few hundred milliseconds after midnight (…922) and end just
# before (…921); the same convention is used here so ranges never overlap.
START_OFFSET = 922
END_OFFSET = 921


def year_ms(year: int) -> int:
    return int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def time_range(start_year: int, end_year: int) -> str:
    return f"{year_ms(start_year) + START_OFFSET}-{year_ms(end_year) + END_OFFSET}"


def interpolate(points: Dict[int, float], year: int) -> float:
    years = sorted(points)
    if year <= years[0]:
        return points[years[0]]
    if year >= years[-1]:
        return points[years[-1]]
    for a, b in zip(years, years[1:]):
        if a <= year <= b:
            return points[a] + (points[b] - points[a]) * (year - a) / (b - a)
    return points[years[-1]]


# ----------------------------------------------------------------------------- parameters
# New HIV diagnoses (first positive test) per year, all ages, thousands. Infections ran well
# ahead of diagnoses until testing scaled up (HCT campaign 2010, UTT 2016).
DIAGNOSES_PER_YEAR = {
    1985: 1, 1988: 3, 1990: 8, 1993: 25, 1996: 60, 1999: 110, 2002: 160, 2004: 230,
    2006: 330, 2008: 420, 2010: 560, 2012: 520, 2014: 420, 2016: 360, 2018: 280,
    2020: 200, 2022: 180, 2024: 150, 2030: 110,
}
# Total population, millions (Stats SA).
POPULATION = {1985: 32.0, 1990: 36.8, 1995: 41.0, 2000: 44.9, 2005: 47.6, 2010: 51.2,
              2015: 55.4, 2020: 59.3, 2024: 63.0, 2030: 66.0}
# Share of the population in each age band (sexes combined, Census 2022 shape).
AGE_BANDS: List[Tuple[str, int, int, float]] = [
    ("0-12", 0, 12, 0.248), ("13-24", 13, 24, 0.200), ("25-34", 25, 34, 0.172),
    ("35-44", 35, 44, 0.147), ("45-54", 45, 54, 0.102), ("55-150", 55, 150, 0.131),
]
# Relative risk of diagnosis by population group (SABSSM 2017 prevalence: Black African 16.6%,
# Coloured 5.3%, White 1.1%, Indian 0.8%). Synthea race keys: black, other = Coloured, white,
# asian = Indian or Asian; native and hawaiian are unused but listed for completeness.
RACE_FACTOR = {"black": 1.16, "other": 0.42, "white": 0.10, "asian": 0.12, "native": 0.42,
               "hawaiian": 0.42}
# Share of diagnoses by sex and age band. Children's share was larger before PMTCT (2002+).
DIAGNOSIS_SHARES_EARLY = {  # before 2005
    ("M", "0-12"): 0.05, ("F", "0-12"): 0.05,
    ("M", "13-24"): 0.06, ("F", "13-24"): 0.16,
    ("M", "25-34"): 0.14, ("F", "25-34"): 0.24,
    ("M", "35-44"): 0.10, ("F", "35-44"): 0.11,
    ("M", "45-54"): 0.04, ("F", "45-54"): 0.03,
    ("M", "55-150"): 0.01, ("F", "55-150"): 0.01,
}
DIAGNOSIS_SHARES_LATE = {  # 2010 onwards
    ("M", "0-12"): 0.012, ("F", "0-12"): 0.012,
    ("M", "13-24"): 0.05, ("F", "13-24"): 0.17,
    ("M", "25-34"): 0.13, ("F", "25-34"): 0.26,
    ("M", "35-44"): 0.12, ("F", "35-44"): 0.14,
    ("M", "45-54"): 0.05, ("F", "45-54"): 0.04,
    ("M", "55-150"): 0.018, ("F", "55-150"): 0.018,
}
# Annual probability of death for a person with diagnosed HIV, by period. Early diagnoses
# were made at AIDS stage; mortality fell with ART (2004), earlier initiation (2010 to
# 2015) and universal treatment (2016).
MORTALITY = {1985: 0.22, 1995: 0.20, 2000: 0.17, 2004: 0.14, 2006: 0.09, 2008: 0.06,
             2010: 0.045, 2012: 0.030, 2014: 0.022, 2016: 0.016, 2019: 0.012, 2022: 0.009,
             2030: 0.007}
# Share of diagnosed people on ART, by period (Thembisa second 95: 29% in 2010, 52% in 2014,
# 68% in 2018, 81.5% in 2024); the rest cycle in and out of care.
CONTINUOUS_ART = {1985: 0.0, 2003: 0.0, 2004: 0.08, 2006: 0.15, 2008: 0.22, 2010: 0.29,
                  2012: 0.44, 2014: 0.52, 2016: 0.61, 2018: 0.68, 2020: 0.73, 2022: 0.76,
                  2024: 0.815, 2030: 0.85}
# Clinical stage at diagnosis (stage 1 early, stage 3 advanced), by period.
STAGE_AT_DIAGNOSIS = {
    1985: (0.10, 0.25, 0.65), 2004: (0.15, 0.30, 0.55), 2010: (0.28, 0.37, 0.35),
    2016: (0.40, 0.36, 0.24), 2022: (0.47, 0.35, 0.18), 2030: (0.50, 0.34, 0.16),
}


def diagnosis_probability(year: int, sex: str, band: str, band_share: float) -> float:
    """Annual probability that a person of this sex and age band is newly diagnosed."""
    total = interpolate(DIAGNOSES_PER_YEAR, year) * 1000.0
    population = interpolate(POPULATION, year) * 1_000_000.0
    mix = (year - 2005) / 5.0
    mix = min(1.0, max(0.0, mix))
    early = DIAGNOSIS_SHARES_EARLY[(sex, band)]
    late = DIAGNOSIS_SHARES_LATE[(sex, band)]
    share = early + (late - early) * mix
    # half the band's population is of this sex
    at_risk = population * band_share * 0.5
    return min(0.25, total * share / at_risk)


def write(name: str, header: List[str], rows: List[List[str]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    print(f"wrote {name}: {len(rows)} rows")


def main() -> None:
    # Diagnosis tables: "early" covers the pre-ART era (diagnosed at AIDS stage), "later"
    # the ART era. Both are read every simulated year for every living person.
    early_rows, later_rows = [], []
    for year in range(1985, 2031):
        rng = time_range(year, year + 1)
        for sex in ("M", "F"):
            for band, _, _, share in AGE_BANDS:
                base = diagnosis_probability(year, sex, band, share)
                for race, factor in RACE_FACTOR.items():
                    probability = min(0.3, base * factor)
                    row = [rng, band, sex, race, f"{probability:.7f}", f"{1 - probability:.7f}"]
                    (early_rows if year < 2004 else later_rows).append(row)
    write("hiv_diagnosis_early.csv",
          ["time", "age", "gender", "race", "Diagnosed_Early_Years", "Wait_Until_Next_Diagnosis_Check"],
          early_rows)
    write("hiv_diagnosis_later.csv",
          ["time", "age", "gender", "race", "Diagnosed_Later_Years", "Wait_Until_Next_Diagnosis_Check"],
          later_rows)

    # Mortality tables share one curve; children and the over 55s fare somewhat worse.
    early_mort, later_mort = [], []
    for year in range(1985, 2031):
        rng = time_range(year, year + 1)
        base = interpolate(MORTALITY, year)
        for sex in ("M", "F"):
            for band, low, _, _ in AGE_BANDS:
                factor = 1.3 if band == "0-12" else (1.25 if low >= 55 else (1.1 if sex == "M" else 0.95))
                probability = min(0.5, base * factor)
                if year < 2004:
                    early_mort.append([rng, band, sex, f"{probability:.4f}", f"{1 - probability:.4f}"])
                else:
                    later_mort.append([rng, band, sex, f"{probability:.4f}", f"{1 - probability:.4f}"])
    write("hiv_mortality_early.csv",
          ["time", "age", "gender", "Death", "Living_with_Diagnosis_Early_Years"], early_mort)
    write("hiv_mortality_later.csv",
          ["time", "age", "gender", "Death", "Living_with_Diagnosis_Later_Years"], later_mort)

    care_rows = []
    for year in range(1985, 2031):
        rng = time_range(year, year + 1)
        continuous = interpolate(CONTINUOUS_ART, year)
        for band, low, _, _ in AGE_BANDS:
            # younger adults are retained in care less well
            adjusted = continuous * (0.85 if band == "13-24" else (0.95 if band == "25-34" else 1.05))
            adjusted = min(0.95, adjusted)
            care_rows.append([rng, band, f"{adjusted:.3f}", f"{1 - adjusted:.3f}"])
    write("hiv_care.csv", ["time", "age", "Continuous_ART", "Non_Continuous_ART"], care_rows)

    stage_rows = []
    stage_years = sorted(STAGE_AT_DIAGNOSIS)
    for start, end in zip(stage_years, stage_years[1:] + [2031]):
        s1, s2, s3 = STAGE_AT_DIAGNOSIS[start]
        for band, low, _, _ in AGE_BANDS:
            if band == "0-12":
                continue
            # older people present later
            shift = 0.05 if low >= 45 else (-0.03 if band == "13-24" else 0.0)
            a, b, c = max(0.05, s1 - shift), s2, min(0.9, s3 + shift)
            total = a + b + c
            stage_rows.append([time_range(start, end), band, f"{a / total:.3f}", f"{b / total:.3f}", f"{c / total:.3f}"])
    write("hiv_stage.csv", ["time", "age", "stage_1", "stage_2", "stage_3"], stage_rows)


if __name__ == "__main__":
    main()
