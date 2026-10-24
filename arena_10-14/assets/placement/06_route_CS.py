#!/usr/bin/env python3
"""Copy the CS_08..11 group's internal routing onto the other CS fan-out groups.

05_place_cs_fanout.py places the five CS fan-out groups (group j = CS_(4j)..CS_(4j+3),
one buffer + cap + two series resistors per CS) around the ring. The CS_08..11
group (P3/P8) is routed by hand and is the TEMPLATE here. Its INTERNAL routing is
every run of connected tracks/vias on one of its pad nets that touches a group pad
and stays within REGION mm of the group's pads:
    U -> R links (Net-(R..-Pad1)), the +3.3V/GND stubs and vias,
    the TNY.CS_* input bridge between the buffer's two inputs (U.1 - U.3).
A run that leaves the group (PAN.CS_* out to a panel, TNY.CS_* to the Teensy, a
power trunk) is a fan-out route; it is not copied, and it is listed.

Each target group is reproduced relative to its OWN parts, not to its anchor
connector: the rigid rotate+translate that takes the template's first buffer (U24)
onto the target's (U16, U20, ...). A group moved or rotated by hand as a whole
still gets its routing. Every pad of the target group must then sit where that
transform puts the template's pad; if one doesn't, the group is skipped and the
off pads are listed, so no copied track ends beside a part. Per target group:
  1. delete its current internal routing (same rule), so a re-run replaces the
       copies instead of stacking them; its fan-out routes are kept,
  2. add the template's internal routing through the transform, nets remapped
       pad by pad (template pad net -> the same pad's net in the target group;
       power nets kept).

05 still copies the CS_00..03 group's routing onto the other groups, CS_08..11
included, so re-running 05 replaces this template's U -> R links. Run 06 after
05, and re-route CS_08..11 by hand first if 05 has touched it.

Default is a DRY RUN. Pass --apply to write (a .bak copy is made first).
"""

from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import sys
import uuid
from collections import defaultdict

PCB = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "arena_10-14.kicad_pcb"))

TEMPLATE_GROUP = 2                 # CS_08..11 (the P3/P8 group), routed by hand
GROUP_SIZE = 4                     # CS signals per group: group j = CS_(4j)..CS_(4j+3)
REGION = 3.0                       # mm from a group pad that internal routing stays within
PAD_TOUCH = 0.4                    # mm: a track end this close to a pad centre is on the pad
PAD_TOL = 0.005                    # mm: target pad vs transformed template pad
MIN_LEN = 0.001                    # mm: shorter template segments are routing leftovers, not copied
POWER_NETS = {"GND", "+3.3V", "+5V", "+5VP", "+3V3", "GNDA"}

AT_RE = re.compile(r"\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?\)")
COORD_RE = re.compile(r"\((start|end|mid|at) (-?[\d.]+) (-?[\d.]+)((?: -?[\d.]+)?)\)")
PAD_RE = re.compile(r'\(pad "([^"]*)" \w+.*?\(at (-?[\d.]+) (-?[\d.]+)[^)]*\)(.*?)(?=\n\t\t\(pad |\Z)', re.S)


def fmt(v: float) -> str:
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def krot(x: float, y: float, deg: float):
    r = math.radians(-deg)
    c, s = math.cos(r), math.sin(r)
    return (x * c - y * s, x * s + y * c)


