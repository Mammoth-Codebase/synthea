"""Conversion of common laboratory results from US conventional units to SI units.

Synthea records many chemistry results in mg/dL (or g/dL). South African laboratories
report these analytes in mmol/L, umol/L or g/L. LOINC codes are property specific, so an
analyte converted from a mass concentration to a molar concentration also receives the
matching [Moles/volume] LOINC code and display. Only observations whose LOINC code appears
in this table and whose unit matches the expected source unit are converted; everything
else is left untouched.

The molar codes below are the standard LOINC counterparts of Synthea's mass codes; analytes
whose molar code could not be confirmed (for example urea nitrogen in whole blood) are left
in their original units rather than mislabelled.
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
    target_code: Optional[str] = None  # LOINC code for the converted property, if it changes
    target_display: Optional[str] = None


# LOINC code -> conversion. Factors are the standard molar conversions.
CONVERSIONS: Dict[str, Conversion] = {
    # glucose: mg/dL -> mmol/L
    "2339-0": Conversion("mg/dL", "mmol/L", 0.0555, 1, "15074-8", "Glucose [Moles/volume] in Blood"),
    "2345-7": Conversion("mg/dL", "mmol/L", 0.0555, 1, "14749-6", "Glucose [Moles/volume] in Serum or Plasma"),
    "1558-6": Conversion("mg/dL", "mmol/L", 0.0555, 1, "14771-0", "Fasting glucose [Moles/volume] in Serum or Plasma"),
    "41653-7": Conversion("mg/dL", "mmol/L", 0.0555, 1, "14743-9", "Glucose [Moles/volume] in Capillary blood by Glucometer"),
    # lipids: mg/dL -> mmol/L
    "2093-3": Conversion("mg/dL", "mmol/L", 0.02586, 2, "14647-2", "Cholesterol [Moles/volume] in Serum or Plasma"),
    "2085-9": Conversion("mg/dL", "mmol/L", 0.02586, 2, "14646-4", "Cholesterol in HDL [Moles/volume] in Serum or Plasma"),
    "18262-6": Conversion("mg/dL", "mmol/L", 0.02586, 2, "22748-8", "Cholesterol in LDL [Moles/volume] in Serum or Plasma by Direct assay"),
    "13457-7": Conversion("mg/dL", "mmol/L", 0.02586, 2, "39469-2", "Cholesterol in LDL [Moles/volume] in Serum or Plasma by calculation"),
    "2571-8": Conversion("mg/dL", "mmol/L", 0.01129, 2, "14927-8", "Triglyceride [Moles/volume] in Serum or Plasma"),
    # renal: creatinine mg/dL -> umol/L, urea nitrogen mg/dL -> mmol/L
    "2160-0": Conversion("mg/dL", "umol/L", 88.42, 0, "14682-9", "Creatinine [Moles/volume] in Serum or Plasma"),
    "38483-4": Conversion("mg/dL", "umol/L", 88.42, 0, "59826-8", "Creatinine [Moles/volume] in Blood"),
    "3094-0": Conversion("mg/dL", "mmol/L", 0.357, 1, "14937-7", "Urea nitrogen [Moles/volume] in Serum or Plasma"),
    # electrolytes and minerals: mg/dL -> mmol/L
    "17861-6": Conversion("mg/dL", "mmol/L", 0.2495, 2, "2000-8", "Calcium [Moles/volume] in Serum or Plasma"),
    "2777-1": Conversion("mg/dL", "mmol/L", 0.3229, 2, "14879-1", "Phosphate [Moles/volume] in Serum or Plasma"),
    "19123-9": Conversion("mg/dL", "mmol/L", 0.4114, 2, "2601-3", "Magnesium [Moles/volume] in Serum or Plasma"),
    # bilirubin and urate: mg/dL -> umol/L
    "1975-2": Conversion("mg/dL", "umol/L", 17.104, 0, "14631-6", "Bilirubin.total [Moles/volume] in Serum or Plasma"),
    "1968-7": Conversion("mg/dL", "umol/L", 17.104, 0, "14629-0", "Bilirubin.direct [Moles/volume] in Serum or Plasma"),
    "3084-1": Conversion("mg/dL", "umol/L", 59.48, 0, "14933-6", "Urate [Moles/volume] in Serum or Plasma"),
    # proteins: g/dL -> g/L (the property stays a mass concentration, so the code is kept)
    "1751-7": Conversion("g/dL", "g/L", 10.0, 0),
    "2885-2": Conversion("g/dL", "g/L", 10.0, 0),
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


def converted_code(code: str) -> Optional[Tuple[str, str]]:
    """The LOINC ``(code, display)`` that describes the converted property, if it changes."""
    conversion = CONVERSIONS.get(code)
    if conversion is None or conversion.target_code is None:
        return None
    return conversion.target_code, conversion.target_display or ""
