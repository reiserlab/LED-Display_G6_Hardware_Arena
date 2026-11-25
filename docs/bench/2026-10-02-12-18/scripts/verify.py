# usage: [ARENA_PORT=/dev/cu.usbmodemXXX] pixi run python verify.py idle,allon,...  [read_s]
# per reset: prep, SYSTEM_RESET, read the 0xD1 page at ~read_s (default 6.5 s) after the reset.
# Run from a firmware worktree root (imports tests.transport). Header = 18 B (scan_id at [17]).
import os, struct, sys, time; sys.path.insert(0, '.')
from tests.transport import SerialTransport
from scripts.arena_port import find_arena_port
PORT = os.environ.get('ARENA_PORT') or find_arena_port() or '/dev/cu.usbmodem121699401'
HDR = 18
def connect(deadline=40):
    end = time.time() + deadline
    while time.time() < end:
        try:
            t = SerialTransport(PORT, settle=0.05); t.open()
            if t.command(0xC2, timeout=0.3)[0] == 0: return t
            t.close()
        except Exception: pass
        time.sleep(0.1)
    raise SystemExit("controller did not come back")
def page(t):
    for _ in range(10):
        st, echo, p, _ = t.command(0xD1); p = bytes(p)
        if echo == 0xD1 and len(p) >= HDR:
            return p[2], p[17], [struct.unpack_from('<BI', p, HDR + 5*k)[0] for k in range(p[4])]
        time.sleep(0.2)
    raise SystemExit("no 0xD1 page")
print(f"port {PORT}")
t = connect(); ok = 0; plan = sys.argv[1].split(',')
for k, mode in enumerate(plan):
    if mode == 'allon': t.command(0xFF); time.sleep(3)
    try: t.command(0x01, timeout=0.3)
    except Exception: pass
    T0 = time.time()
    try: t.close()
    except Exception: pass
    time.sleep(0.5); t = connect(); tb = time.time() - T0
    time.sleep(max(0, float(sys.argv[2]) - (time.time() - T0)) if len(sys.argv) > 2 else max(0, 6.5 - (time.time() - T0)))
    flags, scan_id, s = page(t)
    bad = {i+1: v for i, v in enumerate(s) if v not in (2, 3, 4, 5)}
    ok += (not bad and flags & 1)
    print(f"reset {k+1} ({mode}): back {tb:.1f}s  flags {flags:#04x}  scan_id {scan_id}  panels {len(s)}  not-ok {bad}"); sys.stdout.flush()
    time.sleep(1)
t.close(); print(f"RESULT {ok}/{len(plan)} clean")
