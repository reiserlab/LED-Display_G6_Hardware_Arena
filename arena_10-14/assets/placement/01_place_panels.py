#!/usr/bin/env python3
"""Place the arena panel-header ring (14-position ring, 10 panels populated).

The panel-header footprints (panel_silk:Panel_Silk) sit on a circle centered on
the board's grid origin (the arena center). The ring has 14 slots, 360/14 deg
(25.714... deg) apart; P1..P10 fill 10 of them and P11/P12 are not touched.

P2 is the anchor. It sits at X=-101.38, Y=0 in the SECONDARY (grid-origin)
coordinate system, with Y pointing up as KiCad displays it. That is NOT the
page coordinate system: the script reads (grid_origin) from the PCB and
converts display -> page with
    page_x = origin_x + X,   page_y = origin_y - Y.
P2 keeps the rotation it already has in the file. The radius is |X| = 101.38 mm.

  - P1 is one slot counterclockwise from P2 (rotation + pitch).
  - P3..P10 continue clockwise from P2, one slot each (rotation - pitch each).

How placement works in the .kicad_pcb:
  - A footprint's "(at x y angle)" sets its position and orientation.
  - Graphics (fp_line/fp_circle/...) are stored in the footprint LOCAL frame and
    rotate with it, so they are left untouched.
  - Text items (property/fp_text) store an ABSOLUTE angle that tracks the
    footprint angle, so each text angle is shifted by the footprint's rotation
    delta.

By default this is a DRY RUN (prints the plan, writes nothing). Pass --apply to
edit the file in place (a .bak copy is made first).
"""

from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import sys

# Script lives in <project>/assets/placement/; the PCB is two levels up.
PCB = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "..", "arena_10-14.kicad_pcb"))
PANELS = [f"P{i}" for i in range(1, 11)]   # P1..P10 are placed; P11/P12 untouched
N_SLOTS = 14                         # ring positions
PITCH = 360.0 / N_SLOTS              # 25.714285714285715 deg between neighbours
P2_X, P2_Y = -101.38, 0.0            # P2 in the grid-origin frame (Y up), mm

AT_RE = re.compile(r"\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?\)")


def fmt(v: float) -> str:
    """Format a number the way KiCad does: up to 6 decimals, no trailing zeros."""
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def norm_angle(a: float) -> float:
    a %= 360.0
    return a + 360.0 if a < 0 else a


def find_footprint_blocks(txt: str) -> dict[str, tuple[int, int]]:
    """Return {reference: (start, end)} char spans for each panel footprint."""
    spans: dict[str, tuple[int, int]] = {}
    for m in re.finditer(r'\n\t\(footprint ', txt):
        start = m.start() + 1
        end = txt.find('\n\t(footprint ', m.end())
        if end == -1:
            end = len(txt)
        block = txt[start:end]
        mref = re.search(r'\(property "Reference" "(P\d+)"', block)
        if mref:
            spans[mref.group(1)] = (start, end)
    return spans


def read_at(block: str) -> tuple[float, float, float]:
    """Footprint position/angle = the first (at ...) in the block."""
    m = AT_RE.search(block)
    x, y, a = m.group(1), m.group(2), m.group(3)
    return float(x), float(y), float(a or 0.0)


def get_grid_origin(txt: str) -> tuple[float, float]:
    m = re.search(r'\(grid_origin (-?[\d.]+) (-?[\d.]+)\)', txt)
    if not m:
        sys.exit("No grid_origin found; cannot determine arena center.")
    return float(m.group(1)), float(m.group(2))


def rewrite_block(block: str, nx: float, ny: float, nrot: float) -> str:
    """Set the footprint (at) to (nx,ny,nrot) and shift every text angle by the
    footprint rotation delta. Returns the modified block."""
    _, _, orot = read_at(block)
    delta = nrot - orot

    # Replace the footprint's own (at ...) -- the FIRST one in the block.
    first = AT_RE.search(block)
    new_fp_at = f"(at {fmt(nx)} {fmt(ny)} {fmt(norm_angle(nrot))})"
    block = block[:first.start()] + new_fp_at + block[first.end():]

    # Shift the angle of every remaining (at x y angle) (property / fp_text).
    # These all live after the footprint (at); walk them and add delta.
    out = []
    pos = first.start() + len(new_fp_at)
    out.append(block[:pos])
    for m in AT_RE.finditer(block, pos):
        if m.group(3) is None:      # 2-token (at x y): no angle, leave as is
            continue
        ang = norm_angle(float(m.group(3)) + delta)
        repl = f"(at {m.group(1)} {m.group(2)} {fmt(ang)})"
        out.append(block[pos:m.start()])
        out.append(repl)
        pos = m.end()
    out.append(block[pos:])
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcb", default=PCB, help=f"PCB file (default: {PCB})")
    ap.add_argument("--apply", action="store_true",
                    help="write changes (default: dry run)")
    args = ap.parse_args()

    txt = open(args.pcb, encoding="utf-8").read()
    spans = find_footprint_blocks(txt)
    missing = [p for p in PANELS if p not in spans]
    if missing:
        sys.exit(f"Missing panel footprints: {missing}")

    cx, cy = get_grid_origin(txt)
    R = math.hypot(P2_X, P2_Y)
    th2 = math.atan2(P2_Y, P2_X)                 # P2 angle on the ring, display frame
    rot2 = read_at(txt[slice(*spans["P2"])])[2]  # P2 keeps its current rotation
    pitch = math.radians(PITCH)

    print(f"grid origin (page) = ({fmt(cx)}, {fmt(cy)})  [secondary frame origin]")
    print(f"P2 anchor (display) = ({P2_X}, {P2_Y})  -> page ({fmt(cx + P2_X)}, {fmt(cy - P2_Y)})")
    print(f"radius {R:.3f} mm   pitch {PITCH:.6f} deg   P2 rotation {fmt(rot2)}\n")

    for n in range(1, 11):
        k = 1 if n == 1 else -(n - 2)    # slots from P2: P1 = +1 (CCW), P3.. = -1.. (CW)
        ang = th2 + k * pitch
        dispx, dispy = R * math.cos(ang), R * math.sin(ang)   # display frame, Y up
        x, y = cx + dispx, cy - dispy                         # -> page frame
        rot = norm_angle(rot2 + k * PITCH)
        ref = f"P{n}"
        s, e = spans[ref]
        old = read_at(txt[s:e])
        print(f"{ref:>3}: ({fmt(x)}, {fmt(y)}, {fmt(rot)})"
              f"   [display {dispx:+.2f}, {dispy:+.2f}]"
              f"   was ({fmt(old[0])}, {fmt(old[1])}, {fmt(old[2])})")
        new_block = rewrite_block(txt[s:e], x, y, rot)
        txt = txt[:s] + new_block + txt[e:]
        spans = find_footprint_blocks(txt)

    if args.apply:
        shutil.copyfile(args.pcb, args.pcb + ".bak")
        open(args.pcb, "w", encoding="utf-8").write(txt)
        print(f"\nWrote {args.pcb} (backup at {args.pcb}.bak)")
    else:
        print("\nDRY RUN -- no file written. Re-run with --apply to save.")


if __name__ == "__main__":
    main()
