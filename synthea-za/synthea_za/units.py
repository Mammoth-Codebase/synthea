"""Conversion of common laboratory results from US conventional units to SI units.

Synthea records many chemistry results in mg/dL. South African laboratories report
these analytes in mmol/L or umol/L. Only observations whose LOINC code appears in this
table and whose unit matches the expected source unit are converted; everything else is
left untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Conversion:
    source_unit: str
    target_unit: str
    factor: float
    decimals: int


# LOINC code -> conversion. Factors are the standard molar conversions.
CONVERSIONS: Dict[str, Conversion] = {
    # glucose: mg/dL -> mmol/L
    "2339-0": Conversion("mg/dL", "mmol/L", 0.0555, 1),
    "2345-7": Conversion("mg/dL", "mmol/L", 0.0555, 1),
    "1558-6": Conversion("mg/dL", "mmol/L", 0.0555, 1),
    "41653-7": Conversion("mg/dL", "mmol/L", 0.0555, 1),
    # lipids: mg/dL -> mmol/L
    "2093-3": Conversion("mg/dL", "mmol/L", 0.02586, 2),  # total cholesterol
    "2085-9": Conversion("mg/dL", "mmol/L", 0.02586, 2),  # HDL
    "18262-6": Conversion("mg/dL", "mmol/L", 0.02586, 2),  # LDL
    "13457-7": Conversion("mg/dL", "mmol/L", 0.02586, 2),  # LDL calculated
    "2571-8": Conversion("mg/dL", "mmol/L", 0.01129, 2),  # triglycerides
    # renal: creatinine mg/dL -> umol/L, urea nitrogen mg/dL -> urea mmol/L
    "2160-0": Conversion("mg/dL", "umol/L", 88.42, 0),
    "38483-4": Conversion("mg/dL", "umol/L", 88.42, 0),
    "6299-2": Conversion("mg/dL", "mmol/L", 0.357, 1),
    "3094-0": Conversion("mg/dL", "mmol/L", 0.357, 1),
    # electrolytes and minerals: mg/dL -> mmol/L
    "17861-6": Conversion("mg/dL", "mmol/L", 0.2495, 2),  # calcium
    "49765-1": Conversion("mg/dL", "mmol/L", 0.2495, 2),  # calcium
    "2777-1": Conversion("mg/dL", "mmol/L", 0.3229, 2),  # phosphate
    "19123-9": Conversion("mg/dL", "mmol/L", 0.4114, 2),  # magnesium
    # bilirubin: mg/dL -> umol/L
    "1975-2": Conversion("mg/dL", "umol/L", 17.104, 0),
    "42719-5": Conversion("mg/dL", "umol/L", 17.104, 0),
    "1968-7": Conversion("mg/dL", "umol/L", 17.104, 0),
    # uric acid: mg/dL -> umol/L
    "3084-1": Conversion("mg/dL", "umol/L", 59.48, 0),
    # iron and ferritin stay as reported by Synthea (ug/dL, ng/mL) because those units are
    # also used by South African laboratories.
}


def convert_quantity(code: str, value: float, unit: str) -> Optional[Tuple[float, str]]:
    """Return the converted ``(value, unit)`` or None when no conversion applies."""
    conversion = CONVERSIONS.get(code)
    if conversion is None or unit != conversion.source_unit:
        return None
    exact = Decimal(str(value)) * Decimal(str(conversion.factor))
    quantum = Decimal(1).scaleb(-conversion.decimals)
    converted = float(exact.quantize(quantum, rounding=ROUND_HALF_UP))
    return converted, conversion.target_unit
