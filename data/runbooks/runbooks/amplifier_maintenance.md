# Optical Amplifier Maintenance and Degradation Response

## Purpose
Guide assessment and response when optical amplifier degradation is detected or suspected on long-haul fibre links.

## Symptoms
- Gradual optical power drop on a transport link (e.g., from -3 dBm to -15 dBm over days/weeks)
- Increasing bit error rate (BER) without sudden loss-of-light
- Latency increase on long-haul links

## Procedure
1. **Identify the affected link** and query its amplifier sites (AmplifierSite → amplifies → TransportLink)
2. **Check last calibration dates** for each amplifier on the link
3. **Correlate with telemetry:** Is the optical power degradation gradual (amplifier aging) or sudden (fibre event)?
4. **If gradual:** Schedule field maintenance for recalibration. Priority based on link criticality.
5. **If sudden:** This is NOT an amplifier issue — investigate fibre cut or splice degradation.

## Calibration Schedule
- Amplifiers should be recalibrated every 6 months
- If LastCalibration > 6 months ago AND optical power is dropping: HIGH priority recalibration
- If LastCalibration > 12 months ago: CRITICAL — schedule immediately regardless of current readings

## Escalation
- If multiple amplifiers on the same route show degradation: possible environmental issue (temperature, water ingress in conduit)
- If degradation rate suggests failure within 7 days: pre-emptive traffic reroute + emergency field dispatch