def parse(txt, pcb):
    """footprints (ref -> {x,y,a,leaf,cs,pads}) and tracks (list)."""
    sch = open(os.path.join(os.path.dirname(os.path.abspath(pcb)), "fan_out.kicad_sch"),
               encoding="utf-8").read()
    cs_by_uuid = {}
    for m in re.finditer(r"\(sheet\b", sch):
        blk = sch[m.start():m.start() + 1600]
        nm = re.search(r'\(property "Sheetname" "([^"]*)"', blk)
        uu = re.search(r'\(uuid "([^"]+)"\)', blk)
        if nm and uu:
            mm = re.search(r"CS_(\d+) .*fan ?out", nm.group(1), re.I)
            if mm:
                cs_by_uuid[uu.group(1)] = int(mm.group(1))

    fps = {}
    for m in re.finditer(r"\n\t\(footprint ", txt):
        s = m.start() + 1
        e = txt.find("\n\t)", m.end())
        b = txt[s:e]
        ref = re.search(r'\(property "Reference" "([^"]+)"', b)
        if not ref:
            continue
        at = AT_RE.search(b)
        fx, fy, fa = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0.0)
        path = re.search(r'\(path "([^"]*)"', b)
        seg = path.group(1).strip("/").split("/") if path else []
        pads = {}
        # each pad's own body only, so a pad without a net can't take the next pad's
        for pm in PAD_RE.finditer(b):
            net = re.search(r'\(net "([^"]*)"\)', pm.group(4))
            gx, gy = krot(float(pm.group(2)), float(pm.group(3)), fa)
            pads[pm.group(1)] = (fx + gx, fy + gy, net.group(1) if net else None)
        fps[ref.group(1)] = dict(x=fx, y=fy, a=fa, leaf=seg[-1] if seg else None,
                                 cs=next((cs_by_uuid[x] for x in seg if x in cs_by_uuid), None),
                                 pads=pads)

    tracks = []
    for m in re.finditer(r"\n\t\((segment|via|arc)\b", txt):
        s = m.start() + 1
        e = txt.find("\n\t)", m.end()) + len("\n\t)")
        blk = txt[s:e]
        net = re.search(r'\(net "([^"]*)"\)', blk)
        co = [(k, float(a), float(b)) for k, a, b, _ in COORD_RE.findall(blk)]
        tracks.append(dict(s=s, e=e, text=blk, kind=m.group(1), net=net.group(1) if net else None,
                           pts=[(x, y) for _, x, y in co],
                           ends=[(x, y) for k, x, y in co if k != "mid"]))
    return fps, tracks


