# Runbook: Power Outage — Remote Shelter UPS Failure and Generator Switchover

**Runbook ID:** NOC-PWR-007  
**Version:** 2.3  
**Last Updated:** 2025-11-14  
**Owner:** Network Operations Centre — Power & Facilities  
**Classification:** Standard Operating Procedure  

---

## Summary

This runbook covers the response procedure when a remote outdoor shelter or roadside cabinet experiences a UPS failure, resulting in loss of mains power to hosted network equipment. The procedure addresses battery rundown detection, automatic transfer switch (ATS) verification, and portable generator deployment for shelters without permanent standby generation.

Remote shelters such as **CORE-SYD-01 shelter** house critical optical transport equipment including DWDM amplifiers, optical line terminals, and router line cards. A sustained power outage at these sites will cause **optical power loss across all hosted transport links**, triggering downstream alarms that may initially appear indistinguishable from a fibre cut or cable damage event. It is essential to confirm power status before escalating as a transport fault.

---

## Detection Criteria

The following alarm conditions indicate a remote shelter power event rather than a fibre or transport fault:

| Alarm Source | Alarm Type | Severity | Description |
|---|---|---|---|
| Shelter BMS | `ENV-PWR-MAINS-FAIL` | Critical | Mains supply lost at shelter AC input panel |
| UPS Controller | `UPS-BATTERY-LOW` | Major | UPS battery below 20% remaining capacity |
| UPS Controller | `UPS-BYPASS-ACTIVE` | Warning | UPS has switched to bypass mode (no battery protection) |
| Shelter BMS | `ENV-ATS-TRANSFER-FAIL` | Critical | Automatic transfer switch failed to engage generator |
| NMS (optical) | `OPT-RX-POWER-LOW` on multiple ports | Major | Optical receive power dropped below −28 dBm threshold on all links terminating at this shelter |
| NMS (transport) | `LINK-DOWN` on multiple links | Critical | Multiple transport links down simultaneously at a single site |

**Key Differentiator from Fibre Cut:**  
A fibre cut typically affects a **single span** or a subset of links sharing a common cable route. A power outage at a shelter causes **all links terminating at that shelter** to fail simultaneously. If CORE-SYD-01 shelter loses power, every optical interface on equipment hosted in that shelter will report optical power loss — not just one span.

Check the shelter BMS dashboard before raising a fibre cut ticket. If `ENV-PWR-MAINS-FAIL` is present, follow this runbook.

---

## Procedure Steps

### Step 1 — Confirm Power Outage (NOC Tier 1, 0–5 min)

1. Open the Building Management System (BMS) dashboard for the affected shelter.
2. Verify `ENV-PWR-MAINS-FAIL` alarm is active on the shelter AC input panel.
3. Check UPS status: remaining battery percentage, estimated runtime, load in kVA.
4. Confirm whether the ATS has attempted generator engagement (check `ENV-ATS-TRANSFER` event log).
5. Cross-reference with the electricity distributor's outage map to determine whether the mains failure is a utility fault or a site-specific issue (e.g., breaker trip, fuse failure).

### Step 2 — Assess Impact Window (NOC Tier 1, 5–10 min)

1. Determine UPS remaining runtime at current load.
2. If runtime > 60 minutes, proceed to Step 3 (generator dispatch) with standard priority.
3. If runtime < 30 minutes, escalate generator dispatch to emergency priority and notify the Transport Operations desk that links hosted at this shelter will drop within 30 minutes.
4. If UPS has already exhausted and equipment is down, skip to Step 4 (impact assessment).

### Step 3 — Generator Deployment (Field Operations, 10–120 min)

1. Raise a field dispatch ticket with the following details:
   - Shelter ID and physical address
   - Generator connection type (single-phase / three-phase, connector type)
   - Required generator capacity (minimum kVA rating from shelter power profile)
   - Access requirements (keys, security PIN, escort needed)
2. Field technician arrives on site, connects portable generator to the shelter external generator input socket.
3. Technician verifies ATS transfers load to generator supply.
4. Technician confirms equipment is powering up and optical interfaces are restoring.

### Step 4 — Impact Assessment and Service Restoration (NOC Tier 2, concurrent)

1. Identify all transport links terminating at the affected shelter using the NMS topology view.
2. For each link, check optical receive power levels are returning to nominal (typically −8 dBm to −18 dBm for amplified spans).
3. Monitor for links that do not restore after power is confirmed — these may indicate equipment damage from the power event (PSU failure, line card failure) and require separate fault tickets.
4. Verify BGP/OSPF/IS-IS adjacencies re-establish on all router interfaces hosted at the shelter.
5. Confirm customer-facing services traversing restored links are operational (check customer CPE reachability, run service-level ping tests).

### Step 5 — Root Cause and Permanent Fix (Engineering, next business day)

1. Determine whether the mains failure was a utility outage or a site fault.
2. If site fault: dispatch electrician to inspect breakers, fuses, AC wiring, and ATS mechanism.
3. If UPS batteries failed to provide rated runtime, schedule battery replacement.
4. If ATS failed to engage the permanent generator (for sites with standby generation), schedule ATS maintenance.
5. Update the shelter power profile in the asset database with actual battery runtime observed.

---

## Escalation

| Condition | Escalate To | Timeframe |
|---|---|---|
| UPS runtime < 30 min, no generator available within 30 min | Transport Operations Manager | Immediate |
| Equipment fails to restore after power is confirmed | Hardware Engineering (line card / PSU replacement) | Within 15 min of power confirmation |
| Mains failure duration > 4 hours and no permanent generator on site | Facilities Engineering — permanent generator installation review | Next business day |
| Customer SLA breach due to power-related outage | Service Management — SLA breach notification | Within 30 min of breach threshold |

---

## Expected Resolution Time

| Scenario | Target Resolution |
|---|---|
| UPS holds, generator deployed before battery exhaustion | 60–120 min (no service impact) |
| UPS exhausted, generator deployed, equipment auto-recovers | 120–180 min |
| UPS exhausted, equipment requires manual restart after power restore | 180–240 min |
| Equipment damaged by power event (PSU/line card failure) | 4–8 hours (hardware replacement) |

---

## Related Runbooks

- NOC-OPT-003: Fibre Cut — Span Loss Detection and Restoration
- NOC-ENV-002: Shelter Environmental Alarm — Temperature Exceedance
- NOC-HW-011: Router Line Card Replacement — CORE Platform

---

## Revision History

| Version | Date | Author | Change |
|---|---|---|---|
| 2.3 | 2025-11-14 | J. Tan | Added ATS failure detection criteria, updated generator dispatch procedure |
| 2.2 | 2025-06-01 | M. Chen | Added CORE-SYD-01 shelter-specific notes |
| 2.1 | 2025-02-10 | J. Tan | Updated UPS runtime thresholds |
| 2.0 | 2024-09-15 | K. Patel | Major revision — added BMS integration steps |
| 1.0 | 2024-03-01 | J. Tan | Initial version |
