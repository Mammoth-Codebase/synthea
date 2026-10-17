# Packaged South African reference data

* `names.yml`: name pools per language (and race sub pools), generated from `data_src/names`.
* `languages.json`: first language weights per population group, nationally and per
  province (Census 2022). Race keys follow Synthea: black = Black African, white = White,
  asian = Indian or Asian, other = Coloured. Languages listed in
  `geography/foreign_birthplace.json` mark people born outside South Africa.
* `language_lookup.json`: BCP 47 codes for each language.
* `immunization_schedule.json`: the Expanded Programme on Immunisation (EPI-SA) schedule as
  revised in 2015, with ages in months (1.5 is six weeks), using CVX codes.
* `geography/`, `providers/`, `payers/`, `costs/`: see the README files in each folder.
* `modules/lookup_tables/`: South African calibration tables for the HIV modules.
* `local_modules/`: generic modules added or replaced for South Africa (tuberculosis, ART).
* `module_overrides.properties`: numeric overrides applied to built in modules.
* `templates/notes/note.ftl`: clinical note wording for South Africa.
* `synthea_za.properties`: the Synthea configuration used for every run.

Edit the sources in `synthea-za/data_src` and run `python -m synthea_za.build_data`.
