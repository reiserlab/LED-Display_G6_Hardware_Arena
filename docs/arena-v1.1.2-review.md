---
title: v1.1.2 Changes
parent: Arena
grand_parent: Generation 6
nav_order: 99
---

# v1r2 Change Proposal: Digital Input BNC + EINT Jumper

**Target**: Arena v1r2 revision

**Purpose**: Add an external digital input path with the option to route either into the Teensy (software-handled) OR directly into the EINT fanout (hardware, bypasses Teensy latency)

**Priority**: HIGH — the external digital input is missing from v1r1 and is required for the intended use case

---

## What's needed vs what exists

### What exists on v1r1
- Two BNCs on the Teensy sheet: **J3** and **J4**
- Both wired as **unidirectional 5 V digital OUTPUTS** via SN74LV1T34DBV buffers (U3 for J3, U2 for J4)
- Teensy drives pin A (3.3 V) → level shifter outputs pin Y (5 V) → BNC center conductor
- EINT signal (`TNY.EINT` net) is hardwired to Teensy pin 33 only, via `R25`. No external input path.

### What's needed on v1r2
- **Keep J3 as a digital output** (unchanged — same SN74LV1T34 at VCC = 5 V)
- **Make J4 a digital input** (new: same chip but wired in the opposite direction, powered from VCC = 3.3 V)
- **Add a solder jumper** on the J4 output-side signal so it can route either:
  - **(A)** Into a Teensy GPIO (software-handled trigger — ~0.5–2 µs latency)
  - **(B)** Direct to the EINT fanout input at `R25.1` / `TNY.EINT` net (hardware-timed, no Teensy involvement)

---

## Why the same SN74LV1T34 works in both directions

The SN74LV1T34 is a **single-supply, single-gate buffer** where the direction and voltage levels are set purely by which rail you power it from. Per TI datasheet SCLS743E:

- **Pin A (pin 2, input)**: accepts **0–5.5 V regardless of VCC**
- **Pin Y (pin 4, output)**: swings 0 to VCC

So the same chip does two completely different jobs depending on VCC:

| Use case | VCC | A input | Y output | Direction |
|----------|-----|---------|----------|-----------|
| Output BNC (J3, as-is) | **+5 V** | Teensy 3.3 V → A | Y → BNC at 0–5 V | Teensy → world |
| **Input BNC (J4, new)** | **+3.3 V** | External 0–5 V → A | Y → Teensy at 0–3.3 V | World → Teensy |

**Same footprint, same part number, just swap pin 5 from +5 V to +3.3 V.** No new components to source, no new BOM line item, no new footprint.

---

## Minimum component list for the input BNC

4 components total — all already stocked or on the existing BOM:

| Ref | Part | Package | Purpose | Already on BOM? |
|-----|------|---------|---------|-----------------|
| J4 (repurposed) | BNC connector | Through-hole, same as J3/J27/J28/J29 | External signal entry | Yes (existing) |
| U2 (repurposed) | **SN74LV1T34DBV** | SOT-23-5 | 5 V → 3.3 V level-shift buffer | Yes (existing chip, just different VCC wiring) |
| R (new) | **~100 Ω resistor** | 0402 | Series resistor at BNC input for ESD/overcurrent limiting | Same 0402 family as other resistors |
| C (new) | **0.1 µF capacitor** | 0402 | VCC decoupling for U2 | Yes — 112 × 100 nF 0402 already in BOM |

No new sourcing. No new footprint patterns. BOM adds effectively one line item (the series resistor) if you want to track it separately.

---

## Wiring diagram

```
External source
     │
  [BNC J4 center]
     │
     ├──────[R_series 100 Ω, 0402]──────┬──── U2 pin 2 (A, input, 0–5 V tolerant)
     │                                  │
     │                              (optional TVS/clamp for ESD)
     │
  [BNC J4 shield] ──── GND

U2 pin 1 (NC) ──── leave open (no bond inside chip)
U2 pin 3 (GND) ──── GND
U2 pin 5 (VCC) ──── +3.3 V  ←── THIS IS THE KEY CHANGE vs v1r1 (was +5 V)
                      │
                   [0.1 µF to GND, 0402]

U2 pin 4 (Y, output) ──── → "INPUT_SIG" net
                                  │
                     ┌────────────┤         ◄── Solder jumper, 3 pads
                     │          ┌─┴─┐
                 [pad A]      [pad B]
                     │            │
                     │            │
                     │            │
       Teensy GPIO ──┘            └── TNY.EINT net (R25.1 side)
      (software-handled)         (direct to EINT fanout, bypasses Teensy)
```

### Signal flow

**Input side (BNC → chip)**:
- External source (e.g., microscope TTL line clock, function generator, another MCU) drives the BNC center conductor with a 0–5 V digital signal.
- Series resistor limits ESD/transient current, provides soft low-pass filtering (~300 MHz corner with typical input capacitance — invisible at kHz signal rates).
- Pin A accepts the 5 V signal even though VCC is 3.3 V. TTL-compatible input thresholds (VIH = 2.0 V, VIL = 0.8 V) mean the chip cleanly discriminates any reasonable logic signal.

