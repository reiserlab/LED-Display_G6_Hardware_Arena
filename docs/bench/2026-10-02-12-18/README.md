# 12-18 bench results, 2026-10-02

One afternoon on the **12-18 controller** (`04:E9:E5:1F:D1:72`, **12 panels fitted** in one row of a 4×12 layout), Windows lab PC, COM5.
Covers firmware #58 (Qwiic bridge), #59 (boot + panel inventory), a power and ground map, and the first hardware run of the analog-input work (#46 / #47).

Firmware run: #58 `e40e2a4` · #59 `c15d840` · main `12bba7e` · analog `e08f26d` (`feat/ai-calibration`), all `teensy41-12-18-performance`.
Raw logs are in [`runs/`](runs/), the bench scripts in [`scripts/`](scripts/).

## Status

| Item | Result | What it means |
|---|---|---|
| fw #58 Qwiic stuck-bus (A3) | **PASS** | Merge gate met. A1/A2 suites also pass. |
| fw #59 inventory (B1) | **PASS** | 11 passed, 2 skipped (no panel image on SD). Reset test blocked by a Windows harness gap. B2 not run. |
| Analog ground shift under load | **FINDING** | Analog-section ground rises 6 mV; readings shift +28–30 mV. Board-level fix needed. |
| 5 V input droop | **FINDING** | −137 mV at 12 panels. UVLO margin looks thin at 48 panels. |
| AI1 two-point calibration | **FAILS ACCURACY** | Reads +9.6 % high on an AO loopback. Likely cause: the +10 V point is clipped. Needs a DMM to confirm. |
| AI2 channel | **DEAD** | Same reading open or capped. Front end not reaching the ADC. |
| 12-18 SD card interface | **FAULT** | Reads and purge fail on two cards and two firmware builds. 3.3 V is fine. Suspect the Teensy SD slot. |
| Panel current (E4), ripple (E3), #59 B2 | not run | Out of time. |

## Power and ground map (E1, E2)

DMM readings while a script switched All On / All Off every 5 s for 60 s (`scripts/toggle_load.py`). Load is 12 panels.

| Point (red probe) | Reference (black) | Dark | All On | Change |
|---|---|---:|---:|---:|
| AI1, AI2 and AO BNC shells (analog-section ground) | Teensy GND | +1 mV | +7 mV | **+6 mV** |
| Barrel jack − | Teensy GND | −13 mV | −65 mV | **−52 mV** |
| Barrel jack + | Barrel jack − | 5.187 V | 5.050 V | **−137 mV** |
| Teensy 3V3 | Teensy GND | 3.289 V | 3.287 V | −2 mV |

Ground potential at All On, relative to the Teensy GND: **barrel jack − −65 mV → Teensy GND 0 → analog section +7 mV.**
Most of the drop (52 mV) is on the main return path from the Teensy to the power jack. The small 6 mV step between the Teensy and the analog section is the one that reaches the analog readings.

**Analog ground shift.** With the inputs capped, AI1 and AI2 both read **+28 to +30 mV** higher at All On than dark, in every run. That matches the 6 mV ground difference multiplied by the input stage's attenuation (about 5×), and reproduces the +33 mV seen on 09-10. Calibration cannot remove it, because it changes with display load. This is the case for the analog ground island (LAB-219).

**5 V input margin.** The jack drops 137 mV with 12 panels lit. If the drop scales with current, a full 48-panel arena would see about 0.55 V, leaving the jack near **4.64 V**: below 4.7 V and about 0.13 V above the 4.5 V cutoff in eFuse design #1. A switching transient could trip it.

> The 48-panel figures are linear extrapolations from 12 panels, not measurements. E4 (panel current) is still needed to turn these drops into resistances.

## Analog input (#46 / #47)

Firmware `e08f26d`, first run of this code on hardware.

**HIL suite: 9 / 9 PASS** (`test_analog_cal.py` + `test_io_roles.py`, incl. the channel-2 check that a single calibration point leaves the channel invalid).

### T1: open vs capped, uncalibrated (dark, 200 samples)

| Channel | State | Reading | Raw (12-bit) | Noise | Expected |
|---|---|---:|---:|---:|---|
| AI1 | capped | 314 mV | 2112 | 2.5 cnt | ≈ 0 V (the offset calibration removes) |
| AI1 | open | 9999.9 mV | 4095 | 0.1 cnt | ≈ +10 V, **but 4095 is the ADC's full scale** |
| AI2 | capped | 5636 mV | 3201 | 3.7 cnt | ≈ 0 V |
| AI2 | open | 5636 mV | 3201 | 3.8 cnt | ≈ +10 V |

