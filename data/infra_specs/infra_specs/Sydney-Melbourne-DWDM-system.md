# System Specification — Sydney–Melbourne DWDM Corridor

**Document ID:** INFRA-DWDM-001  
**System Name:** Sydney–Melbourne Dense Wavelength Division Multiplexing (DWDM) System  
**Revision:** 5.1 — 2026-01-10  
**Owner:** Optical Transport Engineering

---

## 1. System Overview

The Sydney–Melbourne DWDM system is a 96-channel dense wavelength division multiplexing optical transport system connecting the Sydney Exchange (Global Switch, Ultimo) to the Melbourne Exchange (NextDC M1, Clayton) via a terrestrial fibre route following the Hume Highway corridor.

| Parameter | Value |
|-----------|-------|
| Total Route Length | 880 km (fibre distance, including cable slack loops) |
| Number of Amplifier Sites | 5 (AMP-SYD-MEL-01 through AMP-SYD-MEL-05) |
| Number of DWDM Channels | 96 (C-band, ITU-T 50GHz grid) |
| Channel Spacing | 50 GHz (0.4nm) |
| Wavelength Range | 1530.33nm – 1567.95nm (C-band) |
| Per-Channel Data Rate | 100 Gbps (DP-QPSK modulation) |
| System Capacity | 9.6 Tbps aggregate (96 × 100G) |
| Currently Lit Channels | 72 of 96 (75% utilisation as of 2026-02-01) |
| Fibre Type | Corning SMF-28e+ (ITU-T G.652D) |
| Cable Construction | 96-fibre loose-tube, gel-filled, armoured |

---

## 2. Amplifier Spacing and Span Budget

The DWDM system uses Erbium-Doped Fibre Amplifiers (EDFAs) to compensate for fibre attenuation. Amplifier sites are spaced at approximately 80km intervals.

| Span | From | To | Distance (km) | Span Loss (dB) | Last Measured |
|------|------|----|---------------|-----------------|---------------|
| Span 1 | Sydney Exchange | AMP-SYD-MEL-01 | 42 | 9.2 | 2025-11-15 |
| Span 2 | AMP-SYD-MEL-01 | AMP-SYD-MEL-02 | 78 | 16.8 | 2025-11-15 |
| Span 3 | AMP-SYD-MEL-02 | AMP-SYD-MEL-03 | 82 | 17.4 | 2025-11-15 |
| Span 4 | AMP-SYD-MEL-03 | AMP-SYD-MEL-04 | 80 | 16.9 | 2025-11-15 |
| Span 5 | AMP-SYD-MEL-04 | AMP-SYD-MEL-05 | 85 | 17.8 | 2025-11-16 |
| Span 6 | AMP-SYD-MEL-05 | Melbourne Exchange | 78 | 16.2 | 2025-11-16 |
| **Total** | | | **445 (one-way fibre pair)** | **94.3** | |

**Note:** Total route length of 880km includes both directions plus cable slack loops at each amplifier site (approximately 200m of slack per site).

---

## 3. Optical Power Budget

| Parameter | Specification |
|-----------|--------------|
| EDFA Output Power (total) | +17 dBm |
| Per-Channel Launch Power | -3 dBm (nominal at 96 channels) |
| Per-Channel Launch Power Range | -6 dBm to +3 dBm (adjustable via NMS) |
| Receiver Sensitivity | -28 dBm (at BER 1×10⁻³, pre-FEC) |
| Maximum Span Loss (budget) | 22 dB (includes 3 dB system margin) |
| System Margin | 3 dB (allocated for ageing, repair splices, and connector degradation) |
| OSNR Requirement | ≥18 dB (per channel, at receiver) |

### Power Budget Implications

- The maximum allowable span loss is 22 dB (19 dB fibre + splice loss + 3 dB margin).
- Span 5 (Yass–Albury, 85km, 17.8 dB) is the tightest span, with only 4.2 dB of remaining margin. Any degradation on this span (additional repair splices, connector contamination, or fibre ageing) should be monitored.
- If span loss exceeds 19 dB (exhausting all but 3 dB margin), a maintenance action is required. If span loss exceeds 22 dB, channels will begin to drop below receiver sensitivity.

---

## 4. Channel Plan

Channels are assigned on the ITU-T 50GHz grid. The first 72 channels (currently lit) carry the following traffic:

| Channel Block | Channels | Service |
|---------------|----------|---------|
| Ch 1–32 | 1530.33–1543.73nm | Enterprise IP transit (Tier 1 customers) |
| Ch 33–48 | 1544.13–1550.12nm | Wholesale ethernet services |
| Ch 49–64 | 1550.52–1556.55nm | Internet peering and CDN backhaul |
| Ch 65–72 | 1556.96–1559.79nm | Internal network backbone (MPLS) |
| Ch 73–96 | 1560.20–1567.95nm | **Unlit — spare capacity** |

Channel 65–72 carry the MPLS backbone traffic, including the primary path MPLS-PRIMARY-01 and associated signalling. Loss of these channels triggers MPLS failover to MPLS-BACKUP-02 (see MPLS backup path design document).

---

## 5. Maintenance Windows

| Window | Day | Time (AEST) | Scope |
|--------|-----|-------------|-------|
| Planned Maintenance | Tuesday | 02:00–06:00 | Non-traffic-affecting: firmware updates, filter cleaning, OTDR testing |
| Planned Maintenance | Thursday | 02:00–06:00 | Traffic-affecting permitted: channel provisioning, EDFA gain adjustment, splice repair |
| Emergency Maintenance | Any day | NOC approval required | Fault restoration — no window restriction for P1/P2 faults |

### Maintenance Rules

1. All planned maintenance must be logged in the NMS maintenance scheduler at least 48 hours in advance.
2. Traffic-affecting work (anything that may cause channel drops or power fluctuations) is restricted to Thursday windows unless classified as emergency.
3. OTDR testing at any amplifier site may cause transient power fluctuations on monitor ports. Notify the NOC before connecting OTDR equipment.
4. After any splice repair or connector replacement, verify per-channel OSNR at the receiving terminal via the NMS before closing the maintenance ticket.

---

## 6. Alarm Thresholds

| Alarm | Warning (Minor) | Alert (Major) | Critical |
|-------|----------------|---------------|----------|
| Per-channel power (low) | < -5 dBm | < -8 dBm | < -12 dBm |
| Per-channel power (high) | > +1 dBm | > +3 dBm | > +5 dBm |
| OSNR | < 22 dB | < 20 dB | < 18 dB |
| Span loss increase | > 1 dB above baseline | > 2 dB above baseline | > 3 dB above baseline |
| EDFA temperature | > 45°C | > 50°C | > 55°C |
| EDFA pump laser current | > 90% rated | > 95% rated | > 98% rated |

---

## 7. Redundancy and Protection

- The DWDM system operates in a **1+0 (unprotected)** configuration at the optical layer. There is no optical-layer protection switching.
- Traffic protection is provided at the MPLS/IP layer via MPLS-BACKUP-02 (diverse route via Canberra).
- If the DWDM system experiences a total failure (e.g., fibre cut severing all channels), traffic is rerouted via the MPLS backup path. See the MPLS backup path design document for capacity limitations and failover behaviour.