**Output side (chip → jumper → destination)**:
- Pin Y drives a 0–3.3 V clean CMOS output, safe for Teensy GPIO input.
- Solder jumper selects destination:
  - **Pad A (software path)**: signal goes to a Teensy GPIO input pin. Firmware reads the state and optionally forwards it to the EINT fanout in software. Adds ~0.5–2 µs interrupt dispatch latency. Acceptable for most slow-kHz triggers; allows timestamping, debouncing, or other processing in firmware.
  - **Pad B (hardware path)**: signal ties directly to the `TNY.EINT` net at `R25.1`, feeding the EINT fanout tree and reaching all 20 panel connectors with no Teensy involvement. Zero-software-latency. Intended for high-rate precision triggers (many kHz).

---

## Jumper options (three alternatives — choose per preference)

| Option | Description | Cost | Reconfiguration effort | Tradeoffs |
|--------|-------------|------|------------------------|-----------|
| **3-pad solder jumper** | 3 copper pads, bridge two with a solder blob. Factory-default at one option; user cuts/re-solders to change. | ~$0 (just PCB copper) | Requires soldering iron, ~1 min | Smallest, no mechanical parts, but requires rework to change |
| **3-pin header + shunt** | Through-hole 0.1" header with removable plastic jumper shunt | ~$0.10 | Remove/reseat shunt, instant | Easy to change; shunt can be lost; adds ~8 mm of height |
| **SPDT slide switch** | Small panel-mount or SMD slide switch | ~$0.50–1.00 | Flip by hand, instant | Most convenient; could be accidentally bumped; adds cost |

**Default state**: regardless of which mechanism is used, default the jumper to the **hardware (direct) path** (signal tied to `TNY.EINT` net, bypassing Teensy), since that's the primary use case. Users who want software handling can reconfigure.

---

## Side concerns

### Hardware path caveat: Teensy pin 33 must be tri-stated

If the jumper is in **pad B (direct-to-EINT) mode**, the external signal ties directly to the same net that R25 feeds from Teensy pin 33. If the Teensy firmware leaves pin 33 as a driven output, the Teensy and the external source will fight.

**Firmware rule**: when using pad B (hardware direct), configure Teensy pin 33 as input (high-Z). The external signal is then the only driver of the net.

Alternatively: add a small series resistor (say 1 kΩ) between R25 and the original Teensy output, so if both drive, current is limited and the stronger signal wins. Slightly less clean but more fool-proof.

### Why not a bidirectional level-shifter (TXS0101 / SN74LVC1T45)?

A true bidirectional translator would let the BNC be either input or output under software control. Tempting for flexibility, but:
- More complex — requires a DIR pin from Teensy, or automatic direction-sensing logic that can oscillate in edge cases
- Different footprint (usually SC-70-6 or SOT-23-6, not SOT-23-5)
- New BOM line item, new sourcing
- For this application the BNCs serve fixed roles (one out, one in), so the added complexity has no payoff

Keeping one output + one input using the same SN74LV1T34 family is the cleanest minimum change.

### ESD protection (optional)

The SN74LV1T34 has built-in 2 kV HBM ESD protection per the datasheet — fine for bench use. If the arena will be used in environments with long cables or frequent hot-plug, add:
- **PESD5V0S1UB** (SOD-323 TVS diode, clamps ~6 V) between the BNC center and GND, on the BNC side of R_series

~$0.10, tiny footprint. Skip unless you specifically care.

---

## Summary for Will (one paragraph)

For v1r2, add one input BNC using the **same SN74LV1T34DBV chip** we already have for the output BNCs — just power it from **+3.3 V instead of +5 V**. The chip's A input tolerates 0–5.5 V regardless of VCC, so 5 V external signals still drive it cleanly, and the Y output is 0–3.3 V (safe for Teensy). Add a 100 Ω series resistor at the BNC center and a 0.1 µF decoupling cap on VCC. Then put a 2-position jumper on the output side (your pick between a 3-pad solder jumper, 3-pin header with shunt, or SPDT slide switch — see tradeoffs in the table above) that selects between (a) Teensy GPIO input for software-handled triggers and (b) direct tie to `R25.1` / `TNY.EINT` for hardware-timed trigger distribution to the panels. Total new parts (excluding the jumper mechanism): 1× BNC, 1× SN74LV1T34 (same P/N as U2/U3), 1× 100 Ω resistor, 1× 0.1 µF cap — all already on the BOM or sourced.

---

## References

- TI datasheet SCLS743E: *SN74LV1T34 Single Power Supply Single Buffer GATE CMOS Logic Level Shifter*
- Existing schematic: `designs/arena_10_of_10_v1r1/teensy.kicad_sch` (see U2, U3, J3, J4 placement)
- EINT fanout start point: `designs/arena_10_of_10_v1r1/fan_out.kicad_sch`, net `TNY.EINT`, component `R25` pin 1
- Full review doc: `ARENA_V1R1_SCHEMATIC_REVIEW.md` (FLAG-2 and FLAG-3 are what this change addresses)
