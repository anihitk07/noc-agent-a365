# Runbook: Environmental Humidity Alert — Data Centre Humidity Exceedance

**Runbook ID:** NOC-ENV-005  
**Version:** 1.3  
**Last Updated:** 2025-11-20  
**Owner:** Network Operations Centre — Facilities & Environmental  
**Classification:** Standard Operating Procedure  

---

## Summary

This runbook covers the response procedure when environmental humidity sensors in data centre facilities or equipment rooms report readings outside the acceptable operating range. High humidity increases the risk of condensation on electronic components, leading to short circuits, corrosion, and accelerated hardware degradation. Low humidity increases the risk of electrostatic discharge (ESD), which can damage sensitive optical and electronic components.

Data centre facilities housing critical network infrastructure must maintain humidity within ASHRAE A1 recommended ranges. Equipment hosted in these facilities includes core routers, optical transport platforms, DWDM terminals, and switching infrastructure.

**Affected Sites and Equipment:**

The following sites have experienced humidity exceedance events in the past 12 months and are subject to enhanced monitoring:

| Site | Equipment Hosted | Humidity Sensor Count | Notes |
|---|---|---|---|
| SYD-DC-01, Hall B | **CORE-SYD-01**, DWDM terminals, aggregation switches | 12 sensors (6 hot aisle, 6 cold aisle) | CORE-SYD-01 is a critical backbone router; humidity damage to this device would impact all transport links originating from Sydney |
| SYD-DC-01, Hall C | Edge routers, customer CPE hosting | 8 sensors | Lower criticality — customer-facing but not backbone |
| MEL-DC-02, Hall A | CORE-MEL-01, DWDM terminals | 10 sensors | Melbourne backbone node |
| BNE-DC-01, Hall A | CORE-BNE-01, aggregation | 6 sensors | Brisbane backbone node |

**Key Distinction from Other Alarms:**  
Humidity alarms are **environmental sensor alarms** — they indicate a problem with the data centre climate control system, not with the network equipment itself. A humidity exceedance does not cause immediate network faults (no link down, no optical power loss, no BGP session drops). However, sustained humidity outside the acceptable range will cause progressive hardware damage. The urgency is in preventing damage, not in responding to an existing outage.

Do not confuse humidity alarms with optical power alarms, temperature alarms, or equipment fault alarms. Check the alarm source — if it originates from the BMS (Building Management System) environmental sensor subsystem and references `%RH` (relative humidity), it is a humidity event. If it references `dBm`, `°C`, or equipment fault codes, it is a different alarm type.

---

## Detection Criteria

| Alarm Source | Alarm Type | Threshold | Severity | Description |
|---|---|---|---|---|
| BMS Humidity Sensor | `ENV-HUMIDITY-HIGH-WARN` | > 60% RH | Warning | Relative humidity exceeds upper warning threshold |
| BMS Humidity Sensor | `ENV-HUMIDITY-HIGH-CRIT` | > 70% RH | Critical | Relative humidity exceeds upper critical threshold — condensation risk |
| BMS Humidity Sensor | `ENV-HUMIDITY-LOW-WARN` | < 30% RH | Warning | Relative humidity below lower warning threshold |
| BMS Humidity Sensor | `ENV-HUMIDITY-LOW-CRIT` | < 20% RH | Critical | Relative humidity below lower critical threshold — ESD risk |
| BMS Humidity Sensor | `ENV-HUMIDITY-SENSOR-FAIL` | N/A | Major | Humidity sensor offline or returning invalid readings |
| BMS Humidity Trend | `ENV-HUMIDITY-RATE-OF-CHANGE` | > 10% RH/hour | Warning | Rapid humidity change — may indicate CRAC unit failure or water ingress |

**ASHRAE A1 Recommended Operating Ranges:**

| Parameter | Recommended Range | Allowable Range |
|---|---|---|
| Relative Humidity | 40%–55% RH | 20%–80% RH (non-condensing) |
| Dew Point | 5.5°C–15°C | −12°C–21°C |
| Temperature | 18°C–27°C | 15°C–32°C |

---

## Procedure Steps

### Step 1 — Confirm Humidity Exceedance (NOC Tier 1, 0–10 min)

1. Open the BMS dashboard for the affected data centre site and hall.
2. Identify which humidity sensors are reporting exceedance:
   - Sensor location (hot aisle / cold aisle, row number, rack position)
   - Current reading (% RH)
   - Trend (rising / falling / stable)
   - Duration of exceedance
3. Determine whether the exceedance is localised (single sensor or sensor cluster) or hall-wide:
   - **Localised:** may indicate a sensor fault, localised water leak, or a single CRAC (Computer Room Air Conditioning) unit failure.
   - **Hall-wide:** indicates a systemic HVAC issue — multiple CRAC units affected or outside air humidity intrusion.
4. Check for correlated temperature alarms. Humidity and temperature are coupled — a CRAC failure will often cause both temperature rise and humidity exceedance simultaneously.

### Step 2 — Assess Risk to Equipment (NOC Tier 1, 10–15 min)

1. **High humidity (> 60% RH):**
   - Check dew point relative to equipment surface temperatures. If the dew point is within 3°C of any equipment inlet temperature, condensation is possible.
   - Identify the highest-criticality equipment in the affected zone. For SYD-DC-01 Hall B, this is **CORE-SYD-01** — a backbone router whose failure would impact all Sydney-originating transport links.
   - If condensation is actively forming (facilities staff visual confirmation), escalate immediately to Critical.

