Geography files use Synthea's column layout:

* `demographics.csv`: one row per town with population, sex, population group
  (WHITE, BLACK, ASIAN = Indian/Asian, OTHER = Coloured; HISPANIC and NATIVE are 0),
  eighteen five-year age bands, household income bands (thousands of US dollars per
  year, see `synthea_za.properties`) and education (LESS_THAN_HS = no matric,
  HS_DEGREE = matric, SOME_COLLEGE = certificate or diploma, BS_DEGREE = degree).
* `zipcodes.csv`: four digit postal codes with coordinates per town.
* `sdoh.csv`: social determinants per district or metropolitan municipality.
* `timezones.csv`, `fipscodes.csv` (empty, FIPS codes are a US concept) and
  `foreign_birthplace.json` (languages whose speakers are born outside South Africa).

These files are generated from the per-province sources in `synthea-za/data_src`
by `python -m synthea_za.build_data`.
