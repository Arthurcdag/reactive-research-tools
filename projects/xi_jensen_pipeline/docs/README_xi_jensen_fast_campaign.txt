Fast campaign runner for xi_jensen_fast_experiments
===================================================

Why this exists
---------------
The optimized fast path is now the correct engine for larger experiments.
This script turns the extended presets into a batch campaign you can leave
running and inspect later.

Campaigns
---------
- core:
  - client_full
  - c070_extended
  - c060_extended

- threshold:
  - threshold_band_extended

- all:
  - client_full
  - c070_extended
  - c060_extended
  - threshold_band_extended

Outputs
-------
For each preset:
- a CSV
- a `.summary.json`

For the whole campaign:
- `xi_jensen_campaign_<name>.json`
- `xi_jensen_campaign_<name>.md`

Examples
--------
Run the core campaign:
    python xi_jensen_fast_campaign.py --campaign core

Run everything, but skip targeted high-precision verification:
    python xi_jensen_fast_campaign.py --campaign all --no-verify-sensitive
