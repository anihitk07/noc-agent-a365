# Runbook: DWDM Wavelength Rebalancing — Channel Plan Adjustment for Capacity Growth

**Runbook ID:** NOC-DWDM-012  
**Version:** 1.4  
**Last Updated:** 2025-10-22  
**Owner:** Network Operations Centre — Transport Engineering  
**Classification:** Planned Engineering Activity  

---

## Summary

This runbook defines the procedure for rebalancing DWDM (Dense Wavelength Division Multiplexing) channel plans on optical transport links to accommodate capacity growth, wavelength additions, or amplifier gain profile adjustments. This is a **planned engineering activity**, not an incident response procedure.

When new wavelengths are provisioned on an existing optical span, the per-channel optical power levels must be rebalanced to ensure all channels fall within the receiver sensitivity window and do not cause nonlinear impairment (e.g., four-wave mixing, cross-phase modulation). This involves adjusting Variable Optical Attenuators (VOAs), EDFA gain tilt, and per-channel power targets across the span.

Rebalancing activities will cause **transient optical power fluctuations** on existing channels. During the adjustment window, NMS alarms for optical power deviation (both high and low) are expected. These alarms must be suppressed or acknowledged to prevent false escalation as fibre degradation or fibre cut events.

---

## Detection Criteria / Trigger

This is a planned activity. It is triggered by:

| Trigger | Source | Description |
|---|---|---|
| Capacity augmentation request | Transport Planning | New wavelengths to be lit on an existing span |
| Amplifier replacement | Hardware Engineering | New EDFA installed with different gain profile requiring channel rebalancing |
| Optical power drift | NMS monitoring | Per-channel power levels drifting outside ±1.5 dB of target over time, requiring recalibration |
| Span loss change | Transport Engineering | Fibre span loss changed (e.g., after fibre splice repair), requiring power plan recalculation |

**Pre-requisite:** A Change Request (CR) must be approved before executing this procedure. No rebalancing activity shall be performed outside of the approved maintenance window.

---

## Procedure Steps

### Step 1 — Pre-Change Baseline (Transport Engineer, T−60 min)

1. Record current per-channel optical power levels at the transmit side (Tx dBm) and receive side (Rx dBm) for every active wavelength on the target span.
2. Record current EDFA input power, output power, and gain for each amplifier site in the span (inline amplifiers, pre-amplifiers, booster amplifiers).
3. Record current VOA attenuation settings at the ROADM or terminal multiplexer.
4. Capture OSNR (Optical Signal-to-Noise Ratio) readings for each channel at the receive terminal.
5. Save baseline data to the change record for post-change comparison.

**Example baseline for a Sydney–Melbourne span:**

| Channel | Wavelength (nm) | Tx Power (dBm) | Rx Power (dBm) | OSNR (dB) |
|---|---|---|---|---|
| CH-21 | 1550.12 | +1.0 | −14.2 | 28.5 |
| CH-22 | 1550.52 | +1.0 | −14.5 | 28.1 |
| CH-23 | 1550.92 | +1.0 | −14.8 | 27.8 |
| CH-24 | 1551.32 | — (new) | — | — |

### Step 2 — NMS Alarm Suppression (NOC Tier 1, T−15 min)

1. Apply alarm suppression window in the NMS for the target span:
   - Suppress `OPT-RX-POWER-LOW` and `OPT-RX-POWER-HIGH` alarms on all interfaces of the affected transport link.
   - Suppress `OPT-SPAN-LOSS-CHANGE` alarms on the affected span.
   - Set suppression duration to cover the approved maintenance window plus 30-minute buffer.
2. Notify the NOC watch desk that transient optical alarms on this span are expected during the maintenance window.
3. Ensure the real fibre cut detection runbook (NOC-OPT-003) is not triggered by these expected power excursions — add a note to the active alarm summary.

### Step 3 — Channel Addition and Power Adjustment (Transport Engineer, T+0)

1. If adding a new wavelength:
   a. Configure the new transponder with the target channel frequency and Tx power from the channel plan.
   b. Enable the wavelength on the ROADM at the add/drop ports.
   c. Verify the new channel is visible on the optical spectrum analyser (OSA) at the receive terminal.

