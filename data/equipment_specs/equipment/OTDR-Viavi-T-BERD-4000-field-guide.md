# Field Guide — Viavi T-BERD 4000 OTDR

**Document ID:** EQ-FG-001  
**Applies to:** Viavi T-BERD/MTS 4000 platform with fibre optic test module  
**Revision:** 3.2 — 2026-01-20  
**Author:** Network Test Engineering, Optical Transport Group

---

## 1. Pre-Test Setup

### Power On and Self-Test

1. Press and hold the power button for 2 seconds. The unit performs a 30-second self-test including laser calibration.
2. Verify the calibration status indicator shows green. If amber, the unit requires recalibration — do not use for acceptance testing.
3. Confirm the software version is 8.40 or later (Settings → About). Earlier versions have a known bug in automatic event detection for short dead zones.

### Fibre Connection

1. Clean the OTDR port with a 2.5mm fibre cleaning stick before every connection. Inspect with fibre microscope if available.
2. Attach a launch fibre reel (minimum 500m for standard testing, 1km recommended for DWDM spans). The launch fibre eliminates the OTDR dead zone and allows measurement of the first connector.
3. Connect the launch fibre to the fibre under test. Use SC/APC connectors for all single-mode testing on the Sydney–Melbourne corridor (network standard).

### Test Parameters

| Parameter | Standard Test | High-Resolution | DWDM Span |
|-----------|--------------|-----------------|-----------|
| Wavelength | 1550nm | 1550nm | 1550nm + 1625nm |
| Pulse Width | 1μs | 100ns | 1μs |
| Range | 120km | 20km | 120km |
| Averaging Time | 60s | 30s | 180s |
| Resolution | 8m | 0.8m | 8m |

For the Sydney–Melbourne backbone, always test at both 1550nm (in-service wavelength) and 1625nm (bend-loss sensitive) to detect macrobend issues.

---

## 2. Trace Interpretation

### Normal Trace Characteristics

A healthy 80km amplifier span on the Sydney–Melbourne corridor (G.652D fibre) should show:

- **Fibre attenuation:** 0.19–0.22 dB/km at 1550nm (typical: 0.20 dB/km)
- **Total span loss:** 15.2–17.6 dB for an 80km span (fibre + splices)
- **Splice events:** spaced every 4–6 km (cable drum lengths), loss ≤0.05 dB each
- **Connector events:** at patch panels only (amplifier sites), reflectance ≤-55 dB for APC connectors

### Common Failure Patterns

#### Fibre Break (Complete)
- **Trace signature:** Sudden drop to noise floor with high Fresnel reflection (≥-20 dB) at the break point.
- **Interpretation:** Clean break, often caused by dig-up or cable cut. The reflection peak indicates an air-glass interface.
- **Action:** Record distance to break. Cross-reference with cable route GIS to identify the physical location. Dispatch field crew with splice kit.

#### Fibre Break (Crush/Bend)
- **Trace signature:** Elevated loss (>1 dB) at the event, possibly with attenuation slope increase after the event. No strong reflection. 1625nm trace shows significantly higher loss than 1550nm at the same point.
- **Interpretation:** Macrobend or crush damage. The fibre is not severed but is damaged.
- **Action:** Compare 1550nm and 1625nm traces. If 1625nm loss exceeds 1550nm loss by >0.5 dB at the event, macrobend is confirmed.

#### Degraded Splice
- **Trace signature:** Splice event loss exceeds 0.1 dB. May appear as a step in the trace rather than a spike.
- **Interpretation:** Fusion splice has degraded, possibly due to mechanical stress, moisture ingress, or original splice quality.
- **Action:** Log the splice location and loss. Schedule re-splice if loss exceeds 0.15 dB or if cumulative span loss is out of budget.

#### Connector Contamination
- **Trace signature:** Elevated reflectance (>-45 dB) at a connector event, with insertion loss >0.5 dB.
- **Interpretation:** Dirty or damaged connector end-face.
- **Action:** Clean and re-test. If reflectance remains high after cleaning, inspect with fibre microscope and replace connector if scratched.

---

## 3. Maintenance Schedule

| Task | Frequency | Performed By |
|------|-----------|--------------|
| Full calibration (NMI-traceable) | Every 12 months | National Measurement Institute or accredited lab |
| Port cleaning and inspection | Before every test session | Field technician |
| Software update check | Monthly | Depot coordinator |
| Battery health check | Quarterly | Depot coordinator |
| Launch fibre reel inspection | Before every test session | Field technician |

### Battery

- The T-BERD 4000 lithium-ion battery provides approximately 8 hours of continuous testing.
- Charge fully before field deployment. Carry the vehicle charger (12V adapter) for extended sessions.
- Replace battery when capacity drops below 60% of rated (observable as <5 hours runtime). Order part: Viavi TBERD-4000-BATT.

---

## 4. Data Management

- Save all traces in SOR format (Bellcore standard) for compatibility with Viavi FiberChek and third-party analysis tools.
- Naming convention: `YYYY-MM-DD_SPAN-ID_WAVELENGTH_DIRECTION.sor` (e.g., `2026-02-28_AMP-SYD-MEL-02-to-03_1550nm_AB.sor`).
- Upload traces to the fibre records database within 24 hours of completion.
- Baseline traces for each span are stored in the fibre records database under the span ID. Always compare current traces against baseline to detect degradation trends.
