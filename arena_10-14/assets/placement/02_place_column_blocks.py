#!/usr/bin/env python3
"""Replicate the P2 panel-column component block to every other panel column.

This arena populates 10 panel columns, P1..P10. Each has a panel-header
connector (P1..P10, the panel_silk footprint that 01_place_panels.py positions
on the ring) plus all its associated parts. Those parts come from two
hierarchical sub-schematics:
  - the panel-column sub-schematic (connectors J*, buffers U*, resistors R*,
    capacitors C*, the panel power fuse F*), instanced once per column, and
  - the CIPO-enable sub-schematic ("CIPO B0/B1 Enable for Pn"), also one per
    column, associated with the connector by the "for Pn" in its sheet name.

Panel column P2 is the TEMPLATE: this script measures every P2 part's placement
(both blocks) relative to the P2 connector (offset + rotation in the connector's
frame), then reproduces that same relative placement in every other column,
anchored to that column's own connector. The connectors themselves are left
exactly where 01_place_panels.py put them; only the associated parts move.

Matching across columns is by the footprint's hierarchical leaf UUID (the last
segment of its (path ...)), which is shared across all instances of a shared
sub-schematic. This is future-proof: any part added to the P2 column is picked
up automatically as long as the same instance exists in the target columns.
The fuse is matched the same way, so each column's fuse lands at F2's offset
from P2 no matter how the F references are numbered.

Columns beyond P10 (the schematic may still carry P11/P12) are ignored: their
parts are not moved, and their CIPO-enable sheets are skipped.

KiCad placement notes (same handling as 01_):
  - A footprint's "(at x y angle)" sets position and orientation.
  - Pad/graphic x/y and fp_line/circle/etc. are in the footprint LOCAL frame and
    rotate with it automatically, so their coordinates are left untouched.
  - Pad and text (fp_text/property) ANGLES are stored ABSOLUTE (board frame) in a
    placed footprint, so each is shifted by the footprint's rotation delta to
    stay locked to the footprint (relative angle preserved).

Default is a DRY RUN (prints the plan, writes nothing). Pass --apply to edit the
file in place (a .bak copy is made first).
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

TEMPLATE_COL = "P2"                       # column whose block is copied
N_PANELS = 10                             # populated columns P1..P10
CONNECTORS = [f"P{i}" for i in range(1, N_PANELS + 1)]

AT_RE = re.compile(r"\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?\)")
# CIPO-enable sub-sheets ("CIPO B0/B1 Enable for Pn") also belong to a column.
ENABLE_SHEETFILE = "cipo_enable.kicad_sch"
ENABLE_SHEET_RE = re.compile(r"Enable for (P\d+)")

# Shared dual fan-out buffers: each drives two adjacent panels with one Teensy
# signal (SCK/COPI/EINT). The 5x fan-out sheets pair them per bank as
# (P1,P2) (P3,P4) (P5,OUT_6) and (P6,P7) (P8,P9) (P10,OUT_6); OUT_6 is the spare
# sixth output. Only the buffer and its decoupling cap are shared; the panel series
# resistors are per-column. The P1/P2 buffers are the template (listed here).
# Every other buffer is found by connectivity (the panels its outputs feed) and
# moved by whole ring slots so that the panel its pad drives takes the place of
# the template's panel on that pad. The connectors are evenly spaced, so that is
# one rigid ring rotation per slot. See place_shared_buffers for the single-panel
# (P5, P10) buffers and the spare-output resistors.
SHARED_BUFFERS = ["U4", "U7", "U39"]     # SCK, COPI, EINT dual buffers (P1/P2 pair)
SHARED_CAPS    = ["C6", "C9", "C41"]     # their decoupling caps (one per buffer)
# buffer leaf -> its decoupling-cap leaf (position within a fan-out sheet); used to
# pick the right cap in each buffer's sheet-instance.
BUF_CAP_LEAF = {"313127c6": "e4a4fe85", "3dec7679": "7434dac7", "c7ec63a9": "1df1b107"}
# element keywords that own an (at ...); only text angles are absolute
TEXT_OWNERS = ("fp_text", "property", "gr_text")
OTHER_OWNERS = ("pad", "fp_line", "fp_circle", "fp_arc", "fp_poly",
                "fp_rect", "model", "footprint")


def fmt(v: float) -> str:
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def norm_angle(a: float) -> float:
    a %= 360.0
    return a + 360.0 if a < 0 else a


def kicad_rotate(x: float, y: float, deg: float) -> tuple[float, float]:
    """Rotate an offset by a KiCad footprint orientation.

    KiCad's Y axis points DOWN, and its footprint rotation (RotatePoint) is the
    opposite handedness of a standard math rotation: a positive footprint angle
    rotates counter-clockwise on screen, i.e. R(-angle) in ordinary (Y-up) math.
    KiCad places a footprint child by:  world = footprint_pos + rotate(local, a),
    so the inverse (world -> local) is rotate(world - pos, -a) with this same fn.
    """
    r = math.radians(-deg)
    c, s = math.cos(r), math.sin(r)
    return (x * c - y * s, x * s + y * c)


def swap_col(net: str, k: int, nets: set[str]) -> str:
    """Retarget a P2 column-tagged net to column k: swap the _P2 suffix and pick
    whichever SCK/COPI bank (B0/B1) column k's net actually has on the board, so
    the bank split between columns isn't hardcoded. Bankless nets (EINT, etc.)
    just get the suffix swapped."""
    net = re.sub(r"_P2$", f"_P{k}", net)
    if not re.search(r"_B[01]_", net):
        return net
    for bank in ("_B0_", "_B1_"):
        cand = re.sub(r"_B[01]_", bank, net)
        if cand in nets:
            return cand
    return net


def pad_nets(txt: str, fp: dict) -> dict[str, str]:
    """{pad number: net name} for one footprint (from its span)."""
    b = txt[fp["span"][0]:fp["span"][1]]
    d: dict[str, str] = {}
    for pm in re.finditer(r'\(pad "([^"]+)".*?\(net "([^"]*)"\)', b, re.S):
        d.setdefault(pm.group(1), pm.group(2))
    return d


def find_footprints(txt: str) -> dict[str, dict]:
    """Return {reference: {span, x, y, a, path, leaf, colinst}}."""
    out: dict[str, dict] = {}
    for m in re.finditer(r'\n\t\(footprint ', txt):
        start = m.start() + 1
        # End at this footprint's own closing paren (the next one-tab "\t)").
        # Ending at the next "(footprint" instead would make the LAST footprint's
        # span run over every track/via/zone after it, and rewrite_block would
        # then add an angle to every via (which KiCad rejects).
        end = txt.find('\n\t)', m.end())
        end = end + len('\n\t)') if end != -1 else len(txt)
        block = txt[start:end]
        mref = re.search(r'\(property "Reference" "([^"]+)"', block)
        if not mref:
            continue
        at = AT_RE.search(block)
        path = re.search(r'\(path "([^"]*)"', block)
        seg = path.group(1).strip("/").split("/") if path else []
        out[mref.group(1)] = dict(
            span=(start, end),
            x=float(at.group(1)), y=float(at.group(2)), a=float(at.group(3) or 0.0),
            path=path.group(1) if path else "",
            leaf=seg[-1] if seg else None,
            colinst=seg[1] if len(seg) >= 2 else None,
        )
    return out


def enable_instances(sch_path: str) -> dict[str, str]:
    """Map each CIPO-enable sheet-instance UUID -> connector reference.

    Footprints in the PCB don't carry sheet names, so the "... Enable for Pn"
    label (which tells us the connector) is read from the fan-out schematic. The
    sheet's own UUID is the path segment those footprints carry in the PCB.
    """
    try:
        sch = open(sch_path, encoding="utf-8").read()
    except OSError:
        return {}
    out: dict[str, str] = {}
    for m in re.finditer(r"\(sheet\b", sch):
        blk = sch[m.start():m.start() + 1600]
        name = re.search(r'\(property "Sheetname" "([^"]*)"', blk)
        sfile = re.search(r'\(property "Sheetfile" "([^"]*)"', blk)
        uu = re.search(r'\(uuid "([^"]+)"\)', blk)             # sheet's own uuid (first)
        if not (name and sfile and uu) or sfile.group(1) != ENABLE_SHEETFILE:
            continue
        mm = ENABLE_SHEET_RE.search(name.group(1))
        if mm:
            out[uu.group(1)] = mm.group(1)
    return out


def owner_before(block: str, pos: int) -> str | None:
    """Which element keyword most-recently opened before char `pos`."""
    best, besti = None, -1
    for kw in TEXT_OWNERS + OTHER_OWNERS:
        i = block.rfind("(" + kw + " ", 0, pos)
        if i > besti:
            besti, best = i, kw
    return best


def rewrite_block(block: str, nx: float, ny: float, nrot: float) -> str:
    """Set the footprint (at) and shift only text-element angles by the delta."""
    fp = AT_RE.search(block)
    orot = float(fp.group(3) or 0.0)
    delta = nrot - orot
    new_fp_at = f"(at {fmt(nx)} {fmt(ny)} {fmt(norm_angle(nrot))})"

    out = [block[:fp.start()], new_fp_at]
    pos = fp.end()
    for m in AT_RE.finditer(block, pos):
        out.append(block[pos:m.start()])
        pos = m.end()
        owner = owner_before(block, m.start())
        if owner in TEXT_OWNERS or owner == "pad":
            # In a placed footprint KiCad stores pad/text ANGLES in the board
            # (absolute) frame, while their x/y stay in the footprint-local
            # frame. So rotate the angle by the footprint's rotation delta to
            # keep the pad/text locked to the footprint (its relative angle,
            # angle - footprint_orientation, is preserved). Positions are local
            # and rotate with the footprint automatically, so they are untouched.
            if m.group(3) is None and abs(delta) < 1e-9:
                out.append(m.group(0))                       # absent, no rotation
            else:
                base = float(m.group(3)) if m.group(3) is not None else 0.0
                out.append(f"(at {m.group(1)} {m.group(2)} {fmt(norm_angle(base + delta))})")
        else:
            out.append(m.group(0))
    out.append(block[pos:])
    return "".join(out)


def to_local(conn: dict, x: float, y: float, a: float) -> tuple[float, float, float]:
    """World placement -> (offset x, offset y, angle delta) in a connector's frame."""
    lx, ly = kicad_rotate(x - conn["x"], y - conn["y"], -conn["a"])
    return lx, ly, a - conn["a"]


