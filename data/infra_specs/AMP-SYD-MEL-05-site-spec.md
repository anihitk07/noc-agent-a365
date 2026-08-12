# Site Specification — AMP-SYD-MEL-05 (Albury)

**Site ID:** AMP-SYD-MEL-05  
**Site Name:** Albury Amplifier  
**Type:** EDFA Optical Line Amplifier  
**Status:** Active — In Service  
**Commissioned:** 2022-05-02  
**Last Maintenance Visit:** 2026-01-23

---

## Location

| Field | Value |
|-------|-------|
| GPS Coordinates | -36.0737, 146.9135 |
| Address | Hume Freeway, 4km south of Albury CBD (NSW/VIC border region), Albury NSW |
| Access | Locked compound, sealed access from Hume Freeway service road |
| Access Code | Gate padlock combination: **4527** |
| Nearest Town | Albury (4km) / Wodonga VIC (8km) |
| Nearest Depot | DEPOT-MEL-CLAYTON (305km, ~3 hr 15 min drive via Hume Freeway) |
| Alternate Depot | DEPOT-SYD-CAMPBELLTOWN (520km — not practical for routine dispatch) |

### Access Notes

- Site is accessible 24/7. Located within the Hume Freeway corridor on a service road.
- Sealed access — standard vehicles acceptable in all conditions.
- **Traffic management:** Not required for cabinet work (site is well clear of travel lanes). Required for cable route access along the freeway.
- Mobile coverage: Telstra 4G (strong), Optus 4G (strong). Good coverage due to proximity to Albury urban area.
- Nearest fuel and amenities: Albury CBD (4km).

---

## Power

| Field | Value |
|-------|-------|
| Supply | Mains — single-phase 240V AC, 32A |
| Circuit Breaker | 32A MCB in site distribution board |
| Meter | NSW meter # E-SYD-AMP05-4416 |
| UPS | APC Smart-UPS 3000VA (battery backup: ~60 min at typical load) |
| Generator Receptacle | 15A inlet, external right-hand wall |

### Power Notes

- This site has a higher power capacity (32A supply, 3000VA UPS) because it co-hosts DWDM terminal equipment for the Albury–Wodonga metro feed in addition to the line amplifier.
- Total site power consumption: approximately 620W (line EDFA 190W + metro EDFA 180W + monitoring 200W + ancillaries 50W).
- UPS battery last replaced 2025-09-10. Next replacement due: 2028-09-10.
- Mains supply is underground from the Albury substation. High reliability — no unplanned outages in the past 36 months.

---

## Optical Equipment

| Component | Details |
|-----------|---------|
| Line EDFA Module | Lumentum S40i, Serial: LUM-S40I-AMP05-001 |
| Metro EDFA Module | Lumentum S20i, Serial: LUM-S20I-AMP05-002 |
| Operating Wavelength | C-band (1530–1565nm) |
| Line Gain | 23 dB |
| Line Output Power | +17 dBm total |
| Input Power Range | -25 dBm to +3 dBm total |
| Noise Figure | ≤5.5 dB |
| Fibre Patch Panel | 12-port SC/APC panel (expanded for metro feed) |
| Port Assignment (Line) | Port 1-2: Line In/Out (Sydney direction), Port 3-4: Line In/Out (Melbourne direction), Port 5: Monitor/tap (-20 dB), Port 6: Spare |
| Port Assignment (Metro) | Port 7-8: Metro Albury feed, Port 9-10: Metro Wodonga feed, Port 11-12: Spare |

### Optical Notes

- Span to the north (AMP-SYD-MEL-04, Yass): 85km. Span loss: 17.8 dB. This is the longest and highest-loss span on the corridor — operates within 1.5 dB of the optical power budget limit. Any additional splice loss or connector degradation on this span will trigger low-power alarms.
- Span to the south (Melbourne exchange): 305km via three additional regional amplifiers (not on the primary Sydney–Melbourne backbone — separate corridor). For the primary backbone, this is the last amplifier before the Melbourne DWDM terminal at Clayton exchange.
- Remaining span to Melbourne DWDM terminal (Clayton exchange): 78km. Span loss: 16.2 dB.
- Fibre type: Corning SMF-28e+ (G.652D), 96-fibre cable.

---

## Environmental

| Field | Value |
|-------|-------|
| Housing | Outdoor roadside cabinet (Emerson NetSure 801), IP55 rated — double-width (1600mm W) to accommodate metro equipment |
| Dimensions | 1200mm (H) × 1600mm (W) × 600mm (D) |
| Cooling | Active cooling — thermostatically controlled fan unit (engages at 35°C internal) |
| Operating Temperature | -10°C to +55°C |
| Typical Temperature Range | -2°C to 40°C |

### Environmental Notes

- The double-width cabinet generates more heat than standard sites due to dual EDFAs. The active cooling fan is critical in summer — if the fan fails, internal temperature can reach 50°C within 2 hours on hot days. Fan motor should be inspected at every maintenance visit.
- Fan motor part: EMR-FAN-801-DBLW. Lead time: 5 business days from Emerson Australia.

---

## Monitoring

| System | Details |
|--------|---------|
| NMS | Ciena MCP |
| SNMP | SNMPv3, polling interval 60 seconds |
| Alarms | Optical power low/high, temperature high/critical, UPS on battery, door open, fan fail |
| CCTV | IP camera (Axis M3106-L Mk II) — accessible via NOC |

### Monitoring Notes

- This is the only amplifier site on the corridor with CCTV. Installed after a 2023 break-in attempt (incident ref: INC-2023-0447). Camera is powered by the site UPS and feeds to the NOC via a 4G cellular modem.

---

## Emergency Contacts

| Role | Name | Contact |
|------|------|---------|
| Site Owner | Network Infrastructure, Optical Transport | NOC: 1800-NET-OPS |
| Nearest Depot | DEPOT-MEL-CLAYTON | Ext. 5538 |
| Electrical Emergency | Albury Power Services | 0412-555-005 |
| Fire / Ambulance / Police | Emergency Services | 000 |
