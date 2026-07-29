# Po Sweep Droplet Summary

Source: `data/stage_timings.csv`

Filter used: `ContPhase = SDS`, `DispPhase = SO`, `Qw = 5 mL/hr`. The matching rows contain `Po = 200, 300, 400, 600 mbar`; no `500 mbar` rows were present in this filtered CSV subset.

| Po (mbar) | Droplet diameter (um) | Diameter CV | n droplets | Device frequency (Hz) | Output at 11,500 DFUs (mL/hr) | n DFUs |
|---:|---:|---:|---:|---:|---:|---:|
| 200 | 25.23 +/- 0.50 | 2.0% | 23 | 1.24 | 0.43 | 10 |
| 300 | 24.89 +/- 0.54 | 2.2% | 16 | 2.09 | 0.70 | 5 |
| 400 | 24.76 +/- 0.38 | 1.5% | 13 | 2.98 | 0.98 | 5 |
| 600 | 25.67 +/- 0.78 | 3.0% | 14 | 4.25 | 1.56 | 5 |

Variance method: droplet spread is the sample standard deviation of `Droplet_diameter_um` across valid measured droplets at each Po; CV is `SD / mean`.

Frequency method: per event, `Hz = 1 / (Stage1_s + Stage2_s + Stage3_s)`. Device frequency is the mean of each recorded DFU position's mean Hz, so DFU positions are weighted equally.

Output method: droplets were treated as spheres, with `V_drop = pi/6 * diameter^3`. Total output is `V_drop * Hz * 11,500 DFUs`.

Interpretation: the device is rate-tunable while remaining size-stable. Increasing `Po` gives the expected monotonic frequency increase, while droplet diameter stays near 25-26 um with low CV. From 300 to 600 mbar, frequency increases 2.0x and estimated output increases 2.2x, while mean diameter shifts by only 0.78 um.
