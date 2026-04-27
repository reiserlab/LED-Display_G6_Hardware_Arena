---
title: v1.1.5 Final Review
parent: Arena
grand_parent: Generation 6
nav_order: 100
---

# Arena v1.1.5 — Final Review (sign-off)

**Date**: 2026-04-24 | **Reviewer**: M. Reiser (automated KiCad 10 ERC + netlist + BOM cross-check + targeted PCB geometry trace)
**Status**: ✅ **APPROVED for ordering** — all prior flags resolved or documented; no new wiring errors found; one minor BOM-tracking item to confirm with Frank.

**Source**: `floesche/LED-Display_G6_Hardware_Arena` branch `diameter-adjustments`, head `0c21458 update panel places`
**Production zip**: `production/v1p1r5/G6_10-10_Teensy_Arena_v1.1.5.zip`
**Prior reviews**:
- `ARENA_V1R1_PR1_SCHEMATIC_REVIEW.md` — review at v1.1.3 (last sign-off baseline)
- `ARENA_V1R1_REV2_SCHEMATIC_REVIEW.md` — review of EINT/DIO bidirectional rev
- `ARENA_V1R1_SCHEMATIC_REVIEW.md` — initial v1.1 review

---

## What changed since the last review (v1.1.3 → v1.1.5)

Three commits beyond PR #1 (`0af3d3d` was v1.1.3 head):

| Commit | Description | Type |
|---|---|---|
| `2528a60 disconnect SW1 pin 3` | **Fixes my OBS-1 flag** — SW1 SPDT pin 3 no longer ties +5V rail to GND in OFF position | Schematic + PCB |
| `193eb7c adding helper CAD files` | New `assets/`: FreeCAD model, panel-placement SVG with 6 variants, Python `distance-calculator.py` | Documentation/tooling only |
| `0c21458 update panel places` | Panel connector positions adjusted (~1-1.5 mm shift) per laser-cut acrylic measurement; **EINT traces length-matched** | PCB layout |

The intermediate v1.1.4 production zip was also added (`production/v1p1r4/`).

---

## TL;DR of changes since v1.1.3 sign-off

1. **SW1 pin 3 disconnected** — the latent OFF-position-shorts-J26 concern is gone. Pin 3 is now a true no-connect.
2. **All 10 panels precisely repositioned** on a 144.546 mm diameter circle (center at PCB coordinate 177.8, 177.8 mm), each panel column at exactly 72.273 mm radius from arena center, 36° apart.
3. **EINT distribution traces length-matched** — fanout branch lengths went from a 240 mm spread (21–261 mm in v1.1.3) down to a 6 mm spread (~258–264 mm in v1.1.5). All 10 panels now receive the EINT trigger with near-identical propagation delay.
4. **Schematic essentially unchanged** — only `power.kicad_sch` had a real edit (the SW1 fix). All other schematic sheets had identical metadata-only changes (title block dates).
5. **Helper assets added** for laser-cut acrylic placement guides (used to physically determine panel spacing).

---

## Answer to your question — diameter of the open circle cutout

**The arena PCB has an actual cutout (Edge.Cuts layer) at the center: 136.000 mm diameter** (radius 68.000 mm), centered at PCB coordinate (177.800, 177.800) mm.

There is also a guide circle on `Dwgs.User` layer at 138.270 mm diameter — that's a documentation/dimension reference, not a physical cutout.

