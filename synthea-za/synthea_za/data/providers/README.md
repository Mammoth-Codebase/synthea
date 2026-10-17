# Facilities

One CSV per facility kind, merged from `data_src/providers/<CODE>_<kind>.csv` by
`python -m synthea_za.build_data` (ids are renumbered from 100 so they are unique across
kinds). Columns follow Synthea's provider files:

| column | content |
| --- | --- |
| `id` | numeric facility id (used for the organisation identifier) |
| `name` | facility name (letters, spaces and hyphens only) |
| `address`, `city`, `state`, `zip` | street, town (must exist in `geography/zipcodes.csv`), province name, postal code |
| `phone` | `0XX XXX XXXX` |
| `ownership` | `Government` or `Private` |
| `emergency` | `Yes` or `No` (adds the emergency service) |
| `lat`, `lon` | coordinates used for nearest facility selection |

Kinds: `hospitals.csv` (inpatient, outpatient, ambulatory), `primary_care.csv` (clinics
and community health centres: wellness visits, immunisations), `urgent_care.csv`,
`dialysis.csv`, `home_health.csv`, `hospice.csv`, `nursing.csv`. `veterans.csv` is header
only because Synthea always loads it and South Africa has no veterans facilities.
