# Site Specification — AMP-SYD-MEL-03 (Goulburn)

**Site ID:** AMP-SYD-MEL-03  
**Site Name:** Goulburn Amplifier  
**Type:** EDFA Optical Line Amplifier  
**Status:** Active — In Service  
**Commissioned:** 2022-04-05  
**Last Maintenance Visit:** 2026-01-22

---

## Location

| Field | Value |
|-------|-------|
| GPS Coordinates | -34.7515, 149.7181 |
| Address | Hume Highway service road, 3km north of Goulburn CBD, Goulburn NSW |
| Access | Locked compound adjacent to highway service road |
| Access Code | Gate padlock combination: **4527** |
| Nearest Town | Goulburn (3km) |
| Nearest Depot (primary) | DEPOT-SYD-CAMPBELLTOWN (75km, ~55 min drive via Hume Motorway) |
| Nearest Depot (secondary) | DEPOT-MEL-CLAYTON (190km, ~2 hr 15 min drive) |

### Access Notes

- Site is accessible 24/7. The compound is fenced with a 1.8m chain-link perimeter fence.
- Located immediately adjacent to the northbound Hume Highway service road. **Traffic management is required** for any work that involves accessing the cable route — the fibre conduit crosses beneath the highway at this location.
- 4WD not required. Sealed access from service road.
- Mobile coverage: Telstra 4G (strong), Optus 4G (moderate).
- Nearest fuel and amenities: Goulburn CBD (3km south).

---

## Power

| Field | Value |
|-------|-------|
| Supply | Mains — single-phase 240V AC, 15A |
| Circuit Breaker | 15A MCB in site distribution board |
| Meter | NSW meter # E-SYD-AMP03-4414 |
| UPS | APC Smart-UPS 1500VA (battery backup: ~45 min) |
| Generator Receptacle | 15A inlet — located on external wall of cabinet for easy access |

### Power Notes

- Total site power consumption: approximately 370W (EDFA 190W + monitoring 130W + ancillaries 50W).
- UPS battery last replaced 2025-04-15. Next replacement due: 2028-04-15.
- Mains supply is reliable (underground feed from Goulburn substation). No unplanned outages recorded in the past 24 months.
- The 15A generator inlet is on the external right-hand wall of the cabinet. Compatible with standard Honda EU22i generator output.

---

## Optical Equipment

| Component | Details |
|-----------|---------|
| EDFA Module | Lumentum S40i, Serial: LUM-S40I-AMP03-001 |
| Operating Wavelength | C-band (1530–1565nm) |
| Gain | 22 dB |
| Output Power | +17 dBm total |
| Input Power Range | -25 dBm to +3 dBm total |
| Noise Figure | ≤5.5 dB |
| Fibre Patch Panel | 6-port SC/APC panel (Fujikura splice tray behind panel) |
| Port Assignment | Port 1-2: Line In/Out (Sydney direction), Port 3-4: Line In/Out (Melbourne direction), Port 5: Monitor/tap (-20 dB), Port 6: Spare |

### Splice Tray Details

The Fujikura splice tray behind the patch panel contains 12 fusion splices connecting the incoming cable fibres to the pigtails on the patch panel. These splices were made during commissioning (2022-04-05) using a Fujikura 90S splicer. Average splice loss at commissioning: 0.02 dB.

**Important:** When re-splicing at this site, use the Fujikura 90S in SM-Standard mode. The splice tray accommodates a maximum of 24 splice sleeves. Currently 12 of 24 slots are occupied.

### Optical Notes

- Span to the north (AMP-SYD-MEL-02, Mittagong): 82km. Span loss: 17.4 dB.
- Span to the south (AMP-SYD-MEL-04, Yass): 80km. Span loss: 16.9 dB (last measured 2025-11-15).
- This site is the **primary demo fault location** for incident simulation scenarios. Network test engineers should familiarise themselves with the full site layout before conducting exercises.
- Fibre type: Corning SMF-28e+ (G.652D), 96-fibre cable on both directions.

---

## Environmental

| Field | Value |
|-------|-------|
| Housing | Outdoor roadside cabinet (Emerson NetSure 801), IP55 rated |
| Dimensions | 1200mm (H) × 800mm (W) × 600mm (D) |
| Cooling | Passive ventilation with filtered air intake |
| Operating Temperature | -10°C to +55°C (cabinet rated) |
| Typical Temperature Range | -3°C to 40°C (seasonal — continental climate, cold winters) |

### Environmental Notes

- Goulburn is one of the coldest inland cities in Australia. Overnight temperatures below 0°C are common June–August. Cabinet internal temperature is maintained above +5°C by equipment heat dissipation.
- Rodent deterrent mesh has been installed on all cable entry points following a 2024 incident where rodent damage caused a fibre break (incident ref: INC-2024-0892).

---

## Cable Route Information

The fibre cable enters and exits the site via underground conduit. The conduit route:

- **North (toward Mittagong):** Runs along the western edge of the Hume Highway for 2.3km before transitioning to a buried route through agricultural land. Pit/manhole spacing: approximately 1km.
- **South (toward Yass):** Follows the highway reserve for 5km, then diverges through farmland. Pit/manhole spacing: approximately 1.2km.
- **Highway crossing:** The cable crosses beneath the Hume Highway via a directional bore at GPS -34.7520, 149.7175 (50m south of the site). Depth: 1.5m. Conduit type: 100mm HDPE, dual bore.

---

## Monitoring

| System | Details |
|--------|---------|
| NMS | Ciena MCP |
| SNMP | SNMPv3, polling interval 60 seconds |
| Alarms | Optical power low/high, temperature, UPS on battery, door open, EDFA pump laser current high |
| CCTV | None |

---

## Emergency Contacts

| Role | Name | Contact |
|------|------|---------|
| Site Owner | Network Infrastructure, Optical Transport | NOC: 1800-NET-OPS |
| Nearest Depot | DEPOT-SYD-CAMPBELLTOWN | Ext. 4412 |
| Local Depot (secondary) | DEPOT-MEL-CLAYTON | Ext. 5538 |
| Electrical Emergency | Goulburn Electrical Services | 0412-555-003 |
| Fire / Ambulance / Police | Emergency Services | 000 |
