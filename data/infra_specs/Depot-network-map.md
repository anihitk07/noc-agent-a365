# Depot Network Map — Sydney–Melbourne DWDM Corridor

**Document ID:** INFRA-DEPOT-001  
**Revision:** 2.0 — 2026-01-20  
**Owner:** Field Operations, Network Infrastructure  
**Purpose:** Dispatch reference for NOC and field coordinators

---

## 1. Depot Locations

| Depot ID | Location | State | GPS | Operating Hours |
|----------|----------|-------|-----|-----------------|
| DEPOT-SYD-PARRAMATTA | 22 Victoria Road, Parramatta NSW 2150 | NSW | -33.8151, 151.0032 | 06:00–20:00 AEST |
| DEPOT-SYD-CAMPBELLTOWN | 14 Blaxland Road, Campbelltown NSW 2560 | NSW | -34.0649, 150.8143 | 06:00–18:00 AEST |
| DEPOT-MEL-CLAYTON | 7 Hume Road, Clayton VIC 3168 | VIC | -37.9145, 145.1192 | 06:00–18:00 AEST |

---

## 2. Amplifier Site Assignments

Each amplifier site has a primary dispatch depot (fastest response) and a secondary depot (backup if primary is unavailable).

| Amplifier Site | Primary Depot | Distance (km) | Drive Time | Secondary Depot | Distance (km) | Drive Time |
|----------------|---------------|---------------|------------|-----------------|---------------|------------|
| AMP-SYD-MEL-01 (Campbelltown) | DEPOT-SYD-CAMPBELLTOWN | 12 | 15 min | DEPOT-SYD-PARRAMATTA | 45 | 40 min |
| AMP-SYD-MEL-02 (Mittagong) | DEPOT-SYD-CAMPBELLTOWN | 55 | 45 min | DEPOT-SYD-PARRAMATTA | 95 | 1 hr 10 min |
| AMP-SYD-MEL-03 (Goulburn) | DEPOT-SYD-CAMPBELLTOWN | 75 | 55 min | DEPOT-MEL-CLAYTON | 190 | 2 hr 15 min |
| AMP-SYD-MEL-04 (Yass) | DEPOT-SYD-CAMPBELLTOWN | 155 | 1 hr 45 min | DEPOT-MEL-CLAYTON | 280 | 3 hr |
| AMP-SYD-MEL-05 (Albury) | DEPOT-MEL-CLAYTON | 305 | 3 hr 15 min | DEPOT-SYD-CAMPBELLTOWN | 520 | 5 hr 30 min |

### Dispatch Decision Notes

- **AMP-SYD-MEL-03 (Goulburn)** is the approximate midpoint of the corridor. It is nominally assigned to Campbelltown (75km), but Clayton (190km) is the secondary option. For Priority 1 faults at Goulburn, always dispatch from Campbelltown unless Campbelltown has no available crew, in which case dispatch from Clayton with an estimated 2 hr 15 min response time.
- **AMP-SYD-MEL-04 (Yass)** is equidistant from both depots in travel time terms. Campbelltown is closer (155km vs 280km) but the drive time difference is approximately 1 hour. If the fault requires specialised DWDM test equipment (e.g., chromatic dispersion analyser), dispatch from Clayton, which carries that equipment.
- **AMP-SYD-MEL-05 (Albury)** is only practically serviced from Clayton. The 520km drive from Campbelltown is not feasible for time-critical faults. If Clayton has no available crew, consider engaging a local third-party contractor (Albury Telecom Services, contract ref: SVC-3P-ALB-2025).

---

## 3. Driving Routes

All driving distances and times assume use of the Hume Motorway/Hume Highway/Hume Freeway (the primary route between Sydney and Melbourne). Times are based on normal traffic conditions and speed limits.

### From DEPOT-SYD-CAMPBELLTOWN

```
Campbelltown → AMP-SYD-MEL-01: 12km south via Hume Motorway (15 min)
Campbelltown → AMP-SYD-MEL-02: 55km south via Hume Motorway, exit Mittagong (45 min)
Campbelltown → AMP-SYD-MEL-03: 75km south via Hume Motorway, exit Goulburn (55 min)
Campbelltown → AMP-SYD-MEL-04: 155km south via Hume Highway to Yass (1 hr 45 min)
Campbelltown → AMP-SYD-MEL-05: 520km south via Hume Highway to Albury (5 hr 30 min) — NOT RECOMMENDED
```

### From DEPOT-MEL-CLAYTON

```
Clayton → AMP-SYD-MEL-05: 305km north via Hume Freeway to Albury (3 hr 15 min)
Clayton → AMP-SYD-MEL-04: 280km north via Hume Freeway/Highway to Yass (3 hr)
Clayton → AMP-SYD-MEL-03: 190km north via Hume Freeway/Highway to Goulburn (2 hr 15 min) — SECONDARY ONLY
Clayton → AMP-SYD-MEL-02: 400km north (4 hr 30 min) — NOT PRACTICAL
Clayton → AMP-SYD-MEL-01: 450km north (4 hr 45 min) — NOT PRACTICAL
```

### From DEPOT-SYD-PARRAMATTA

Parramatta depot services Sydney metro exchange sites. It is not a primary or secondary dispatch point for amplifier sites except AMP-SYD-MEL-01 (secondary, 45km, 40 min). In exceptional circumstances, Parramatta can be used as a tertiary dispatch point for AMP-SYD-MEL-02 (95km, 1 hr 10 min).

---

## 4. After-Hours Dispatch Protocol

Outside depot operating hours (18:00–06:00 AEST, or 20:00–06:00 for Parramatta):

1. The NOC contacts the on-call technician for the assigned depot.
2. On-call technicians have security fob access to their home depot.
3. On-call roster is maintained in the Workforce Management System (WMS) and updated weekly.
4. If the on-call technician for the primary depot is unreachable within 15 minutes, escalate to the secondary depot's on-call technician.
5. Response time SLAs apply from the moment the technician acknowledges the callout, not from the time of the initial fault detection.

| Fault Priority | Target Response Time (on-site) | Maximum Response Time |
|----------------|-------------------------------|----------------------|
| P1 (service down, >10,000 customers affected) | 2 hours | 4 hours |
| P2 (service degraded, <10,000 customers affected) | 4 hours | 8 hours |
| P3 (non-service-affecting, monitoring alarm) | Next business day | 48 hours |

---

## 5. Equipment Availability Matrix

This matrix shows which key test equipment is available at each depot. If a specific item is required for a fault, dispatch from the depot that has it.

| Equipment | Parramatta | Campbelltown | Clayton |
|-----------|------------|--------------|---------|
| Viavi T-BERD 4000 OTDR | ✓ (2 units) | ✓ (1 unit) | ✓ (1 unit) |
| Fujikura 90S splicer | ✓ (1 unit) | ✓ (1 unit) | ✓ (1 unit) |
| Fujikura 70R+ ribbon splicer | ✓ (1 unit) | ✗ | ✗ |
| EXFO FTB-5700 CD analyser | ✗ | ✗ | ✓ (1 unit) |
| Portable generator | ✓ (1 unit) | ✓ (1 unit) | ✓ (2 units) |
| Confined space entry kit | ✓ (full kit) | ✓ (gas detector only) | ✓ (full kit) |

**Note:** If a fault at AMP-SYD-MEL-03 (Goulburn) or AMP-SYD-MEL-04 (Yass) might involve DWDM channel-level diagnostics requiring a CD analyser, dispatch from Clayton despite the longer drive time. Campbelltown does not carry CD/PMD test equipment.
