# Quick Start Guide — Fujikura 90S Fusion Splicer

**Document ID:** EQ-QS-002  
**Applies to:** Fujikura 90S+ core-alignment fusion splicer  
**Revision:** 2.1 — 2025-12-15  
**Author:** Network Test Engineering, Optical Transport Group

---

## 1. Pre-Splice Setup

### Power On

1. Open the wind cover. Press the green power button and hold for 1 second.
2. The splicer performs a self-test (approximately 10 seconds). Verify the electrode condition indicator on the home screen shows "Good" or "Normal."
3. If electrode condition shows "Replace Soon" or "Replace," do not proceed with production splicing. See Section 5 for electrode replacement.

### Splice Mode Selection

Select the appropriate splice mode from the preset menu:

| Mode | Fibre Type | Application |
|------|-----------|-------------|
| SM-Standard | G.652D single-mode | Standard backbone splicing (Sydney–Melbourne corridor) |
| SM-Auto | G.652D auto-detected | General single-mode, auto-adjusts arc parameters |
| DS | G.653 dispersion-shifted | Legacy dispersion-shifted fibre (not used on current network) |
| NZDS | G.655 non-zero DS | NZDS fibre in metro ring segments |
| MM | OM3/OM4 multimode | Data centre and building riser fibre |

For the Sydney–Melbourne backbone, always use **SM-Standard** mode. The auto mode may over-optimise arc power for G.652D and produce marginally higher splice loss.

---

## 2. Fibre Preparation

Proper fibre preparation is the single most important factor in achieving low splice loss. Follow this procedure exactly.

### Strip

1. Using the Fujikura CT-08 thermal stripper (or approved equivalent), strip 30–40mm of coating from each fibre end.
2. Grip the fibre firmly in the stripper jaws. Close and wait for the "beep" (thermal strip complete, approximately 3 seconds).
3. Pull the fibre smoothly through the jaws to remove the coating. Do not twist.
4. Inspect the stripped fibre under the splicer's built-in magnifier. The bare cladding (125μm) must be clean, with no residual coating fragments.

### Clean

1. Fold a lint-free IPA wipe over the stripped fibre.
2. Pull the fibre through the wipe in one direction only (away from the coated section). Repeat 2–3 times with a fresh section of wipe each time.
3. Do not touch the cleaned fibre with fingers. Skin oils cause splice contamination and elevated loss.

### Cleave

1. Place the fibre in the Fujikura CT-50 precision cleaver. Set the cleave length to **16mm** (factory default for the 90S).
2. Close the clamp and press the cleave lever in a single smooth motion.
3. The splicer will display the cleave angle after fibre insertion. Acceptable cleave angle: **≤0.5°**. If the angle exceeds 1.0°, discard the cleave and re-cleave.
4. Discard cleaved fibre offcuts into the fibre scrap container immediately. Glass fragments are a puncture hazard.

---

## 3. Splice Procedure

1. Open the splicer V-groove covers and place each prepared fibre into its respective fibre holder.
2. Close the wind cover.
3. Press the green **SET** button. The splicer will:
   - Align the fibres using active core alignment (camera-based, X and Y axes).
   - Perform a pre-arc cleaning discharge (0.5 seconds).
   - Execute the fusion arc (approximately 2 seconds at 1,600°C).
   - Estimate the splice loss from the core alignment offset.
4. Read the estimated splice loss on the display.

### Splice Loss Targets

| Metric | Target | Maximum Acceptable |
|--------|--------|-------------------|
| Individual splice loss | ≤0.02 dB | 0.05 dB |
| Average splice loss (per cable drum joint) | ≤0.03 dB | 0.05 dB |
| Cumulative splice loss (80km span, ~16 splices) | ≤0.48 dB | 0.80 dB |

If the estimated splice loss exceeds 0.05 dB, the splicer will flag the splice with a warning. **Do not accept the splice.** Re-strip, re-cleave, and re-splice. Common causes of high splice loss:

- Poor cleave angle (>1.0°)
- Fibre contamination (residual coating, dust, or oil)
- Worn electrodes (>5,000 arcs since last replacement)
- Core eccentricity in the fibre (rare; switch to a different fibre from the same cable)

---

## 4. Splice Protection

1. Before splicing, pre-load a heat-shrink splice protection sleeve (60mm) onto one fibre.
2. After a successful splice, slide the sleeve over the splice point, centred on the bare fibre.
3. Place the assembly into the splicer's built-in heater. Press the **HEAT** button.
4. The heater cycle takes approximately 30 seconds. The sleeve will shrink and the adhesive will bond.
5. When the heater LED turns green, remove the protected splice and place it into the splice tray. Route the fibre with a minimum bend radius of 30mm.

---

## 5. Electrode Maintenance

Electrodes are consumable components. Performance degrades gradually with use.

| Arc Count | Action |
|-----------|--------|
| 0–3,000 | Normal operation. No action required. |
| 3,000–5,000 | Monitor splice loss trends. Clean electrodes with electrode cleaning function (Menu → Maintenance → Electrode Clean). |
| 5,000+ | Replace electrodes. Order part: Fujikura ELCT2-20A (pair). Replacement procedure takes approximately 5 minutes — refer to the maintenance manual. |

After electrode replacement, run the **Arc Calibration** function (Menu → Maintenance → Arc Calibrate) using a test fibre. The splicer will auto-adjust arc power and duration. Perform three test splices and verify loss is within target before returning to production splicing.

---

## 6. Storage and Transport

- Always close the wind cover and power off the splicer before transport.
- Store in the original Fujikura carrying case with foam insert. Do not stack heavy items on top.
- Remove the battery if storing for more than 30 days.
- Keep the cleaver blade covered when not in use. The CT-50 blade lasts approximately 48,000 cleaves (16 positions × 3,000 cleaves per position).
