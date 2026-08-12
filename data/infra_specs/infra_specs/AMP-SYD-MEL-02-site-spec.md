# Site Specification — AMP-SYD-MEL-02 (Mittagong)

**Site ID:** AMP-SYD-MEL-02  
**Site Name:** Mittagong Amplifier  
**Type:** EDFA Optical Line Amplifier  
**Status:** Active — In Service  
**Commissioned:** 2022-03-22  
**Last Maintenance Visit:** 2026-01-22

---

## Location

| Field | Value |
|-------|-------|
| GPS Coordinates | -34.4517, 150.4468 |
| Address | Off Old Hume Highway, 1.2km south of Mittagong township, Mittagong NSW |
| Access | Locked compound at end of gravel access track (150m from road) |
| Access Code | Gate padlock combination: **4527** |
| Nearest Town | Mittagong (1.2km) |
| Nearest Depot | DEPOT-SYD-CAMPBELLTOWN (55km, 45 min drive via Hume Motorway) |

### Access Notes

- Site is accessible 24/7. Located on private rural land with an access easement — no traffic management required.
- Access track is unsealed, narrow, and steep in the final 50m. 4WD recommended in all conditions.
- Mobile coverage: Telstra 4G (moderate), Optus 4G (weak). Satellite phone recommended for extended site work.
- Nearest fuel station: Mittagong BP (1.5km).

---

## Power

| Field | Value |
|-------|-------|
| Supply | Mains — single-phase 240V AC, 15A |
| Circuit Breaker | 15A MCB in site distribution board |
| Meter | NSW meter # E-SYD-AMP02-4413 |
| UPS | APC Smart-UPS 1500VA (battery backup: ~45 min) |
| Generator Receptacle | 15A inlet |

### Power Notes

- Total site power consumption: approximately 380W (EDFA 200W + monitoring 130W + ancillaries 50W).
- UPS battery last replaced 2025-08-20. Next replacement due: 2028-08-20.
- Mains supply runs from a pole-mounted transformer on Old Hume Highway. Supply reliability is lower than urban sites — two unplanned outages recorded in the past 12 months (storm damage). Consider portable generator pre-deployment during severe weather forecasts.

---

## Optical Equipment

| Component | Details |
|-----------|---------|
| EDFA Module | Lumentum S40i, Serial: LUM-S40I-AMP02-001 |
| Operating Wavelength | C-band (1530–1565nm) |
| Gain | 22 dB |
| Output Power | +17 dBm total |
| Input Power Range | -25 dBm to +3 dBm total |
| Noise Figure | ≤5.5 dB |
| Fibre Patch Panel | 6-port SC/APC panel |
| Port Assignment | Port 1-2: Line In/Out (Sydney direction), Port 3-4: Line In/Out (Melbourne direction), Port 5: Monitor/tap (-20 dB), Port 6: Spare |

### Optical Notes

- Span to the north (AMP-SYD-MEL-01, Campbelltown): 78km. Span loss: 16.8 dB.
- Span to the south (AMP-SYD-MEL-03, Goulburn): 82km. Span loss: 17.4 dB (last measured 2025-11-15).
- This is the highest-altitude amplifier on the corridor (elevation ~640m). Temperature swings are wider than coastal sites — monitor cabinet temperature alarms during summer heat events.
- Fibre type: Corning SMF-28e+ (G.652D), 96-fibre cable.

---

## Environmental

| Field | Value |
|-------|-------|
| Housing | Outdoor roadside cabinet (Emerson NetSure 801), IP55 rated |
| Dimensions | 1200mm (H) × 800mm (W) × 600mm (D) |
| Cooling | Passive ventilation with filtered air intake |
| Operating Temperature | -10°C to +55°C (cabinet rated) |
| Typical Temperature Range | -2°C to 38°C (seasonal — frost risk in winter) |

### Environmental Notes

- Frost has been observed on the cabinet exterior during winter mornings (June–August). Internal cabinet temperature has not dropped below +2°C due to equipment heat dissipation.
- Spider and insect ingress noted during maintenance visits. Air intake filters should be inspected and cleaned at every visit. Carry spare filter media (part: EMR-FLT-801-STD).

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
| Nearest Depot | DEPOT-SYD-CAMPBELLTOWN | Ext. 4412 |
| Electrical Emergency | Southern Highlands Electrical | 0412-555-002 |
| Fire / Ambulance / Police | Emergency Services | 000 |