2. Adjust per-channel VOA settings at the transmit ROADM to achieve the target per-channel power plan:
   - Target per-channel power at EDFA input: as specified in the span engineering design (typically −2 dBm to +2 dBm per channel).
   - All channels must be within ±0.5 dB of each other at the EDFA input to achieve flat gain across the amplifier bandwidth.

3. Adjust EDFA gain if the total channel count has changed:
   - For EDFAs in AGC (Automatic Gain Control) mode: verify gain target matches the new total channel power requirement.
   - For EDFAs in APC (Automatic Power Control) mode: adjust the output power target to accommodate the new channel count.

4. Iterate VOA adjustments until all channels at the receive terminal are within the target Rx power window (typically −12 dBm to −18 dBm for 100G coherent receivers).

### Step 4 — Post-Change Verification (Transport Engineer, T+30 min to T+60 min)

1. Record per-channel Rx power and OSNR at the receive terminal. Compare with baseline.
2. Verify all channels are within the receiver sensitivity window:
   - Rx power: within −10 dBm to −20 dBm (coherent receiver range varies by vendor).
   - OSNR: minimum 18 dB for 100G DP-QPSK, minimum 22 dB for 400G 64-QAM.
3. Verify pre-FEC BER (Bit Error Rate) on all channels is below threshold (typically < 1×10⁻³ for soft-decision FEC).
4. Verify post-FEC BER is error-free on all channels.
5. Monitor for 30 minutes for stability — no power oscillation, no FEC error bursts.

### Step 5 — Alarm Restoration and Closeout (NOC Tier 1, T+60 min)

1. Remove alarm suppression window from the NMS.
2. Verify no standing alarms on the span after suppression is removed.
3. If new alarm thresholds are required for the rebalanced channel plan, update the NMS alarm threshold profile for the span.
4. Close the change record with post-change power readings attached.

---

## Escalation

| Condition | Escalate To | Timeframe |
|---|---|---|
| Unable to achieve target Rx power within ±2 dB after 30 min of adjustment | Senior Transport Engineer | During maintenance window |
| OSNR below minimum threshold on any channel after rebalancing | Optical Design Engineering — span redesign may be required | Within 1 hour |
| Existing traffic-carrying channels experience post-FEC errors during rebalancing | NOC Tier 2 — assess customer impact and consider rollback | Immediate |
| Rebalancing cannot be completed within the approved maintenance window | Change Manager — request window extension or schedule continuation | 30 min before window close |

---

## Expected Resolution Time

| Scenario | Target Duration |
|---|---|
| Single channel addition, minor rebalancing | 60–90 min |
| Multiple channel additions (3–5 channels) | 90–150 min |
| Full channel plan rebuild (amplifier replacement) | 3–5 hours |
| Complex multi-span rebalancing (cascaded amplifier adjustment) | 4–8 hours (may require multiple maintenance windows) |

---

## Key Reference Values

| Parameter | Typical Range | Notes |
|---|---|---|
| Per-channel Tx power | −2 dBm to +3 dBm | Varies by channel plan and span loss |
| Per-channel Rx power (coherent) | −10 dBm to −22 dBm | Below −28 dBm triggers `OPT-RX-POWER-LOW` |
| EDFA output power (per amp) | +17 dBm to +23 dBm total | Depends on channel count |
| Span loss budget | 0.25 dB/km fibre + splice/connector loss | Recalculate if fibre route changed |
| OSNR minimum (100G) | 18 dB | At receiver, after all amplifier noise contributions |

---

## Related Runbooks

- NOC-OPT-003: Fibre Cut — Span Loss Detection and Restoration
- NOC-DWDM-008: EDFA Amplifier Replacement Procedure
- NOC-DWDM-015: Optical Spectrum Analyser — Remote Monitoring Setup
- NOC-CAP-001: Transport Link Capacity Planning Threshold Review

---

## Revision History

| Version | Date | Author | Change |
|---|---|---|---|
| 1.4 | 2025-10-22 | S. Nguyen | Added 400G OSNR thresholds, updated alarm suppression procedure |
| 1.3 | 2025-07-01 | R. Kumar | Added multi-span rebalancing guidance |
| 1.2 | 2025-03-15 | S. Nguyen | Clarified VOA adjustment iteration process |
| 1.1 | 2024-11-01 | S. Nguyen | Added pre-FEC BER verification step |
| 1.0 | 2024-06-10 | R. Kumar | Initial version |
