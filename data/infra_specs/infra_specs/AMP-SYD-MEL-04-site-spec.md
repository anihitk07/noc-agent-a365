# Site Specification — AMP-SYD-MEL-04 (Yass)

**Site ID:** AMP-SYD-MEL-04  
**Site Name:** Yass Amplifier  
**Type:** EDFA Optical Line Amplifier  
**Status:** Active — In Service  
**Commissioned:** 2022-04-18  
**Last Maintenance Visit:** 2026-01-23

---

## Location

| Field | Value |
|-------|-------|
| GPS Coordinates | -34.8411, 148.9098 |
| Address | Barton Highway interchange, 2km east of Yass township, Yass NSW |
| Access | Locked compound off unsealed access track (100m from interchange) |
| Access Code | Gate padlock combination: **4527** |
| Nearest Town | Yass (2km) |
| Nearest Depot | DEPOT-MEL-CLAYTON (280km, ~3 hr drive via Hume Highway) |
| Alternate Depot | DEPOT-SYD-CAMPBELLTOWN (155km, ~1 hr 45 min drive) |

### Access Notes

- Site is accessible 24/7. Located on Crown land adjacent to the Barton Highway–Hume Highway interchange.
- The access track is unsealed but well-maintained. Standard vehicles are acceptable in dry conditions; 4WD recommended after rain.
- **Traffic management:** Not required for cabinet-side work. Required if accessing the cable route along the highway.
- Mobile coverage: Telstra 4G (strong), Optus 4G (moderate).
- Nearest fuel: Yass BP (2.5km). Nearest accommodation: Yass Motor Inn (3km) — useful for multi-day maintenance windows.

---

## Power

| Field | Value |
|-------|-------|
| Supply | Mains — single-phase 240V AC, 15A |
| Circuit Breaker | 15A MCB in site distribution board |
| Meter | NSW meter # E-SYD-AMP04-4415 |
| UPS | APC Smart-UPS 1500VA (battery backup: ~45 min) |
| Generator Receptacle | 15A inlet, external right-hand wall |

### Power Notes

- Total site power consumption: approximately 360W.
- UPS battery last replaced 2025-07-01. Next replacement due: 2028-07-01.
- Mains supply from overhead line off the Barton Highway. Moderate reliability — one unplanned outage in the past 12 months (bushfire-related pole damage, 4-hour duration). Generator pre-deployment recommended during Total Fire Ban days.

---

## Optical Equipment

| Component | Details |
|-----------|---------|
| EDFA Module | Lumentum S40i, Serial: LUM-S40I-AMP04-001 |
| Operating Wavelength | C-band (1530–1565nm) |
| Gain | 21 dB |
| Output Power | +17 dBm total |
| Input Power Range | -25 dBm to +3 dBm total |
| Noise Figure | ≤5.5 dB |
| Fibre Patch Panel | 6-port SC/APC panel |
| Port Assignment | Port 1-2: Line In/Out (Sydney direction), Port 3-4: Line In/Out (Melbourne direction), Port 5: Monitor/tap (-20 dB), Port 6: Spare |

### Optical Notes

- Span to the north (AMP-SYD-MEL-03, Goulburn): 80km. Span loss: 16.9 dB.
- Span to the south (AMP-SYD-MEL-05, Albury): 85km. Span loss: 17.8 dB (last measured 2025-11-16). This is the longest span on the corridor and operates closest to the optical power budget limit.
- Fibre type: Corning SMF-28e+ (G.652D), 96-fibre cable.
- The Yass–Albury span crosses the Snowy Mountains foothills. Cable route includes several directional bores under creek crossings (flood risk areas). See cable route GIS for bore locations.

---

## Environmental

| Field | Value |
|-------|-------|
| Housing | Outdoor roadside cabinet (Emerson NetSure 801), IP55 rated |
| Dimensions | 1200mm (H) × 800mm (W) × 600mm (D) |
| Cooling | Passive ventilation with filtered air intake |
| Operating Temperature | -10°C to +55°C |
| Typical Temperature Range | -4°C to 42°C (hot summers, cold winters) |

### Environmental Notes

- This site experiences the widest temperature range on the corridor due to its inland continental location.
- Bushfire risk is rated High (RFS assessment 2025). A 10m cleared firebreak surrounds the compound. Vegetation management is performed annually (October).
- Dust ingress is a concern during dry summers. Air intake filters should be inspected and replaced more frequently than coastal sites (every 3 months vs. 6 months).

---

## Monitoring

| System | Details |
|--------|---------|
| NMS | Ciena MCP |
| SNMP | SNMPv3, polling interval 60 seconds |
| Alarms | Optical power low/high, temperature, UPS on battery, door open |
| CCTV | None |

---

## Emergency Contacts

| Role | Name | Contact |
|------|------|---------|
| Site Owner | Network Infrastructure, Optical Transport | NOC: 1800-NET-OPS |
| Nearest Depot | DEPOT-MEL-CLAYTON | Ext. 5538 |
| Alternate Depot | DEPOT-SYD-CAMPBELLTOWN | Ext. 4412 |
| Electrical Emergency | Yass Valley Electrical | 0412-555-004 |
| Fire / Ambulance / Police | Emergency Services | 000 |
