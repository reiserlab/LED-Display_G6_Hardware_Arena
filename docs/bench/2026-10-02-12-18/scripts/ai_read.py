# usage: [ARENA_PORT=COMx] pixi run python ai_read.py [label] [samples=200]
# Bench helper for the analog-input T/C tests: averages GET_ANALOG_IN (0xA4, two int16 LE mV +
# flags) and GET_ANALOG_IN_RAW (0xA5, raw ADC per channel) at a fixed display state, and prints
# mean / std / min / max per channel. Run from the analog worktree root (imports tests.transport).
import os, statistics as st, struct, sys, time; sys.path.insert(0, '.')
from tests.transport import SerialTransport
from scripts.arena_port import find_arena_port
PORT = os.environ.get('ARENA_PORT') or find_arena_port()
if not PORT: raise SystemExit("no arena port found; set ARENA_PORT")
LABEL = sys.argv[1] if len(sys.argv) > 1 else ''
N = int(sys.argv[2]) if len(sys.argv) > 2 else 200
t = SerialTransport(PORT, settle=0.3); t.open()
mv = ([], []); raw = ([], []); flags = None; raw_hex = None
for _ in range(N):
    s, e, p, _ = t.command(0xA4, timeout=1.0); p = bytes(p)
    if s == 0 and len(p) >= 4:
        a, b = struct.unpack_from('<hh', p, 0); mv[0].append(a); mv[1].append(b)
        if len(p) >= 5: flags = p[4]
    s, e, p, _ = t.command(0xA5, timeout=1.0); p = bytes(p)
    if s == 0 and len(p) >= 4:
        a, b = struct.unpack_from('<HH', p, 0); raw[0].append(a); raw[1].append(b); raw_hex = p.hex(' ')
    time.sleep(0.01)
t.close()
def line(name, xs, unit):
    if not xs: return f"  {name}: no data"
    sd = st.pstdev(xs) if len(xs) > 1 else 0.0
    return f"  {name}: mean {st.mean(xs):9.2f} {unit}  std {sd:6.2f}  min {min(xs)}  max {max(xs)}  (n={len(xs)})"
print(f"[{LABEL}] port {PORT}  flags {flags if flags is None else hex(flags)}")
print(line('AI1 mV ', mv[0], 'mV')); print(line('AI2 mV ', mv[1], 'mV'))
print(line('AI1 raw', raw[0], 'cnt')); print(line('AI2 raw', raw[1], 'cnt'))
print(f"  last 0xA5 payload: {raw_hex}")
