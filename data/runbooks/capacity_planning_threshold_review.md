# Runbook: Transport Link Capacity Planning Threshold Review

**Runbook ID:** NOC-CAP-001  
**Version:** 1.6  
**Last Updated:** 2025-10-10  
**Owner:** Network Operations Centre — Capacity Planning  
**Classification:** Operational Review Procedure  

---

## Summary

This runbook defines the procedure for periodic review and adjustment of utilization thresholds on transport links in the optical and IP/MPLS backbone network. Utilization thresholds determine when capacity alarms fire and when augmentation planning is triggered. This is a **scheduled operational review activity**, not an incident response procedure.

Transport links carry aggregated customer and internal traffic between core routers, aggregation switches, and peering points. Each link has a configured capacity (e.g., 100 Gbps, 400 Gbps) and a set of utilization thresholds that generate alerts when traffic volume approaches capacity limits.

Incorrect thresholds cause two failure modes:
1. **Thresholds too low:** Excessive false alarms, alarm fatigue, NOC desensitisation — operators start ignoring capacity alerts.
2. **Thresholds too high:** Insufficient lead time for capacity augmentation — links congest before planning can provision additional capacity, causing packet loss and service degradation.

This review covers all backbone transport links, including:
- **LINK-SYD-MEL** (Sydney to Melbourne backbone, 4× 400G DWDM channels)
- **LINK-SYD-BNE** (Sydney to Brisbane backbone, 2× 400G DWDM channels)
- **LINK-MEL-ADL** (Melbourne to Adelaide backbone, 2× 100G DWDM channels)
- **LINK-SYD-CBR** (Sydney to Canberra regional link, 2× 100G DWDM channels)
- All metro aggregation links within the SYD, MEL, BNE metro areas

---

## Detection Criteria / Trigger

This is a scheduled activity. It is triggered by:

| Trigger | Frequency | Description |
|---|---|---|
| Quarterly capacity review cycle | Every 3 months | Standing review of all backbone link utilization against thresholds |
| Traffic growth exceeding forecast | Ad hoc | Actual traffic growth rate exceeds the planning forecast by >20% for any link |
| Post-augmentation threshold recalibration | After capacity addition | After new capacity is lit on a link (e.g., additional DWDM wavelength), thresholds must be recalculated for the new total capacity |
| Post-incident review recommendation | After capacity-related incident | A congestion incident identified threshold misconfiguration as a contributing factor |

---

## Procedure Steps

### Step 1 — Gather Current Utilization Data (Capacity Planner, Day 1)

1. Extract 90-day traffic utilization data for all in-scope transport links from the NMS or traffic analytics platform.
2. For each link, record:
   - **Link ID** (e.g., LINK-SYD-MEL)
   - **Link capacity** (total provisioned bandwidth in Gbps)
   - **Peak utilization (%)** — highest 5-minute average in the 90-day period (`UtilizationPct` peak)
   - **95th percentile utilization (%)** — the value below which 95% of all 5-minute samples fall
   - **Average utilization (%)** — mean of all 5-minute samples
   - **Growth rate (%)** — month-over-month change in 95th percentile utilization
   - **Current alarm thresholds** — Warning threshold (%) and Critical threshold (%)

**Example data extract:**

| Link ID | Capacity (Gbps) | Peak Util% | 95th% Util | Avg Util% | MoM Growth | Warn Thresh | Crit Thresh |
|---|---|---|---|---|---|---|---|
| LINK-SYD-MEL | 1600 | 72% | 58% | 41% | +3.2% | 70% | 85% |
| LINK-SYD-BNE | 800 | 65% | 49% | 33% | +2.8% | 70% | 85% |
| LINK-MEL-ADL | 200 | 81% | 67% | 48% | +4.1% | 70% | 85% |
| LINK-SYD-CBR | 200 | 45% | 32% | 22% | +1.5% | 70% | 85% |

### Step 2 — Assess Threshold Adequacy (Capacity Planner, Day 1–2)

For each link, evaluate whether the current thresholds provide adequate lead time for capacity augmentation:

1. **Calculate time-to-threshold** at the current growth rate:
   - Time to reach Warning threshold = `(Warn% - Current95th%) / MoM_Growth%` months
   - Time to reach Critical threshold = `(Crit% - Current95th%) / MoM_Growth%` months

2. **Minimum lead time requirements:**
   - Warning threshold must fire at least **6 months** before the link would reach 95% utilization at the current growth rate.
   - Critical threshold must fire at least **3 months** before the link would reach 95% utilization.
   - This accounts for the lead time needed to procure, install, and light additional DWDM wavelengths or deploy new fibre capacity.

3. **Flag links that violate lead time requirements:**
   - If time-to-warning < 6 months: threshold is too high, lower it.
   - If time-to-warning > 18 months: threshold may be too low, generating premature alarms.

