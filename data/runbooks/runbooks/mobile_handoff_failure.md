# Runbook: 5G NR Inter-Cell Handoff Failure — Radio Layer Troubleshooting

**Runbook ID:** NOC-RAN-034  
**Version:** 2.0  
**Last Updated:** 2025-12-01  
**Owner:** Network Operations Centre — Radio Access Network  
**Classification:** Standard Operating Procedure  

---

## Summary

This runbook covers the diagnosis and resolution of 5G NR (New Radio) inter-cell handover failures, where User Equipment (UE) fails to successfully transition from a serving cell to a target cell during mobility events. Handover failures result in call drops, session interruptions, and degraded customer experience for mobile subscribers.

Handover failures manifest at the **radio access layer** and involve the gNodeB (gNB) base stations that manage the air interface. This procedure applies to handover failures between cells served by the following gNodeBs in the Sydney metropolitan coverage area:

- **GNB-SYD-2041** (CBD North sector)
- **GNB-SYD-2042** (CBD South sector)
- **GNB-SYD-2043** (Inner West sector)
- **GNB-SYD-2044** (Eastern Suburbs sector)
- **GNB-SYD-2045** (North Shore sector)

Handover failures are a **radio layer problem** — they are caused by RF coverage gaps, interference, incorrect neighbour relations, timing advance mismatches, or gNodeB software issues. They do **not** indicate transport network faults (fibre cuts, optical link failures, or backhaul outages), although transport problems can sometimes cause symptoms that appear similar to handover failures when the X2/Xn interface between gNodeBs is disrupted.

---

## Detection Criteria

| Metric Source | Indicator | Threshold | Description |
|---|---|---|---|
| RAN Performance Counters | Handover Success Rate (HOSR) | < 95% (4-hour rolling) | Ratio of successful handovers to attempted handovers for a cell pair |
| RAN Performance Counters | Handover Failure Rate | > 5% (4-hour rolling) | Percentage of handover attempts resulting in RLF (Radio Link Failure) |
| RAN Performance Counters | Too-Early Handover Count | > 10/hour per cell pair | UE returns to source cell after handover — indicates target cell signal too weak |
| RAN Performance Counters | Too-Late Handover Count | > 10/hour per cell pair | UE experiences RLF before handover command — indicates handover trigger too late |
| UE Measurement Reports | A3 Event Report Anomalies | N/A | UE reporting target cell RSRP/RSRQ values inconsistent with RF propagation model |
| Customer Complaints | Call drops during travel on specific routes | > 3 complaints same route/hour | Correlated complaints indicating systematic handover failure along a mobility path |

**Key Differentiator from Transport Fault:**  
A transport fault (e.g., fibre cut on the gNodeB backhaul link) would cause the **entire gNodeB** to become unreachable from the core network, resulting in all UEs on that gNodeB losing service simultaneously — not just UEs performing handover. Check the gNodeB backhaul link status (SCTP association to AMF/CU) before investigating radio layer causes. If the backhaul is down, follow the transport fault runbook instead.

---

## Procedure Steps

### Step 1 — Identify Affected Cell Pairs (NOC Tier 1, 0–15 min)

1. Open the RAN Performance Management dashboard.
2. Filter for cells with HOSR below 95% in the last 4 hours.
3. Identify the specific cell pair(s) exhibiting handover failures:
   - Source cell (serving cell before handover)
   - Target cell (cell the UE is attempting to hand over to)
4. Note the gNodeB IDs and cell IDs involved. Example:
   - Source: GNB-SYD-2041, Cell 1 (sector α, Band n78)
   - Target: GNB-SYD-2042, Cell 3 (sector γ, Band n78)
5. Check whether the failure is unidirectional (A→B fails, B→A succeeds) or bidirectional.

### Step 2 — Confirm Transport Layer Health (NOC Tier 1, 15–20 min)

1. Verify the backhaul links for both source and target gNodeBs are operational:
   - SCTP association between gNodeB CU and AMF: status `ESTABLISHED`
   - F1 interface between gNodeB CU and DU: status `UP`
   - X2/Xn interface between source and target gNodeBs: status `UP`
2. Check for recent transport alarms affecting gNodeB backhaul paths:
   - Fibre cut alarms on the fronthaul/midhaul/backhaul spans
   - Optical power loss on links serving the gNodeB site
   - Ethernet CRC errors or packet loss on backhaul interfaces
