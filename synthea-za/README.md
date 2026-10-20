# synthea-za: South African synthetic patient population

`synthea-za` generates a demo population that resembles South Africa: its people, names,
languages, towns, health facilities, funders and disease burden. It is built on the
[Synthea](https://github.com/synthetichealth/synthea) patient simulator that lives in the
parent directory of this project and writes FHIR R4 transaction bundles that can be loaded
into InterSystems HealthShare (or any FHIR R4 server).

Each patient carries up to ten years of history ending today (older chronic conditions and
medications that are still active are kept), simulated from birth so that chronic diseases
progress realistically.

## What is South African about the output

| Area | How it is modelled |
| --- | --- |
| Demographics | Statistics South Africa Census 2022: nine provinces, about 440 towns, suburbs, townships and rural municipalities with population, sex, age structure, population group (Black African, Coloured, Indian or Asian, White), household income and education per town. Patients are allocated to provinces in proportion to population. |
| Names | Name pools per home language (isiZulu, isiXhosa, Sepedi, Sesotho, Setswana, Xitsonga, siSwati, Tshivenda, isiNdebele, Afrikaans, English) with separate pools for Indian and Coloured South Africans and for migrant communities (Shona, Portuguese, Chichewa, French). Names contain only letters, spaces and hyphens: no digits or symbols. Clinicians are named the same way. |
| Languages | First language is drawn per population group and province (Census 2022) and exported as a BCP 47 code (for example `zu`, `xh`, `af`, `en-ZA`). Speakers of migrant languages are born abroad. |
| Addresses | South African street names, four digit postal codes, province in the address, country `ZA`, coordinates inside the town. |
| Identifiers | A valid 13 digit South African identity number (Luhn check digit, gender sequence, citizenship digit) replaces the US social security number; passports use the `A12345678` format; practitioners carry HPCSA style registration numbers. |
| Facilities | Real public hospitals (central, tertiary, regional and district), clinics and community health centres, plus realistic private hospitals, day hospitals, renal units, hospices, frail care homes and home nursing agencies in every province, each with a South African telephone number. |
| Funders | The public sector (National Department of Health, free at the point of care) covers most people; the largest open and restricted medical schemes cover roughly a sixth of the population, limited by affordability. Money is converted to rand. |
| Disease burden | HIV calibrated to the South African epidemic (Thembisa/UNAIDS shape: diagnoses at AIDS stage before 2004, the 2010 to 2015 testing surge, women diagnosed younger, falling mortality, continuous ART for most people after 2016) with South African regimens (d4T/3TC/EFV, TDF/3TC/EFV, TEE, TLD); a new tuberculosis module (Xpert MTB/RIF diagnosis, RHZE/RH treatment, HIV co-infection, drug resistant disease, loss to follow up, recurrence, death); hypertension and diabetes prevalence by population group; injury and opioid rates; smoking and alcohol; the EPI-SA immunisation schedule (BCG, OPV, hexavalent, PCV, measles, Td, HPV). |
| Units | Common chemistry results are converted to SI units (mmol/L, umol/L). |

## Calibration targets

The disease calibration was set against published South African figures (web research
summarised in the generator and module files):

| Indicator | Target used | Source |
| --- | --- | --- |
| HIV prevalence, all ages, 2022 | 12.7% (women 16.4%, men 8.8%; women 35-39 about 34%) | HSRC SABSSM VI |
| HIV: diagnosed, on ART among diagnosed, 2024 | 95%, 81.5% | Thembisa 4.8 |
| First line ART by period | d4T/3TC/EFV 2004, TDF/3TC/EFV 2010, TEE 2013, TLD Dec 2019 | National guidelines |
| TB incidence | about 1 000 per 100 000 in 2008, 427 in 2023; 54% of TB patients HIV positive | WHO Global TB Report |
| TB outcomes (drug sensitive) | 83% success, 8% died, 9% lost to follow up; RR-TB 3.5% of new cases | NDoH cohort 2023 |
| Hypertension, adults 15+ | 46% of women, 44% of men | SADHS 2016 |
| Diabetes by population group | Black African 8.9%, Coloured 9.9%, White 16%, Indian 32% | SANHANES-1 |
| Current smoking | 21% of adults, applied as 35% of men and 8% of women | GATS 2021 |
| Medical scheme cover | about 15% of the population | Council for Medical Schemes 2023 |
| Homicide and road deaths | 37-44 and 19 per 100 000 | SAMRC, RTMC |

Synthea reproduces these as emergent properties of the simulation, so a generated corpus
approximates them rather than matching them exactly; `summary.md` reports what was produced.

## Requirements

* Python 3.9 or newer (no third party packages are required at run time).
* Java 17 or newer (JDK) on the `PATH`, or `--java` pointing at one.
* The Synthea checkout this project lives in (`../`), built with Gradle. The first run
  builds `build/libs/synthea-with-dependencies.jar` automatically (several minutes, needs
  internet access for Gradle dependencies), or run `synthea-za build-jar` beforehand.

## Quick start

On a Mac or Linux machine the bundled script does everything (finds or installs Java and
Python, builds the jar on the first run and generates a corpus):

```bash
git clone https://github.com/Mammoth-Codebase/synthea.git
cd synthea
git checkout claude/sa-synthea-population-generator-gu33o7
synthea-za/run_local.sh 200 ~/sa-corpus          # patients, output directory
```

The script also works on its own: saved anywhere outside a checkout, it clones the branch
into `~/synthea` (or `REPO_DIR`) first.

`EXTRA_ARGS="--province GP --csv" ./run_local.sh 50` passes extra generate options,
`INSTALL_DEPS=1` lets it install a missing JDK or Python with Homebrew, and setting
`HEALTHSHARE_URL` with `HEALTHSHARE_USER`/`HEALTHSHARE_PASSWORD` (or `HEALTHSHARE_TOKEN`)
loads the result into HealthShare afterwards. The header of the script lists every option.

By hand:

```bash
cd synthea-za
pip install -e .                 # installs the synthea-za command (or use python -m synthea_za)

synthea-za generate --patients 200 --output ./output
```

This produces:

```
output/
  fhir/                        one transaction bundle per patient plus
                               hospitalInformation_<province>.json and
                               practitionerInformation_<province>.json
  manifest.json                what was run (seeds, provinces, timings, post-processing)
  summary.md / summary.json    corpus summary: sex, age bands, provinces, languages,
                               funders, prevalence of tracked conditions, resource counts
```

Useful options:

```
synthea-za generate -p 1000 -s 42                     # reproducible seed
synthea-za generate -p 50 --province Gauteng          # one province (name or code)
synthea-za generate -p 20 --province WC --city "Khayelitsha"
synthea-za generate -p 100 --age-range 18-65 --gender F --only-alive
synthea-za generate -p 100 --years-of-history 5 --reference-date 20241231
synthea-za generate -p 100 --clinical-notes --csv     # also notes and Synthea CSV tables
synthea-za generate -p 100 --jobs 3                   # simulate three provinces at once
synthea-za generate -p 100 --property generate.middle_names=0.3
synthea-za generate -p 100 --keep-raw                 # keep Synthea's raw output and logs
synthea-za generate -p 100 --keep-old-deaths          # also export people who died before the window
```

`--patients` is the number of living patients. Synthea also simulates people who died
along the way; those who died inside the history window are exported too (they make
realistic recent deaths), while people who died before the window are left out unless
`--keep-old-deaths` is given, because their records would be almost empty.

Post-processing switches: `--no-national-id`, `--national-id-system URI`,
`--practitioner-system URI`, `--mrn-system URI`, `--keep-drivers-licence`, `--no-phones`,
`--currency USD` (leave money unchanged), `--zar-per-usd 18.5`, `--no-si-units`,
`--meta-tag synthetic`. Run `synthea-za generate --help` for the full list.

## Loading into HealthShare

The bundles are FHIR R4 transaction bundles. Patient bundles use `urn:uuid` references
internally and conditional `Organization?identifier=...` and `Practitioner?identifier=...`
references to the facility and practitioner bundles, so those two bundles must be loaded
first and the server must support conditional references in transactions (HealthShare
does). They can be posted to the FHIR server base URL of a HealthShare Unified Care Record
or HealthShare Health Connect FHIR endpoint. Post the organisation and practitioner bundles
first, then the patients:

```bash
synthea-za load ./output/fhir --url https://healthshare.example/csp/healthshare/hsfhir/fhir/r4 \
    --username superuser --password '...'
synthea-za load ./output/fhir --url ... --token "$BEARER" --dry-run
```

Bundles range from a few hundred kilobytes to tens of megabytes (patients on long term
dialysis or oncology care carry tens of thousands of resources); raise the server's request
size limit or time-out if large bundles are rejected, or generate with `--only-alive` and a
shorter `--years-of-history` for a lighter corpus.

Patients carry a medical record number (`MR`, Synthea's `http://hospital.smarthealthit.org`
system unless `--mrn-system` is set) and the South African ID number (`NNZAF`, system
`http://www.dha.gov.za/identity-number` by default). Configure the matching assigning
authorities in HealthShare before loading if you want them indexed by the patient index.

## Other commands

```
synthea-za provinces                       # population weights per province
synthea-za validate-data                   # validate the packaged reference data
synthea-za validate-part names data_src/names/zulu.yml
synthea-za postprocess raw_fhir_dir out_dir --label GP
synthea-za report ./output/fhir [--json]
synthea-za build-jar
```

## How it works

1. `synthea_za/overlay.py` assembles a classpath overlay from `synthea_za/data` (names,
   languages, geography, providers, payers, costs, templates, HIV lookup tables) and writes a
   properties file. Because Synthea reads resources through the classpath, the overlay placed
   ahead of the jar replaces the US data without rebuilding Synthea.
2. `synthea_za/runner.py` runs Synthea once per province with the overlay, the South African
   local modules (`-d synthea_za/data/local_modules`: tuberculosis, HIV diagnosis, ART
   regimens) and `module_overrides.properties` (numeric overrides for hypertension, diabetes,
   injuries and opioids). US only modules (veterans) are excluded.
3. `synthea_za/postprocess.py` rewrites the bundles: identity numbers, passports, HPCSA
   numbers, telephone numbers, rand, SI units.
4. `synthea_za/report.py` summarises the corpus.

The Synthea fork in the parent directory carries small, backwards compatible changes that
make this possible: name pools per language and population group (`Names.java`), a
configurable first language distribution and an honoured Coloured population column
(`Demographics.java`), configurable smoking and alcohol probabilities (overall or per sex)
and no repeated middle names (`LifecycleModule.java`), clinicians named from the
population group of their facility's town (`Provider.java`), rounded `SetAttribute`
distributions stored as integers (`State.java`), numeric observation values of any type in
the exporters (`ExportHelper.java`) and an optional `gender` key in the immunisation
schedule (`Immunizations.java`). The defaults keep Synthea's US behaviour; `git log --
src/main/java` lists every change. The jar is rebuilt automatically when it is older than
these sources.

## Editing the reference data

Sources live in `data_src/` (one file per language pool, per province and per facility
kind) and are merged into `synthea_za/data` with:

```bash
python -m synthea_za.build_data
```

Disease calibration lives in `tools/make_hiv_tables.py` (HIV lookup tables) and
`tools/make_tb_module.py` (tuberculosis module); run them after changing parameters.
`tools/localise_builtin_modules.py` copies built in Synthea submodules that hard code US
assumptions (the social needs screening's refugee question) into the local modules with
South African values; rerun it after updating Synthea.

## Tests

```bash
pip install -e .[dev]
pytest
```

The Java changes are covered by `NamesTest` and `DemographicsTest` in the Synthea test suite.

## Limitations

* Synthea's clinical modules are US sourced; apart from the calibrations above (HIV, TB,
  hypertension, diabetes, injuries, opioids, smoking, alcohol, immunisations) the natural
  history of other conditions follows the US modules.
* Costs are Synthea's US cost model converted at a fixed exchange rate.
* Towns and facilities are a representative sample, not a complete gazetteer; coordinates
  are approximate. Private facility names are realistic but invented.