**AI2 does not see its input.** It reads 3201 counts whether its BNC is capped or open, so the BNC signal is not reaching the ADC. The ADC pin is alive (it shifts with display load like AI1). Something in the AI2 front end is open or missing; R179 / R181 (flagged on 09-10, divider ≈ 0.26 instead of 1/3) is the first place to look. AI2 was not calibrated.

### AI1 calibrated: noise (T3) and persistence (C2)

| AI1 capped | Mean | Std | Range |
|---|---:|---:|---:|
| Dark | −0.3 mV | 13.2 mV (2.5 cnt) | −25 … +20 |
| All On | +27.4 mV | 9.6 mV (1.5 cnt) | −5 … +45 |
| Dark again | −0.4 mV | 12.2 mV (2.5 cnt) | −20 … +20 |
| After power-cycle | −0.8 mV | 12.3 mV | — |

- Calibration takes the capped offset from 314 mV to under 1 mV, and the EEPROM record survives a power-cycle (C2 pass). One count is about 5 mV.
- Noise is 2.5 counts dark, slightly above the 1–2 count target, and gives a measured bound of about ±25 mV for fw issue #63.
- The default 20 mV Mode 4 deadband is about 1.5σ of this noise, so the closed loop would twitch. 35–40 mV (about 3σ) is the better default.

### C1: accuracy check, AO (J27) looped back into AI1

| AO setpoint | AI1 (calibrated) | AI1 − setpoint | Std |
|---:|---:|---:|---:|
| 1.000 V | 1.067 V | +67 mV | 12 mV |
| 2.500 V | 2.712 V | +212 mV | 14 mV |
| 5.000 V | 5.451 V | +451 mV | 13 mV |

**Calibration gain is about 9.6 % high.** The error is a straight line, about +9.6 % gain and −29 mV offset, far outside the 20 mV target. The likely cause is the calibration method: the "open input = +10 V" point read 4095, the ADC's maximum, so the ADC is already saturated there. If saturation starts near 9.1 V at the input, every calibrated reading is inflated by 10 / 9.1, which matches.

**Not yet confirmed:** the DMM was not read at the three AO steps, so an AO error has not been ruled out. The AO only reaches 0–5 V, so the negative half of the range is untested. The incorrect AI1 calibration is still stored in the 12-18's EEPROM.

## Firmware #58 and #59

| Test | Result | Detail |
|---|---|---|
| #58 A1/A2 | PASS | Qwiic suite 10 passed, 2 skipped (no I2C mux). TSL2591, VEML7700, AS7343 identified and read; feature-bit test passed for the first time on hardware. |
| #58 A3 | PASS | SDA/SCL shorted to GND 5× over 60 s: 45 scans returned status 4 (bus stuck), each on the next scan; recovered on release; worst scan 18 ms; no resets or USB drops. |
| #59 B1 | PASS | 11 passed, 2 skipped (no `/firmware/panel.bin` on SD). First two-page (48-slot) inventory read on hardware. |
| #59 reset test | blocked | The test harness keeps one serial port open; on Windows the port dies when the Teensy reboots, so every later test fails. Harness gap, not firmware. |
| #59 B2 | not run | PE02 / PE03 panel glyphs were seen during B1's resets and rescans. Unexplained; B2 is the controlled test for it. |

Hot-plugging the Qwiic chain into J2 with the arena powered produced PE2 glyphs and probably reset the controller. Plug sensors in with power off.

## 12-18 SD card fault

- The card mounts and the file count reads, but `GET_PATTERN_INFO` and `PURGE_MEMORY` both return status 4.
- Same result with a known-good card from another arena, on fw #59 and on fw main, and with the Qwiic chain unplugged. The first card was hot when removed.
- 3.3 V is steady under load, so a sagging supply is ruled out. Next step: swap the Teensy 4.1.

## Next steps

- Repeat the AO loopback with a DMM on the node to confirm the clipped-calibration explanation, then clear or redo the AI1 calibration.
- Rework the #47 calibration so the high point sits below ADC full scale (for example a known AO voltage).
- Inspect AI2's front end (R179 / R181 area).
- Measure panel current (E4) so the ground and 5 V drops become resistances for the board redesign.
- Run #59 B2 (reset cycling + cold power-up) and explain the PE02 / PE03 glyphs.
- Swap the 12-18's Teensy to settle the SD fault.

## Files

- `runs/`: the raw output of every scripted run (stuck bus, inventory, E1/E2 runs, T1, C1/T3, C2, AO loopback).
- `scripts/`: `toggle_load.py` (All On/Off cycling + AI logging), `ai_read.py` (AI mean/std/raw), `ao_ai_steps.py` (AO→AI1 loopback), `qwiic_stuck_bus.py` (A3), `verify.py` (B2). Run them from a firmware worktree root with `ARENA_PORT=COMx`; they import the firmware repo's `tests.transport`.