def runs_by_net(tracks):
    """net -> runs: lists of track indices joined end to end (a via joins at its centre)."""
    by_net = defaultdict(list)
    for i, t in enumerate(tracks):
        if t["net"] is not None and t["pts"]:
            by_net[t["net"]].append(i)
    out = {}
    for net, idxs in by_net.items():
        parent = {i: i for i in idxs}

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        seen = {}
        for i in idxs:
            for x, y in tracks[i]["ends"]:
                key = (round(x, 3), round(y, 3))
                if key in seen:
                    parent[find(i)] = find(seen[key])
                else:
                    seen[key] = i
        runs = defaultdict(list)
        for i in idxs:
            runs[find(i)].append(i)
        out[net] = list(runs.values())
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcb", default=PCB)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    txt = open(args.pcb, encoding="utf-8").read()
    fps, tracks = parse(txt, args.pcb)
    runs = runs_by_net(tracks)

    # ---- group -> {(cs_k, leaf): ref}: the same sub-sheet part in every group ---
    groups = defaultdict(dict)
    for ref, f in fps.items():
        if f["cs"] is not None:
            groups[f["cs"] // GROUP_SIZE][(f["cs"] % GROUP_SIZE, f["leaf"])] = ref
    if TEMPLATE_GROUP not in groups:
        sys.exit(f"No CS group {TEMPLATE_GROUP} found in fan_out.kicad_sch")
    tg = groups[TEMPLATE_GROUP]

    def label(j):
        return f"CS_{GROUP_SIZE * j:02d}..{GROUP_SIZE * j + GROUP_SIZE - 1:02d}"

    def internal(j):
        """(track indices of group j's internal routing, nets of its runs that leave it)."""
        pads = [(x, y) for ref in groups[j].values() for x, y, _ in fps[ref]["pads"].values()]
        nets = {n for ref in groups[j].values() for _, _, n in fps[ref]["pads"].values() if n}

        def dist(p):
            return min(math.hypot(p[0] - x, p[1] - y) for x, y in pads)
        keep, leaving = [], set()
        for net in nets:
            for run in runs.get(net, []):
                if not any(dist(p) < PAD_TOUCH for i in run for p in tracks[i]["ends"]):
                    continue
                if all(dist(p) < REGION for i in run for p in tracks[i]["pts"]):
                    keep += run
                else:
                    leaving.add(net)
        return keep, leaving

    tmpl, leaving = internal(TEMPLATE_GROUP)
    if not tmpl:
        sys.exit(f"The {label(TEMPLATE_GROUP)} template group has no internal routing.")
    print(f"template {label(TEMPLATE_GROUP)}: {len(tmpl)} internal tracks on "
          f"{len({tracks[i]['net'] for i in tmpl})} nets")
    stubs = {i for i in tmpl if tracks[i]["kind"] == "segment"
             and math.dist(*tracks[i]["ends"]) < MIN_LEN}
    if stubs:
        print(f"  {len(stubs)} zero-length segments, not copied")
    if leaving:
        print(f"  fan-out runs, not copied: {', '.join(sorted(n.split('/')[-1] for n in leaving))}")

    # the template's first buffer is the reference part the transform is taken on
    ref_key = min((k for k, r in tg.items() if r.startswith("U")), key=lambda k: (k[0], tg[k]))
    rt = fps[tg[ref_key]]

    tmpl_ids = set(tmpl)
    dels, additions = set(), []
    for j in sorted(groups):
        if j == TEMPLATE_GROUP:
            continue
        g = groups[j]
        missing = [tg[k] for k in tg if k not in g]
        if missing:
            print(f"SKIP {label(j)}: no counterpart for {', '.join(sorted(missing))}")
            continue
        ru = fps[g[ref_key]]
        da = ru["a"] - rt["a"]

        def tp(x, y, ru=ru, da=da):
            gx, gy = krot(x - rt["x"], y - rt["y"], da)
            return ru["x"] + gx, ru["y"] + gy

        # every template pad must have its target pad at the transformed spot
        off, nm, clash = [], {}, set()
        for k, tref in tg.items():
            uref = g[k]
            for pad, (x, y, net) in fps[tref]["pads"].items():
                tgt = fps[uref]["pads"].get(pad)
                ex, ey = tp(x, y)
                if not tgt or math.hypot(tgt[0] - ex, tgt[1] - ey) > PAD_TOL:
                    off.append(f"{uref}.{pad}")
                    continue
                if net and net not in POWER_NETS:
                    if nm.setdefault(net, tgt[2]) != tgt[2]:
                        clash.add(net)
        if off:
            print(f"SKIP {label(j)}: {len(off)} pads are not where {tg[ref_key]}'s placement puts "
                  f"them relative to {g[ref_key]} (move the group as a whole, or re-run 05): "
                  f"{', '.join(off[:8])}{' ...' if len(off) > 8 else ''}")
            continue

        old, _ = internal(j)
        old = [i for i in old if i not in tmpl_ids and i not in dels]
        dels.update(old)
        added = skipped = 0
        for i in tmpl:
            if i in stubs:
                continue
            t = tracks[i]
            if t["net"] in POWER_NETS:
                newnet = t["net"]
            elif t["net"] in nm and t["net"] not in clash and nm[t["net"]]:
                newnet = nm[t["net"]]
            else:
                skipped += 1
                continue
            blk = COORD_RE.sub(lambda m: f"({m.group(1)} "
                               + " ".join(fmt(v) for v in tp(float(m.group(2)), float(m.group(3))))
                               + f"{m.group(4)})", t["text"])
            blk = re.sub(r'\(net "[^"]*"\)', f'(net "{newnet}")', blk, count=1)
            blk = re.sub(r'\(uuid "[^"]*"\)', f'(uuid "{uuid.uuid4()}")', blk, count=1)
            additions.append(blk)
            added += 1
        print(f"{label(j)} ({g[ref_key]}, rotated {(da + 180) % 360 - 180:+.3f} deg): "
              f"deleted {len(old)} old internal tracks, added {added}"
              + (f" ({skipped} skipped: no net in this group)" if skipped else ""))

    print(f"CS internal routing: deleted {len(dels)}, added {len(additions)} tracks.")

    for i in sorted(dels, key=lambda i: tracks[i]["s"], reverse=True):
        txt = txt[:tracks[i]["s"] - 1] + txt[tracks[i]["e"]:]
    idx = txt.rstrip().rfind(")")
    txt = txt[:idx] + "\n".join(additions) + "\n" + txt[idx:]

    if args.apply:
        shutil.copyfile(args.pcb, args.pcb + ".bak")
        open(args.pcb, "w", encoding="utf-8").write(txt)
        print(f"\nWrote {args.pcb} (backup at {args.pcb}.bak).")
    else:
        print(f"\nDRY RUN -- no file written. Re-run with --apply to save.")


if __name__ == "__main__":
    main()
