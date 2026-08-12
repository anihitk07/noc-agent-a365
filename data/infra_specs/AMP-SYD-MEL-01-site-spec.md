# Site Specification — AMP-SYD-MEL-01 (Campbelltown)

**Site ID:** AMP-SYD-MEL-01  
**Site Name:** Campbelltown Amplifier  
**Type:** EDFA Optical Line Amplifier  
**Status:** Active — In Service  
**Commissioned:** 2022-03-15  
**Last Maintenance Visit:** 2026-01-22

---

## Location

| Field | Value |
|-------|-------|
| GPS Coordinates | -34.0775, 150.8121 |
| Address | Adjacent to Hume Motorway, 200m south of Narellan Road overpass, Campbelltown NSW |
| Access | Locked compound, gravel access track from service road (4WD not required) |
| Access Code | Gate padlock combination: **4527** (network-wide amplifier access code) |
| Nearest Town | Campbelltown (2km) |
| Nearest Depot | DEPOT-SYD-CAMPBELLTOWN (12km, 15 min drive) |

### Access Notes

- Site is accessible 24/7. No traffic management required — site is set back 50m from the road.
- The access track is unsealed but graded. Suitable for standard vehicles in dry conditions; 4WD recommended after heavy rain.
- Mobile coverage: Telstra 4G (strong), Optus 4G (moderate). Satellite phone not required.

---

## Power

| Field | Value |
|-------|-------|
| Supply | Mains — single-phase 240V AC, 15A |
| Circuit Breaker | 15A MCB in site distribution board |
| Meter | NSW meter # E-SYD-AMP01-4412 |
| UPS | APC Smart-UPS 1500VA (battery backup: ~45 min at typical load) |
| Generator Receptacle | 15A inlet — for portable generator connection during mains outage |

### Power Notes

- Total site power consumption: approximately 350W (EDFA 180W + monitoring equipment 120W + ancillaries 50W).
- UPS battery was last replaced 2025-06-10. Expected battery life: 3 years. Next replacement due: 2028-06-10.
- If mains power is lost, the UPS will sustain the EDFA for approximately 45 minutes. After UPS depletion, the amplifier will shut down and the span will go dark. Connect portable generator to the 15A inlet to restore power.

---

## Optical Equipment

| Component | Details |
|-----------|---------|
| EDFA Module | Lumentum S40i, Serial: LUM-S40I-AMP01-001 |
| Operating Wavelength | C-band (1530–1565nm) |
| Gain | 20 dB (adjustable 15–25 dB via NMS) |
| Output Power | +17 dBm total (per-channel: -3 dBm nominal at 96 channels) |
| Input Power Range | -25 dBm to +3 dBm total |
| Noise Figure | ≤5.5 dB |
| Fibre Patch Panel | 6-port SC/APC panel (rack-mounted) |
| Port Assignment | Port 1-2: Line In/Out (Sydney direction), Port 3-4: Line In/Out (Melbourne direction), Port 5: Monitor/tap (-20 dB), Port 6: Spare |

### Optical Notes

- This is the first amplifier south of Sydney on the Sydney–Melbourne DWDM corridor.
- Span to the north (Sydney exchange): 42km. Span loss: 9.2 dB (last measured 2025-11-15).
- Span to the south (AMP-SYD-MEL-02, Mittagong): 78km. Span loss: 16.8 dB (last measured 2025-11-15).
- Fibre type on both spans: Corning SMF-28e+ (G.652D), 96-fibre cable.

---

## Environmental

| Field | Value |
|-------|-------|
| Housing | Outdoor roadside cabinet (Emerson NetSure 801), IP55 rated |
| Dimensions | 1200mm (H) × 800mm (W) × 600mm (D) |
| Cooling | Passive ventilation with filtered air intake. No active cooling. |
| Operating Temperature | -10°C to +55°C (cabinet rated) |
| Typical Temperature Range | 5°C to 42°C (seasonal) |

---

## Monitoring

| System | Details |
|--------|---------|
| NMS | Monitored via Ciena MCP (Management and Control Plane) |
| SNMP | SNMPv3, polling interval 60 seconds |
| Alarms | Optical power low/high, temperature, UPS on battery, door open |
| CCTV | None (not justified at this risk level) |

---

## Emergency Contacts

| Role | Name | Contact |
|------|------|---------|
| Site Owner | Network Infrastructure, Optical Transport | NOC: 1800-NET-OPS (1800-638-677) |
| Nearest Depot | DEPOT-SYD-CAMPBELLTOWN | Ext. 4412 |
| Electrical Emergency | Local electrician (AllSpark Electrical, Campbelltown) | 0412-555-001 |
| Fire / Ambulance / Police | Emergency Services | 000 |
