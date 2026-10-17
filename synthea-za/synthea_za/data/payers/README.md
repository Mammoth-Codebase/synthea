Payers model the South African funding landscape: the public sector (National
Department of Health, free at the point of care and used by about 84% of the
population) and the largest open and restricted medical schemes. Premiums are
monthly amounts in US dollars because Synthea's cost model is dollar based; the
post-processing step converts money to rand. Scheme membership is limited by
affordability (`generate.payers.insurance_plans.income_premium_ratio`) and the
acceptance likelihood in `insurance_eligibilities.csv`, which together give
roughly a sixth of the population scheme cover.
