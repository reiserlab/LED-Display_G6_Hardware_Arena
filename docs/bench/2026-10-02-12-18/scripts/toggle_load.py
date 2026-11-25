# usage: [ARENA_PORT=COMx] pixi run python toggle_load.py [period_s=5] [total_s=60]
# Bench helper for the E1/E2 ground + rail map: alternates ALL_OFF / ALL_ON every
# period_s so the operator can read a DMM hands-free, and logs Analog In 1/2 (0xA4,
# two int16 LE mV + flags) averaged over the second half of each state.
# Run from a firmware worktree root (imports tests.transport).
import os, struct, sys, time; sys.path.insert(0, '.')
from tests.transport import SerialTransport
from scripts.arena_port import find_arena_port
PORT = os.environ.get('ARENA_PORT') or find_arena_port()
if not PORT: raise SystemExit("no arena port found; set ARENA_PORT")
PERIOD = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
TOTAL = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
t = SerialTransport(PORT, settle=0.3); t.open()

def ai():
    st, echo, p, _ = t.command(0xA4, timeout=1.0)
    p = bytes(p)
    if st != 0 or len(p) < 4: return None
    return struct.unpack_from('<hh', p, 0)

rows = {'OFF': [], 'ON': []}
print(f"port {PORT}; {PERIOD:.0f} s per state for {TOTAL:.0f} s. Read the DMM in each state.")
T0 = time.time(); on = True  # flipped before use: the first state is OFF
try:
    while time.time() - T0 < TOTAL:
        on = not on
        state = 'ON' if on else 'OFF'
        t.command(0xFF if on else 0x00, timeout=1.0)
        print(f"{time.time()-T0:5.1f}s  >>> ALL {state:3s} <<<", flush=True)
        t_state = time.time(); samples = []
        while time.time() - t_state < PERIOD:
            if time.time() - t_state > PERIOD / 2:
                v = ai()
                if v: samples.append(v)
            time.sleep(0.1)
        if samples:
            a1 = sum(s[0] for s in samples) / len(samples)
            a2 = sum(s[1] for s in samples) / len(samples)
            rows[state].append((a1, a2))
            print(f"        AI1 {a1:8.1f} mV   AI2 {a2:8.1f} mV   ({len(samples)} samples)", flush=True)
finally:
    t.command(0x00, timeout=1.0)
    t.close()
for k in ('OFF', 'ON'):
    if rows[k]:
        print(f"mean {k:3s}: AI1 {sum(r[0] for r in rows[k])/len(rows[k]):8.1f} mV   "
              f"AI2 {sum(r[1] for r in rows[k])/len(rows[k]):8.1f} mV")
if rows['OFF'] and rows['ON']:
    d1 = sum(r[0] for r in rows['ON'])/len(rows['ON']) - sum(r[0] for r in rows['OFF'])/len(rows['OFF'])
    d2 = sum(r[1] for r in rows['ON'])/len(rows['ON']) - sum(r[1] for r in rows['OFF'])/len(rows['OFF'])
    print(f"ON - OFF: AI1 {d1:+.1f} mV   AI2 {d2:+.1f} mV")
print("arena left ALL OFF")