**Example assessment for LINK-MEL-ADL:**
- Current 95th%: 67%, Warning threshold: 70%, Growth: 4.1%/month
- Time to Warning: (70 − 67) / 4.1 = 0.7 months — **CRITICAL: insufficient lead time**
- Recommendation: lower Warning threshold to 60%, Critical to 75%

### Step 3 — Propose Threshold Adjustments (Capacity Planner, Day 2)

1. For each link requiring adjustment, calculate new thresholds using the formula:
   - New Warning threshold = Current 95th% + (6 months × MoM Growth%)
   - New Critical threshold = Current 95th% + (3 months × MoM Growth%) + 10% buffer
   - Both thresholds capped at a maximum of 90% (absolute ceiling regardless of calculation).

2. Document the proposed changes in a threshold adjustment request:
   - Link ID
   - Current Warning / Critical thresholds
   - Proposed Warning / Critical thresholds
   - Justification (time-to-threshold calculation)
   - Risk assessment (does lowering the threshold increase alarm volume unacceptably?)

3. Submit the threshold adjustment request for peer review by a second capacity planner.

### Step 4 — Implement Approved Threshold Changes (NOC Tier 1, Day 3–5)

1. After peer review approval, implement the new thresholds in the NMS alarm configuration.
2. For each link:
   - Update the Warning utilization threshold (`UtilizationPct` Warning alarm)
   - Update the Critical utilization threshold (`UtilizationPct` Critical alarm)
   - Verify the alarm fires correctly by checking against current utilization (if current utilization exceeds the new Warning threshold, expect an immediate alarm — acknowledge it as part of the threshold change).
3. Update the capacity planning database with the new threshold values and the date of change.

### Step 5 — Augmentation Trigger Review (Capacity Planner, concurrent)

1. For any link where the current 95th percentile utilization already exceeds the new Warning threshold, immediately raise a capacity augmentation request:
   - Link ID and current utilization
   - Projected date to reach Critical threshold
   - Required additional capacity (number of DWDM wavelengths or new fibre pair)
   - Estimated cost and lead time for augmentation
2. Track augmentation requests in the capacity planning tracker.
3. After augmentation is completed, trigger a threshold recalibration for the augmented link (return to Step 1 for that link).

---

## Escalation

| Condition | Escalate To | Timeframe |
|---|---|---|
| Link utilization already exceeding Critical threshold at time of review | Transport Operations Manager — immediate congestion risk | Within 1 business day |
| Time-to-critical < 3 months and no augmentation path available | Network Planning Director — strategic capacity decision | Within 1 week |
| Threshold adjustment approval delayed beyond 5 business days | Capacity Planning Manager | Day 5 |
| Traffic growth rate exceeding forecast by > 50% (trend break) | Commercial / Product team — demand driver investigation | Next quarterly review |

---

## Expected Resolution Time

| Activity | Target Duration |
|---|---|
| Data extraction and analysis (Steps 1–2) | 1–2 business days |
| Threshold proposal and peer review (Step 3) | 1–2 business days |
| Threshold implementation (Step 4) | 1 business day |
| Full review cycle (all steps) | 3–5 business days |
| Augmentation request raised to capacity lit | 8–16 weeks (DWDM wavelength addition) |

---

## Key Definitions

| Term | Definition |
|---|---|
| UtilizationPct | The percentage of a link's provisioned capacity consumed by traffic, measured as a 5-minute average of input+output bits per second divided by link speed |
| 95th Percentile | The value below which 95% of all utilization samples fall over the measurement period — standard industry billing and planning metric |
| MoM Growth | Month-over-month growth rate in 95th percentile utilization, used for forecasting |
| Time-to-Threshold | The projected number of months until utilization reaches a given threshold at the current growth rate |

---

## Related Runbooks

- NOC-OPT-003: Fibre Cut — Span Loss Detection and Restoration (relevant when augmentation requires new fibre deployment)
- NOC-DWDM-012: DWDM Wavelength Rebalancing (required after adding new channels)
- NOC-PERF-002: Link Congestion — Traffic Engineering and Load Balancing
- NOC-CHANGE-001: Change Management — Standard Change Process

---

## Revision History

| Version | Date | Author | Change |
|---|---|---|---|
| 1.6 | 2025-10-10 | C. Zhao | Added LINK-SYD-CBR, updated example data, revised lead time formula |
| 1.5 | 2025-06-15 | N. Brooks | Added augmentation trigger review step |
| 1.4 | 2025-03-01 | C. Zhao | Updated growth rate calculation methodology |
| 1.3 | 2024-11-20 | N. Brooks | Added 90% absolute ceiling to threshold calculation |
| 1.2 | 2024-08-01 | C. Zhao | Added peer review requirement for threshold changes |
| 1.1 | 2024-04-15 | N. Brooks | Added key definitions section |
| 1.0 | 2024-01-05 | C. Zhao | Initial version |
