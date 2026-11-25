# usage: [ARENA_PORT=/dev/cu.usbmodemXXX] pixi run python qwiic_stuck_bus.py [seconds=60]
# Loops GET_I2C_SCAN (0xB0) on the Qwiic bus and prints status/time per scan, with the
# controller's uptime before and after — short SDA (blue) to GND (black) on the Qwiic cable
# for ~2 s while it runs. Pass = status 4 within ~0.5 s while shorted, status 0 again after,
# uptime never decreases (no watchdog reset), USB never drops.
# Run from the #58 worktree root (imports tests.transport).
import os, struct, sys, time; sys.path.insert(0, '.')
from tests.transport import SerialTransport
from scripts.arena_port import find_arena_port
PORT = os.environ.get('ARENA_PORT') or find_arena_port()
if not PORT: raise SystemExit("no arena port found; set ARENA_PORT")
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
t = SerialTransport(PORT, settle=0.3); t.open()
def uptime():
    st, echo, p, _ = t.command(0xCA, timeout=1.0)
    return struct.unpack_from('<I', bytes(p), 2)[0] if st == 0 else None
print(f"port {PORT}; scanning for {DUR:.0f} s — short SDA to GND now and then")
last_up = uptime(); worst = 0; stuck = 0; resets = 0; T0 = time.time()
while time.time() - T0 < DUR:
    t0 = time.time()
    try:
        st, echo, p, _ = t.command(0xB0, timeout=3.0)
    except Exception as e:
        print(f"  !! transport error: {e} (USB dropped? controller reset?)"); resets += 1
        time.sleep(1); continue
    ms = (time.time() - t0) * 1000; worst = max(worst, ms)
    up = uptime()
    note = ""
    if up is not None and last_up is not None and up < last_up: note = "  !! UPTIME WENT BACKWARDS — CONTROLLER RESET"; resets += 1
    if st == 4: stuck += 1
    devs = list(bytes(p)[1:1 + bytes(p)[0]]) if st == 0 and p else []
    print(f"  {time.time()-T0:6.1f}s  status {st}  {ms:6.0f} ms  devices {[hex(d) for d in devs]}  uptime {up}{note}")
    last_up = up or last_up
    time.sleep(0.3)
t.close()
print(f"DONE: {stuck} stuck-bus scans (status 4), worst scan {worst:.0f} ms, resets/drops {resets}")
print("PASS" if stuck > 0 and resets == 0 and worst < 1500 else "CHECK — see notes above")