def to_world(conn: dict, lx: float, ly: float, da: float) -> tuple[float, float, float]:
    """Offset in a connector's frame -> world placement (inverse of to_local)."""
    gx, gy = kicad_rotate(lx, ly, conn["a"])
    return conn["x"] + gx, conn["y"] + gy, norm_angle(conn["a"] + da)


def panel_of(net: str | None) -> int | None:
    """Panel number of a PAN.*_Pn net (None for any other net, e.g. OUT_6)."""
    m = re.search(r"PAN\.\S*_P(\d+)$", net or "")
    return int(m.group(1)) if m else None


def buffer_legs(buf: str, pn: dict) -> dict[str, tuple[str | None, str | None]]:
    """{output pad: (series resistor, PAN net it feeds)} for a fan-out buffer.

    Each Net-(...) output runs to one series resistor whose other pad is the
    panel's PAN net; the spare output (OUT_6) has a resistor but no PAN net.
    """
    out = {}
    for pad, net in pn[buf].items():
        if not net.startswith("Net-("):
            continue
        r = next((r for r, d in pn.items() if r[0] == "R" and net in d.values()), None)
        pan = next((n for n in pn[r].values() if panel_of(n)), None) if r else None
        out[pad] = (r, pan)
    return out


def buffer_groups(pn: dict, nets: set[str]) -> dict[str, dict[str, list[int]]]:
    """{template buffer: {buffer: [panels it drives]}} over that buffer's signal.

    Each panel's series resistor for the signal (the template's P2-side PAN net,
    retargeted with swap_col) has its other pad on a buffer output, so that buffer
    drives the panel. This finds every buffer of the signal, whatever the pairing.
    """
    groups = {}
    for tbuf in SHARED_BUFFERS:
        pan2 = next(p for _, p in buffer_legs(tbuf, pn).values() if panel_of(p) == 2)
        drives: dict[str, list[int]] = {}
        for k in range(1, N_PANELS + 1):
            tgt = swap_col(pan2, k, nets)
            r = next((r for r, d in pn.items() if r[0] == "R" and tgt in d.values()
                      and any(n.startswith("Net-(") for n in d.values())), None)
            leg = next((n for n in pn[r].values() if n.startswith("Net-(")), None) if r else None
            buf = next((u for u, d in pn.items() if u[0] == "U" and leg in d.values()), None)
            if buf:
                drives.setdefault(buf, []).append(k)
        groups[tbuf] = drives
    return groups


