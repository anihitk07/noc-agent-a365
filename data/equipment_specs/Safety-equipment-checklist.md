# Safety Equipment Checklist — Field Operations

**Document ID:** EQ-SAFE-001  
**Revision:** 4.0 — 2026-01-05  
**Authority:** WHS Manager, Network Operations  
**Compliance:** Work Health and Safety Act 2011 (NSW/VIC), AS/NZS standards as cited

---

## 1. Personal Protective Equipment (PPE) — All Field Work

Every technician must carry and wear the following PPE when working at any field site, including amplifier cabinets, pits, poles, and roadside locations.

| Item | Standard | Notes |
|------|----------|-------|
| Hard hat | AS/NZS 1801:1997 | Mandatory at all amplifier sites and pit/pole locations. Replace after any impact or every 5 years from manufacture date (stamped inside). |
| Safety glasses (clear) | AS/NZS 1337.1 | Mandatory during fibre preparation, cleaving, and splicing. Bare fibre fragments are invisible and can penetrate skin or eyes. |
| Hi-visibility vest | AS/NZS 4602.1 Class D/N | Day/Night rated. Mandatory at all roadside and outdoor sites. |
| Steel-cap boots | AS/NZS 2210.3 | Mandatory at all field sites. |
| Insulated gloves | AS/NZS 2225 Class 0 (1000V) | Mandatory when working near or opening electrical panels at amplifier sites. Test gloves with inflator before each use — discard if punctured. |
| Hearing protection | AS/NZS 1270 Class 5 | Required when operating portable generators (Honda EU22i rated at 89 dBA at full load). |
| Sunscreen (SPF 50+) | — | Required for outdoor work exceeding 15 minutes. Reapply every 2 hours. |

---

## 2. Confined Space Entry

Confined space entry applies to underground pits, manholes, and sealed amplifier vaults. A confined space is any enclosed or partially enclosed area not designed for continuous human occupancy, with restricted entry/exit.

### Pre-Entry Requirements

1. **Risk assessment:** Complete a Confined Space Entry Permit (form WHS-CSE-01) before entering any pit or vault. The permit must be signed by the site supervisor.
2. **Gas monitoring:** Use a calibrated 4-gas detector (BW Clip4 or equivalent) to test atmosphere before entry:
   - Oxygen: 19.5–23.5% (safe range). Below 19.5% = oxygen deficient, do not enter.
   - LEL (combustible gas): <10% LEL. Above 10% = evacuate and ventilate.
   - H₂S: <10 ppm. Above 10 ppm = evacuate immediately.
   - CO: <25 ppm. Above 25 ppm = evacuate and ventilate.
3. **Ventilation:** If any reading is outside safe limits, ventilate the space with a forced-air blower for a minimum of 15 minutes and re-test before entry.
4. **Communication:** Maintain continuous visual or voice contact with a standby person at the entry point. The standby person must not enter the space under any circumstances.
5. **Rescue plan:** A rescue tripod and winch must be erected over the entry point before any person enters. Ensure the retrieval line is attached to the entrant's harness.

### Equipment Required

| Item | Purpose |
|------|---------|
| 4-gas detector (calibrated) | Atmosphere monitoring — continuous wear during entry |
| Forced-air blower | Ventilation of the space |
| Full-body harness (AS/NZS 1891.1) | Fall arrest and rescue retrieval |
| Rescue tripod and winch | Emergency extraction |
| Torch / headlamp (intrinsically safe) | Illumination |
| Confined Space Entry Permit (completed) | Regulatory compliance |

---

## 3. Electrical Safety at Amplifier Sites

All amplifier sites on the Sydney–Melbourne corridor are powered by mains electricity (single-phase 240V, 15A or 32A circuits). The following procedures apply when accessing electrical panels or working near energised equipment.

### Isolation Procedure

1. Before opening any electrical panel, verify the circuit is de-energised using a voltage tester (CAT III rated minimum). Test between Active-Neutral, Active-Earth, and Neutral-Earth.
2. If the circuit cannot be isolated (e.g., the amplifier must remain powered), work under **live-work conditions**:
   - Wear Class 0 insulated gloves.
   - Use insulated tools only.
   - Maintain a minimum 300mm clearance from exposed live parts.
   - A second person must be present as a safety observer.
3. Lock-out/tag-out (LOTO): When the circuit is isolated, apply a personal lock and tag to the circuit breaker. Each technician working on the equipment must apply their own lock. The circuit must not be re-energised until all locks are removed.

### Portable Generator Safety

When using a portable generator at a site with no mains power or as a temporary supply:

1. Position the generator at least 3 metres from any enclosed space or air intake (carbon monoxide hazard).
2. Use a residual current device (RCD, 30mA) on all extension leads.
3. Earth the generator frame to a ground stake using the supplied earth lead.
4. Refuel only when the generator is off and cool (minimum 5-minute cool-down).

---

## 4. Roadside and Traffic Management

Any work within 3 metres of a traffic lane requires traffic management controls.

| Traffic Speed | Minimum Control |
|---------------|----------------|
| ≤60 km/h | Witches hats (cones) and warning signs — "Workers Ahead" at 100m |
| 61–80 km/h | Traffic management plan (TMP) required. Arrow board or vehicle-mounted attenuator. |
| >80 km/h | Accredited traffic controller required on site. Submit TMP to road authority 48 hours in advance. |

Most amplifier sites on the Sydney–Melbourne corridor are adjacent to the Hume Highway (110 km/h zones). A traffic controller and approved TMP are mandatory for any work at these sites.

---

## 5. Laser Safety

All fibre optic test equipment emits Class 1M or Class 3R laser radiation. Observe the following:

- Never look directly into a fibre end or OTDR port.
- Cap unused fibre connectors and OTDR ports when not in use.
- Display "Laser in Use" signage at the work area during testing.
- Laser safety training (module WHS-LASER-01) is a prerequisite for operating OTDR, VFL, or optical power meter equipment.
