# Cost adjustments

Synthea prices every encounter, procedure, medication, lab, device and supply in US dollars
from its built in cost tables. These files scale those prices per province
(`STATE,ADJ_FACTOR`, with an extra `ENCOUNTER` column for encounter classes) before the
post-processor converts the amounts to rand with `--zar-per-usd`. Factors above one make a
province more expensive than the national average (Gauteng, Western Cape private care);
factors below one make it cheaper (rural provinces).