def board_bbox(txt: str) -> tuple[float, float, float, float] | None:
    """(xmin, ymin, xmax, ymax) over the Edge.Cuts graphics, None if there are none."""
    pts = []
    for m in re.finditer(r"\n\t\(gr_\w+", txt):
        b = txt[m.start():txt.find("\n\t)", m.end())]
        if '(layer "Edge.Cuts")' in b:
            pts += [(float(x), float(y)) for x, y in
                    re.findall(r"\((?:start|end|mid|center|xy) (-?[\d.]+) (-?[\d.]+)\)", b)]
    if not pts:
        return None
    xs, ys = zip(*pts)
    return min(xs), min(ys), max(xs), max(ys)


def place_shared_buffers(txt, fps, pn, nets, edits):
    """Place every non-template fan-out buffer and its cap at the template's offset.

    A buffer moves by whole ring slots: the panel its output pad p drives takes
    the role of the panel the template's pad p drives (P1 or P2), and both outputs
    must agree (same pin order as the template). So a pair buffer (Pa, Pa+1) sits
    between Pa and Pa+1 the way U4 sits between P1 and P2, and a single-panel
    buffer (P5, P10: the other output is the spare OUT_6) sits where a pair
    buffer starting at that panel would. A buffer whose spot falls outside the
    board (Edge.Cuts bounding box; P10's, below the empty P11 slot) is left where
    it is. The spare-output resistors are never moved: their template spot is
    either another panel's series resistor (P5's points at P6) or off the board,
    so they are placed by hand. The cap is the C sharing the buffer's fan-out
    sheet instance (colinst) with the paired cap leaf.
    """
    bbox = board_bbox(txt)

    def on_board(x, y):
        return bbox is None or (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3])

    def cap_of(buf):
        cp = BUF_CAP_LEAF.get((fps[buf]["leaf"] or "")[:8], "\0")
        return next((c for c in fps if c[0] == "C"
                     and fps[c]["colinst"] == fps[buf]["colinst"]
                     and (fps[c]["leaf"] or "").startswith(cp)), None)

    def move(ref, x, y, a):
        s, e = fps[ref]["span"]
        edits.append((s, e, rewrite_block(txt[s:e], x, y, a)))

    groups = buffer_groups(pn, nets)
    placed: dict[int, list[str]] = {}               # target panel -> "tref->ref" notes
    spares = []
    print("Shared buffers/caps (moved by whole ring slots, template U4/U7/U39):")
    for tbuf, tcap in zip(SHARED_BUFFERS, SHARED_CAPS):
        tlegs = buffer_legs(tbuf, pn)
        for buf in groups[tbuf]:
            if buf == tbuf:
                continue
            legs = buffer_legs(buf, pn)
            spares += [r for r, pan in legs.values() if r and not pan]
            # (template panel, this buffer's panel) per used output pad
            roles = sorted((panel_of(tlegs[pad][1]), panel_of(pan))
                           for pad, (_, pan) in legs.items() if pan and pad in tlegs)
            if not roles or len({k - t for t, k in roles}) != 1:
                print(f"  WARNING: {buf} outputs are not in {tbuf}'s pin order "
                      f"(template panel -> panel: {roles}); left where it is.")
                continue
            t, k = roles[0]
            src, dst = fps[f"P{t}"], fps[f"P{k}"]
            moves = [(tref, ref) for tref, ref in ((tbuf, buf), (tcap, cap_of(buf))) if ref]
            spots = {ref: to_world(dst, *to_local(src, fps[tref]["x"], fps[tref]["y"],
                                                  fps[tref]["a"]))
                     for tref, ref in moves}
            if not all(on_board(x, y) for x, y, _ in spots.values()):
                print(f"  WARNING: {buf} (P{k}) would land off the board (outside the "
                      f"Edge.Cuts bounding box); left where it is, with its cap.")
                continue
            for tref, ref in moves:
                move(ref, *spots[ref])
            placed.setdefault(k, []).extend(f"{tref}->{ref}" for tref, ref in moves)

    for k in sorted(placed):
        print(f"  P{k}: {', '.join(placed[k])}")
    if spares:
        print(f"  Spare-output (OUT_6) resistors, not moved (place by hand): "
              f"{', '.join(sorted(spares, key=lambda r: int(r[1:])))}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcb", default=PCB, help=f"PCB file (default: {PCB})")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    txt = open(args.pcb, encoding="utf-8").read()
    fps = find_footprints(txt)

    missing = [c for c in CONNECTORS if c not in fps]
    if missing:
        sys.exit(f"Missing panel connectors: {missing}")

    conn_leaf = fps[TEMPLATE_COL]["leaf"]

    # Map path-segment UUIDs to a connector:
    #   - each connector's own panel-column sheet-instance (its 2nd path segment)
    #   - each CIPO-enable sheet-instance ("... Enable for Pn"), read from the
    #     fan-out schematic since footprints don't store sheet names
    seg2conn = {fps[c]["colinst"]: c for c in CONNECTORS}
    sch_path = os.path.join(os.path.dirname(os.path.abspath(args.pcb)), "fan_out.kicad_sch")
    all_enables = enable_instances(sch_path)
    enables = {u: c for u, c in all_enables.items() if c in CONNECTORS}
    seg2conn.update(enables)
    if enables:
        skipped = sorted(set(all_enables.values()) - set(CONNECTORS), key=lambda p: int(p[1:]))
        print(f"CIPO-enable blocks: {len(enables)} instances -> "
              f"{sorted(set(enables.values()), key=lambda p: int(p[1:]))}"
              + (f"  (ignored, beyond P{N_PANELS}: {skipped})" if skipped else ""))
    else:
        print(f"WARNING: no CIPO-enable sheets found (looked in {sch_path}); "
              f"placing panel-column blocks only.")

    # Group every associated footprint (panel-column + CIPO-enable) by connector,
    # keyed by hierarchical leaf UUID (shared across the repeated sub-sheets).
    columns: dict[str, dict[str, str]] = {c: {} for c in CONNECTORS}   # col -> {leaf: ref}
    for ref, f in fps.items():
        conn = next((seg2conn[s] for s in f["path"].strip("/").split("/") if s in seg2conn), None)
        if conn:
            columns[conn][f["leaf"]] = ref

    # template: relative transform of each P2 part (excluding the connector)
    anchor = fps[TEMPLATE_COL]
    template = {}   # leaf -> (rel_x, rel_y, rel_a, template_ref)
    for leaf, ref in columns[TEMPLATE_COL].items():
        if leaf == conn_leaf:
            continue
        f = fps[ref]
        lx, ly = kicad_rotate(f["x"] - anchor["x"], f["y"] - anchor["y"], -anchor["a"])
        template[leaf] = (lx, ly, f["a"] - anchor["a"], ref)
    print(f"Template = column {TEMPLATE_COL} ({fps[TEMPLATE_COL].get('leaf','')[:8]} connector), "
          f"{len(template)} parts relative to {TEMPLATE_COL}.")
    fuse_leaves = {leaf for leaf, (*_, tref) in template.items() if tref.startswith("F")}
    if fuse_leaves:
        print(f"Template fuse(s): {sorted(template[l][3] for l in fuse_leaves)}\n")
    else:
        print(f"WARNING: no fuse (F*) in the {TEMPLATE_COL} column block; fuses won't be placed.\n")

    # Per-column series output resistors (Fan-Out): each has one pad on a shared
    # buffer output (Net-(R..-Pad1)) and the other on a PAN.*_P2 panel net. They
    # are the last per-column hop before the shared buffer, so they replicate per
    # column (one ring slot) like the panel-column parts, mapped by their PAN net.
    pn = {ref: pad_nets(txt, f) for ref, f in fps.items()}
    nets = {n for d in pn.values() for n in d.values()}
    buf_out = {n for buf in SHARED_BUFFERS if buf in fps
               for n in pn[buf].values() if n.startswith("Net-(")}
    series = []   # (pan_net_P2, rel_x, rel_y, rel_a)
    for ref, d in pn.items():
        if ref[0] != "R" or not (buf_out & set(d.values())):
            continue
        pan = [n for n in d.values() if n.endswith("_P2") and n not in buf_out]
        if pan:
            f = fps[ref]
            lx, ly = kicad_rotate(f["x"] - anchor["x"], f["y"] - anchor["y"], -anchor["a"])
            series.append((pan[0], lx, ly, f["a"] - anchor["a"]))
    if series:
        print(f"Per-column series resistors: {len(series)} "
              f"({', '.join(p for p, *_ in series)}).\n")

    edits = []   # (start, end, newtext)
    for col in CONNECTORS:
        if col == TEMPLATE_COL:
            print(f"{col}: template, left unchanged.")
            continue
        cfp = fps[col]                      # this column's connector (fixed anchor)
        k = int(col[1:])
        members = columns[col]
        placed = missing_here = 0
        samples, fuses = [], []
        for leaf, (lx, ly, da, tref) in template.items():
            ref = members.get(leaf)
            if not ref:
                missing_here += 1
                continue
            gx, gy = kicad_rotate(lx, ly, cfp["a"])
            nx, ny = cfp["x"] + gx, cfp["y"] + gy
            na = norm_angle(cfp["a"] + da)
            s, e = fps[ref]["span"]
            edits.append((s, e, rewrite_block(txt[s:e], nx, ny, na)))
            placed += 1
            if leaf in fuse_leaves:
                fuses.append(f"{ref}->({fmt(nx)},{fmt(ny)},{fmt(na)})")
            elif len(samples) < 1:
                samples.append(f"{ref}->({fmt(nx)},{fmt(ny)},{fmt(na)})")
        for pan, lx, ly, da in series:               # this column's series resistors
            tref = next((r for r in fps
                         if r[0] == "R" and swap_col(pan, k, nets) in pn[r].values()), None)
            if tref:
                gx, gy = kicad_rotate(lx, ly, cfp["a"])
                s, e = fps[tref]["span"]
                edits.append((s, e, rewrite_block(txt[s:e], cfp["x"] + gx, cfp["y"] + gy,
                                                  norm_angle(cfp["a"] + da))))
                placed += 1
        extra = [members[l] for l in members if l not in template and l != conn_leaf]
        note = f"  UNMATCHED template parts: {missing_here}" if missing_here else ""
        note += f"  extra-not-in-template: {extra}" if extra else ""
        note += "  NO FUSE" if fuse_leaves and not fuses else ""
        print(f"{col}: connector at ({fmt(cfp['x'])},{fmt(cfp['y'])},{fmt(cfp['a'])}), "
              f"placed {placed} parts. fuse {', '.join(fuses) or '-'}; "
              f"e.g. {', '.join(samples)}{note}")

    # shared dual-buffers + caps, moved by whole ring slots from the template
    place_shared_buffers(txt, fps, pn, nets, edits)

    starts = [s for s, _, _ in edits]
    if len(starts) != len(set(starts)):
        sys.exit("A footprint would be moved twice (overlapping edits); nothing written.")

    # apply edits back-to-front so spans stay valid
    for s, e, newtext in sorted(edits, key=lambda t: t[0], reverse=True):
        txt = txt[:s] + newtext + txt[e:]

    if args.apply:
        shutil.copyfile(args.pcb, args.pcb + ".bak")
        open(args.pcb, "w", encoding="utf-8").write(txt)
        print(f"\nWrote {args.pcb} (backup at {args.pcb}.bak); {len(edits)} footprints moved.")
    else:
        print(f"\nDRY RUN -- no file written ({len(edits)} footprints would move). "
              f"Re-run with --apply to save.")


if __name__ == "__main__":
    main()