2. **Low humidity (< 30% RH):**
   - Assess ESD risk. Low humidity + high foot traffic = elevated ESD risk.
   - If facilities or engineering staff must enter the affected area, enforce ESD precautions: wrist straps, ESD-safe footwear, anti-static mats.
   - Restrict non-essential access to the affected hall until humidity is restored.

3. **Rapid rate of change (> 10% RH/hour):**
   - Investigate immediately — rapid humidity increase may indicate water ingress (roof leak, pipe burst, CRAC condensate drain overflow).
   - Rapid humidity decrease typically indicates dry outside air being drawn in (economiser mode failure, door seal failure).

### Step 3 — HVAC Investigation and Remediation (Facilities Engineering, 15–60 min)

1. Check CRAC unit status for all units serving the affected hall:
   - Operating mode (cooling / heating / humidifying / dehumidifying)
   - Compressor status (running / standby / fault)
   - Fan status (running / fault)
   - Humidifier status (active / standby / fault / water supply fault)
   - Dehumidifier status (if equipped)

2. **If CRAC unit fault is identified:**
   - Attempt CRAC unit restart via BMS (remote power cycle).
   - If CRAC does not recover, dispatch facilities maintenance technician.
   - Assess whether remaining CRAC units can maintain acceptable humidity with the failed unit offline (redundancy check — N+1 or N+2 configuration).

3. **If water ingress is suspected (high humidity, rapid increase):**
   - Dispatch facilities staff immediately for visual inspection.
   - Identify water source: roof, pipe, CRAC condensate drain, water-cooled door coil.
   - Deploy containment (drip trays, barriers) to protect equipment from water contact.
   - If water is reaching equipment racks, initiate emergency equipment protection procedure (cover equipment with anti-static waterproof sheeting, assess shutdown of at-risk devices).

4. **If low humidity is caused by economiser mode malfunction:**
   - Switch CRAC units from economiser mode to mechanical cooling mode.
   - Close outside air dampers.
   - Activate humidifiers if equipped.

### Step 4 — Monitor Recovery (NOC Tier 1, 60–180 min)

1. After HVAC remediation action, monitor humidity sensors for the affected zone.
2. Humidity should return to the recommended range (40%–55% RH) within 60 minutes of CRAC remediation.
3. If humidity has not returned to range within 120 minutes, escalate to Senior Facilities Engineer.
4. Once humidity is stable within the recommended range for 30 consecutive minutes, close the environmental alert.
5. Check all equipment in the affected zone for signs of condensation damage:
   - Visual inspection of optical connectors (fogging, water droplets).
   - Check for new hardware fault alarms on equipment hosted in the affected zone (CORE-SYD-01 line card errors, PSU faults, optic transceiver errors).
   - If any equipment faults are found that may be humidity-related, raise separate hardware fault tickets.

### Step 5 — Root Cause and Prevention (Facilities Engineering, next business day)

1. Determine the root cause of the humidity exceedance:
   - CRAC unit mechanical failure (compressor, fan, humidifier, condensate pump)
   - Building envelope breach (roof leak, wall seal failure, door seal degradation)
   - HVAC control system misconfiguration (setpoint error, economiser logic fault)
   - External weather event (extreme ambient humidity overwhelming HVAC capacity)
2. Implement corrective action and document in the facilities maintenance log.
3. If the root cause is a recurring issue, raise a capital project request for HVAC system upgrade or building envelope repair.
4. Verify humidity sensor calibration in the affected zone (sensors may need recalibration after exposure to extreme humidity).

---

## Escalation

| Condition | Escalate To | Timeframe |
|---|---|---|
| Humidity > 70% RH (critical threshold) | Facilities Engineering Manager | Immediate |
| Active condensation on equipment | Data Centre Operations Manager + NOC Manager | Immediate |
| Water ingress detected in equipment hall | Emergency response — facilities and NOC | Immediate |
| CORE-SYD-01 or other backbone equipment at risk of humidity damage | Transport Operations Manager (equipment protection / controlled shutdown decision) | Within 15 min |
| Humidity not recovered after 120 min of remediation | Senior Facilities Engineer | At 120 min mark |
| Low humidity < 20% RH with engineering access required | ESD Safety Officer | Before personnel entry |

---

## Expected Resolution Time

| Scenario | Target Resolution |
|---|---|
| Single CRAC unit fault, redundant units maintaining partial control | 30–60 min (CRAC restart or switchover) |
| CRAC mechanical failure requiring technician | 2–4 hours |
| Water ingress — contained, source isolated | 1–3 hours (containment) + repair timeline varies |
| Economiser mode malfunction — mode switch | 15–30 min |
| Building envelope breach — temporary seal | 2–4 hours (temporary), weeks–months (permanent repair) |

---

## Related Runbooks

- NOC-ENV-002: Shelter Environmental Alarm — Temperature Exceedance
- NOC-ENV-003: Data Centre Environmental Alarm — Temperature Exceedance
- NOC-PWR-007: Power Outage — Remote Shelter UPS Failure (CRAC units lose power during mains failure)
- NOC-HW-011: Router Line Card Replacement — CORE Platform (if humidity causes hardware damage)
- NOC-OPT-003: Fibre Cut — Span Loss Detection and Restoration (not related to humidity — referenced for disambiguation)

---

## Revision History

| Version | Date | Author | Change |
|---|---|---|---|
| 1.3 | 2025-11-20 | B. Okafor | Added CORE-SYD-01 risk assessment, water ingress procedure expanded |
| 1.2 | 2025-07-01 | M. Torres | Added ASHRAE A1 reference values, rate-of-change alarm |
| 1.1 | 2025-02-15 | B. Okafor | Added ESD precautions for low humidity scenario |
| 1.0 | 2024-08-10 | M. Torres | Initial version |