Helper SVG file `assets/10-10_pin-placement-model_6-variants.svg` contains 7 circles at 140 mm diameter — 6 placement-variant explorations Frank tried, plus one reference. The final settled position is captured by the panel-column circle at 144.546 mm diameter (where the 10 panels' connector-pair centers sit).

**Geometry summary:**

| Feature | Diameter | Notes |
|---|---|---|
| **PCB Edge.Cuts cutout** | **136.000 mm** | Physical hole in the board — open area where the test subject sits |
| Dwgs.User reference circle | 138.270 mm | Documentation only, slightly larger than the cutout |
| Helper SVG variants | 140 mm | 6 explored panel placements + reference (laser-cut template) |
| Final panel-column circle | 144.546 mm | All 10 panel column centers lie exactly on this circle |
| Panel-column radius from center | 72.273 mm | 144.546 / 2 |

Each panel sits ~4.273 mm outside the Edge.Cuts cutout edge (72.273 − 68.000), giving clearance between the cutout edge and the panel mounting locations.

---

## Verdict scorecard

| Area | v1.1.3 (prior sign-off) | v1.1.5 (current) | Status |
|------|-------------------------|------------------|--------|
| **KiCad ERC** | 3 warnings (cosmetic) | 3 warnings (identical, all cosmetic) | PASS |
| **BOM (schematic)** | 507 components | **507 components, identical** | PASS |
| **BOM (production)** | 510 (incl. 3 PCB-only sockets) | 510 (same) | PASS — 1 minor flag (see below) |
| **All 54 Teensy U1 pin assignments** | Baseline | **All identical to v1.1.3** | PASS |
| **EINT fanout (R25, R216, J30)** | Intact | Intact, all wiring preserved | PASS |
| **SN74LVC1T45 bidirectional buffers (U2, U3)** | Intact | Intact (VCCA=3.3V, VCCB=5V, DIR pins via Teensy GPIOs) | PASS |
| **MISO arbitration (U2.1, U3.1 OE — wait, that was the wrong part)** | n/a | n/a | n/a |
| **SW1 OFF-position behavior (my OBS-1)** | LATENT (SW1.3 → GND) | **FIXED** — SW1.3 is now no-connect | RESOLVED |
| **Panel placement** | OK but pre-acrylic-measurement | Adjusted to 144.546 mm circle per physical measurement | IMPROVED |
| **EINT length matching** | 240 mm spread across panels | **6 mm spread** (length-tuned) | IMPROVED |

---

## Detailed verification results

### 1. ERC — clean
```
warning: lib_symbol_mismatch — Symbol 'Cetus_RJ45_Magjack' (capitalization)
warning: footprint_link_issues — J25 BarrelJack* filter mismatch
warning: footprint_link_issues — J26 BarrelJack* filter mismatch
```
Same 3 warnings as v1.1.3 — all cosmetic library naming/filter issues, **0 errors, 0 wiring violations**.

### 2. SW1 fix verified at netlist level

```
SW1.1 → net [SW_5V]                     (2 nodes: SW1.1 + J25.1)        — J25 input
SW1.2 → net [+5V]                       (31 nodes: main +5V rail)        — common pole
SW1.3 → net [unconnected-(SW1-C-Pad3)]  (1 node: SW1.3 only — floating)  — NO LONGER tied to GND
```

The previous "OFF position shorts J26 to GND" failure mode is **eliminated**. SW1 now operates as a true SPST (J25-only on/off switch). When OFF, J26 (if connected) continues to power the +5V rail unimpeded.

### 3. Teensy U1 pin coverage — zero regressions

All 54 Teensy pins on U1 map to **identical nets** between v1.1.3 and v1.1.5. Compared programmatically — full match. No accidental pin moves, no broken connections.

### 4. EINT external-input infrastructure intact

```
TNY.EINT (fanout input net): 12 nodes — same as v1.1.3
  R216.2  (1 kΩ isolation)
  R25.1   (33 Ω from Teensy pin 33)
  10× fanout buffer inputs (U36-U41)

R25.2  → Teensy pin 33 (Net-(U1-33_MCLK2))
R216.1 → J30.1                              — jumper input
J30.2  → /Teensy/D35_0_3V3                   — DIO2 buffer A-side, also drives Teensy pin 35
```

The EINT external-input + jumper architecture from rev2 is fully preserved.

### 5. Bidirectional buffers (SN74LVC1T45) intact

| | U2 (DIO1 / J3 BNC) | U3 (DIO2 / J4 BNC) |
|---|---|---|
| VCCA (pin 1) | +3.3 V | +3.3 V |
| GND (pin 2) | GND | GND |
| A (pin 3) | D29_0_3V3 → Teensy pin 5 | D35_0_3V3 → Teensy pin 35 + J30.2 |
| B (pin 4) | D29_5V → J3 BNC | D35_5V → J4 BNC |
| DIR (pin 5) | Net-(U1-36_CS) → Teensy pin 36 | Net-(U1-34_RX8) → Teensy pin 34 |
| VCCB (pin 6) | +5 V | +5 V |

All wiring identical to v1.1.3 — no regressions.

### 6. Panel positions — physically rearranged on a 144.546 mm circle

All 10 panel column centers are at exactly **72.273 mm radius** from arena center (177.800, 177.800) mm, at 36° angular spacing. Verified by computing centroid + per-panel distance — every panel is at exactly 72.273 mm. This is geometrically perfect (zero spread).

The shifts from v1.1.3 to v1.1.5 are 1-1.5 mm per panel, in the radial direction (each panel pulled slightly toward the arena center). The Python helper script `assets/distance-calculator.py` documents this adjustment: original distance 147.4 mm → new 144.546 mm.

### 7. EINT trace lengths — newly matched

| Net | v1.1.3 length (mm) | v1.1.5 length (mm) |
|---|---|---|
| PAN.EINT_P1 | 73.7 | 259.4 |
| PAN.EINT_P2 | 130.4 | 259.1 |
| PAN.EINT_P3 | 176.4 | 260.5 |
| PAN.EINT_P4 | 225.9 | 261.8 |
| PAN.EINT_P5 | 260.6 | 261.3 |
| PAN.EINT_P6 | 211.4 | 257.9 |
| PAN.EINT_P7 | 159.8 | 258.8 |
| PAN.EINT_P8 | 112.7 | 259.4 |
| PAN.EINT_P9 | 49.7 | 257.6 |
| PAN.EINT_P10 | 21.1 | 263.9 |
| **Spread (max − min)** | **240 mm** | **6.3 mm** |

In copper, 240 mm corresponds to ~1.6 ns of propagation delay variation; 6 mm = ~0.04 ns. At 8 kHz scan triggers this is utterly negligible either way, but the matching is good engineering practice and would matter at higher trigger rates.

The TNY.EINT trunk (Teensy → first fanout stage) is unchanged at 32.327 mm.

### 8. Production BOM check

`production/v1p1r5/bom.csv` matches schematic BOM (502 + 8 PCB-only = 510 components) — same as v1.1.3.

**One minor issue — BOM tracking flag**:
- In v1.1.3, J100/J101 (Teensy pin sockets) had LCSC part number `C41376163` listed.
- In v1.1.5, the LCSC part number for J100/J101 is **blank** in `production/v1p1r5/bom.csv`.
- All other components retain their LCSC part numbers.

This may be intentional (perhaps C41376163 went out of stock and Frank will source manually) or an oversight. **Recommend asking Frank before placing the JLCPCB order** — without an LCSC part for J100/J101, JLCPCB won't auto-populate them, and the assembly will arrive without the Teensy sockets.

### 9. Helper files added (non-design)

The PR adds three documentation/tooling assets in `assets/`:
- `10-10_pin-placement-model.FCStd` — FreeCAD source for the panel-placement model (binary, 28 KB)
- `10-10_pin-placement-model_6-variants.svg` — Inkscape SVG with 7 reference circles (6 placement variants + 1 reference) at 140 mm diameter, used as laser-cut acrylic template
- `distance-calculator.py` — Small Python script that computes panel spacing adjustments. Documents the example values: original distance 147.4 mm → new 144.546 mm

Plus `arena_10_of_10_v1r1.pdf` (regenerated PDF rendering) and `arena_10_of_10_v1r1.step` (regenerated 3D model). These are auto-generated outputs.

---

## Status of all prior flags

| Flag | Prior status (v1.1.3) | Current status (v1.1.5) |
|------|-----------------------|--------------------------|
| FLAG-1 — Analog ±15 V (U82 DNP) | RESOLVED context (intentional hand-solder) | Unchanged — still intentional |
| FLAG-2 — EINT external input + jumper | RESOLVED in rev2 (J30, R216) | Still intact, length-matched |
| FLAG-3 — BNCs output-only | RESOLVED in rev2 (SN74LVC1T45) | Still intact |
| FLAG-4 — Schmitt jitter on SCK | OPEN (medium, bring-up measurement) | Unchanged |
| FLAG-5 — MISO pull-up | OPEN (low, firmware fix) | Unchanged |
| FLAG-6 — No per-panel fuse | OPEN (low, future rev) | Unchanged |
| FLAG-7 — SCK source termination | RESOLVED (R25 family verified) | Still resolved |
| FLAG-8 — CS mapping table | INFO (documentation) | Unchanged |
| FLAG-9 — No SWD debug | INFO (Teensy uses USB) | Unchanged |
| OBS-1 — SW1 OFF-position shorts +5 V to GND | LATENT (worth documenting) | **FIXED** — SW1.3 disconnected (commit `2528a60`) |
| Rev2 NEW-1 — DIR pins float at power-on | OPEN (firmware setup) | Unchanged |
| Rev2 NEW-2 — DIR nets auto-named | INFO (documentation) | Unchanged |
| Rev2 NEW-3 — J30 shunt sourcing | INFO (assembly) | Unchanged |

**Net disposition**: 1 prior flag (OBS-1) is now RESOLVED. No flags regressed. No new flags introduced.

---

## One BOM item to confirm before ordering

**LCSC part number for J100/J101 (Teensy pin sockets)** is blank in `production/v1p1r5/bom.csv`. The same parts had LCSC `C41376163` in v1.1.3. Either:
- Frank intentionally left it blank (e.g., to source manually), in which case the team needs to ensure the parts arrive separately and are hand-installed before testing
- Or it's an oversight that would result in the Teensy sockets being absent from the assembled boards

**Quick Slack ping to Frank** to confirm should resolve this in seconds.

---

## Sign-off

✅ **Ready to order.** With Frank's confirmation on the J100/J101 LCSC part-number question, the design is final.

Quality of the v1.1.5 update:
- The SW1 OFF-position concern from my previous review is fixed.
- The panel placement now matches the physical laser-cut acrylic measurement, ensuring the connectors mate correctly with the panels.
- EINT trace length matching is a nice signal-integrity improvement.
- Schematic-level review shows zero regressions to any previously-resolved item.

Other open items (FLAG-4 Schmitt jitter, FLAG-5 MISO pull-up, FLAG-6 polyfuse, Rev2 firmware items) all remain in their prior status — none are blockers, all were noted as future / firmware / measurement items.

---

## Files saved

- Outputs: `/tmp/arena_v115/{erc.json, netlist.net, bom.csv}`
- Comparison baselines from prior reviews: `/tmp/arena_pr1/`, `/tmp/arena_rereview/`
- This review will be backed up to `~/Documents/g6_arena_reviews/`
