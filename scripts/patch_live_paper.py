import re
from pathlib import Path

p = Path("scripts/live_paper_loop.py")
t = p.read_text(encoding="utf-8")

# Ensure time is imported
if re.search(r"^\s*import\s+time\s*$", t, flags=re.M) is None:
    # Insert import time after argparse/json imports block (best-effort)
    t = re.sub(r"(import\s+argparse\s*\n)", r"\1import time\n", t, count=1)

# Add argparse flag if missing
if "--run-seconds" not in t:
    # Insert after --poll arg (best-effort)
    t, n = re.subn(
        r'(add_argument\(\s*["\']--poll["\'].*\)\s*\n)',
        r'\1    ap.add_argument("--run-seconds", type=int, default=0, help="Run for N seconds then exit (0=forever).")\n',
        t,
        count=1
    )
    if n == 0:
        # Fallback: insert before parse_args
        t = re.sub(
            r'(args\s*=\s*ap\.parse_args\(\)\s*\n)',
            r'ap.add_argument("--run-seconds", type=int, default=0, help="Run for N seconds then exit (0=forever).")\n\1',
            t,
            count=1
        )

# Add runtime cutoff logic (best-effort)
if "run_seconds_deadline" not in t:
    # After args = ap.parse_args()
    t = re.sub(
        r'(args\s*=\s*ap\.parse_args\(\)\s*\n)',
        r'\1    run_seconds_deadline = time.time() + args.run_seconds if getattr(args, "run_seconds", 0) > 0 else None\n',
        t,
        count=1
    )
    # At top of main loop, break if deadline reached
    t = re.sub(
        r'(\n\s*while\s+True\s*:\s*\n)',
        r'\1        if run_seconds_deadline is not None and time.time() >= run_seconds_deadline:\n            print("run-seconds reached; exiting.")\n            break\n',
        t,
        count=1
    )

p.write_text(t, encoding="utf-8")
print(f"Patched {p} (added --run-seconds + cutoff)")
