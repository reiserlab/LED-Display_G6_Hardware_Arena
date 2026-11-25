# usage: [ARENA_PORT=COMx] pixi run python ao_ai_steps.py [mv,mv,...] [hold_s=10]
# C1 accuracy check via the controller's own AO (J27, MCP4725, 0-5000 mV) looped back into
# Analog In 1: steps SET_AO_VOLTAGE (0xA0) through the list, holds each step so the operator can
# read a DMM on the same node (the truth), and logs AI1 (0xA4, calibrated mV) averaged over the
# second half of each hold. Leaves the AO at 5000 mV (the rig idle default).
# Run from the analog worktree root (imports tests.transport).
import os, statistics as st, struct, sys, time; sys.path.insert(0, '.')
from tests.transport import SerialTransport
from scripts.arena_port import find_arena_port
PORT = os.environ.get('ARENA_PORT') or find_arena_port()
if not PORT: raise SystemExit("no arena port found; set ARENA_PORT")
STEPS = [int(x) for x in (sys.argv[1] if len(sys.argv) > 1 else '1000,2500,5000').split(',')]
HOLD = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
t = SerialTransport(PORT, settle=0.3); t.open()
t.command(0x00, timeout=1.0)
results = []
try:
    for mv in STEPS:
        mv = max(0, min(5000, mv))
        s, e, p, _ = t.command(0xA0, bytes([mv & 0xFF, mv >> 8]), timeout=1.0)
        print(f">>> AO = {mv} mV <<<  (set status {s}) — read the DMM now", flush=True)
        t0 = time.time(); xs = []; fl = None
        while time.time() - t0 < HOLD:
            if time.time() - t0 > HOLD / 2:
                s, e, p, _ = t.command(0xA4, timeout=1.0); p = bytes(p)
                if s == 0 and len(p) >= 5: xs.append(struct.unpack_from('<h', p, 0)[0]); fl = p[4]
            time.sleep(0.02)
        m = st.mean(xs); sd = st.pstdev(xs)
        results.append((mv, m, sd))
        print(f"    AI1 {m:8.1f} mV  std {sd:5.1f}  (n={len(xs)}, flags {fl:#04x})", flush=True)
finally:
    t.command(0xA0, bytes([5000 & 0xFF, 5000 >> 8]), timeout=1.0)
    t.close()
print("summary (AO setpoint -> AI1 mean):")
for mv, m, sd in results:
    print(f"  {mv:5d} mV -> {m:8.1f} mV  (AI1 - setpoint {m - mv:+6.1f} mV)")
print("AO left at 5000 mV")