3. If any transport layer fault is found, escalate to Transport Operations and follow the relevant transport runbook. Do not continue with radio troubleshooting until transport is confirmed healthy.

### Step 3 — Analyse Handover Parameters (RAN Engineer, 20–45 min)

1. Review the handover configuration for the affected cell pair:
   - A3 offset (dB): the RSRP difference threshold that triggers handover measurement reporting
   - Time-to-Trigger (TTT): how long the A3 condition must persist before handover is initiated
   - Hysteresis (dB): additional margin to prevent ping-pong handovers
2. Compare current parameter values with the network standard configuration template.
3. Check for recent parameter changes (CRs, optimisation tool adjustments) that may have altered handover behaviour.
4. Analyse the handover failure type:
   - **Too-Early HO:** target cell signal degrades rapidly after handover — may need to increase A3 offset or TTT.
   - **Too-Late HO:** UE experiences RLF before handover triggers — may need to decrease A3 offset or TTT.
   - **HO to Wrong Cell:** UE hands over to a cell that is not the optimal target — check neighbour relation table (NRT) and measurement configuration.

### Step 4 — RF Analysis (RAN Engineer, 45–90 min)

1. Review RF coverage predictions for the area between source and target cells.
2. Check for RF anomalies:
   - Antenna tilt changes (mechanical or electrical) that may have altered coverage footprint
   - New buildings or structures causing RF shadowing since the cell was last optimised
   - External interference detected on the operating band (n78, n258, etc.)
   - Antenna hardware faults (VSWR alarm, RET motor failure, feeder damage)
3. If antenna hardware fault is suspected, dispatch a field technician to inspect the antenna system at the gNodeB site.
4. If interference is detected, use the RAN management system's interference detection feature to identify the source and mitigate (frequency retuning, beam adjustment).

### Step 5 — Parameter Adjustment and Verification (RAN Engineer, 90–150 min)

1. Based on the analysis in Steps 3–4, implement parameter corrections:
   - Adjust A3 offset, TTT, or hysteresis values for the affected cell pair.
   - Update the Neighbour Relation Table if missing or incorrect neighbour entries are found.
   - Adjust antenna electrical tilt if coverage gap is identified.
2. Monitor the HOSR for the affected cell pair for the next 2 hours after parameter change.
3. Target: HOSR should recover to > 98% within 2 hours of adjustment.
4. If HOSR does not recover, escalate to RAN Design Engineering for detailed drive test and RF survey.

---

## Escalation

| Condition | Escalate To | Timeframe |
|---|---|---|
| HOSR < 90% for any cell pair | RAN Operations Manager | Within 30 min |
| Handover failure correlated with transport backhaul fault | Transport Operations — fibre/backhaul investigation | Immediate |
| Antenna hardware fault confirmed (VSWR, RET, feeder) | Field Maintenance — antenna repair/replacement | Within 2 hours |
| HOSR does not recover after parameter adjustment | RAN Design Engineering — drive test required | Within 4 hours |
| Handover failures affecting emergency services coverage | RAN Operations Manager + Regulatory Affairs | Immediate |

---

## Expected Resolution Time

| Scenario | Target Resolution |
|---|---|
| Parameter misconfiguration (A3 offset, TTT) — correction applied | 1–2 hours |
| Missing neighbour relation — NRT updated | 1–2 hours |
| Antenna tilt drift — electrical tilt adjusted remotely | 2–3 hours |
| Antenna hardware fault — field repair required | 4–8 hours |
| RF coverage gap due to new construction — permanent solution (new cell, repeater) | 2–6 weeks (interim mitigation within 24 hours) |

---

## Related Runbooks

- NOC-RAN-031: gNodeB Site Outage — Complete Service Loss at Cell Site
- NOC-RAN-037: 5G NR Throughput Degradation — Interference Analysis
- NOC-TRANSPORT-003: gNodeB Backhaul Link Failure — Fronthaul/Midhaul/Backhaul Restoration
- NOC-OPT-003: Fibre Cut — Span Loss Detection and Restoration

---

## Revision History

| Version | Date | Author | Change |
|---|---|---|---|
| 2.0 | 2025-12-01 | P. Wong | Added X2/Xn interface check, updated GNB-SYD-204x references |
| 1.2 | 2025-08-15 | D. Kim | Added too-early/too-late handover classification |
| 1.1 | 2025-04-01 | P. Wong | Added interference detection guidance |
| 1.0 | 2024-10-20 | D. Kim | Initial version |
