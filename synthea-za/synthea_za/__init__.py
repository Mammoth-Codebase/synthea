"""South African synthetic population generator built on Synthea.

The package assembles a South African resource overlay (names, languages,
geography, providers, payers, disease calibration) on top of the Synthea
patient simulator, runs Synthea once per province, and post-processes the
resulting FHIR R4 transaction bundles so that identifiers, telephone numbers,
currency and laboratory units look like South African data.
"""

__version__ = "0.1.0"
