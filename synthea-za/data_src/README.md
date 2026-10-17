# Source data for the South African population

Human editable sources merged into `synthea_za/data` by

    cd synthea-za && python -m synthea_za.build_data

## names/

One YAML file per language pool, e.g. `zulu.yml`:

    zulu:
      M: [Sipho, Thabo, ...]
      F: [Nomvula, Lerato, ...]
      family: [Dlamini, Nkosi, ...]

`english.yml` and `afrikaans.yml` also carry race specific sub pools (`asian` for
Indian South Africans, `other` for Coloured South Africans); the `black` sub pool is
derived automatically from the African language pools. Names may only contain
letters, spaces and hyphens: no digits, apostrophes or other symbols.
`street.yml` holds street names and street types.

## geography/

Per province (code GP, KZN, WC, EC, LP, MP, NW, FS, NC):

* `<CODE>_demographics.csv`: Synthea demographics columns, one row per town.
* `<CODE>_zipcodes.csv`: `,USPS,ST,NAME,ZCTA5,LAT,LON` with four digit postal codes.
* `<CODE>_sdoh.csv`: social determinants per district or metro.

## providers/

Per province and facility kind: `<CODE>_hospitals.csv`, `<CODE>_primary_care.csv`,
`<CODE>_urgent_care.csv` (required) and optionally `<CODE>_dialysis.csv`,
`<CODE>_hospice.csv`, `<CODE>_nursing.csv`, `<CODE>_home_health.csv`. Columns:

    id,name,address,city,state,zip,phone,ownership,emergency,lat,lon

`id` may be any unique string within the file; ids are renumbered when merged.

Validate a single file while editing with

    python -m synthea_za validate-part <kind> <file> [--province "Gauteng"]
