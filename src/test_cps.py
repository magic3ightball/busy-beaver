"""Soundness check for `bb cps`: random machines that halt must never be 'cps_proved'.

Run from busy-beaver/: python3 src/test_cps.py [count] [seed]
Generates fully specified random machines (2-4 states x 2 symbols, 2-3 x 3), runs
`bb check` (simulation + cycler deciders, 1M steps) and `bb cps`, and reports any
machine that halts in simulation but was proved non-halting by CPS (= a bug).
"""
import random
import subprocess
import sys

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
rng = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
SHAPES = [(2, 2), (3, 2), (4, 2), (2, 3), (3, 3), (2, 4)]


def rand_tm(n, m):
    out = []
    for s in range(n):
        seg = ""
        for r in range(m):
            nx = rng.randrange(n + 1)  # n = halt
            seg += f"{rng.randrange(m)}{rng.choice('LR')}{'Z' if nx == n else chr(65 + nx)}"
        out.append(seg)
    return "_".join(out)


tms = [rand_tm(*rng.choice(SHAPES)) for _ in range(N)]
inp = "\n".join(tms) + "\n"
chk = subprocess.run(["./bb", "check", "-", "1000000"], input=inp, capture_output=True, text=True).stdout.split("\n")
cps = subprocess.run(["./bb", "cps", "-", "6", "200000", "3"], input=inp, capture_output=True, text=True).stdout.split("\n")
res = {l.split("\t")[0]: l.split("\t")[1] for l in chk if l}
prf = {l.split("\t")[0]: l.split("\t")[1] for l in cps if l}
halts = [t for t in tms if res.get(t) == "halt"]
bad = [t for t in halts if prf.get(t) == "cps_proved"]
proved = sum(1 for t in tms if prf.get(t) == "cps_proved")
nonhalt = sum(1 for t in tms if res.get(t) in ("cycler", "translated_cycler"))
both = sum(1 for t in tms if res.get(t) in ("cycler", "translated_cycler") and prf.get(t) == "cps_proved")
print(f"machines {N}: halting {len(halts)}, cps proved {proved}, cycler-proved {nonhalt} (of which cps also proved {both})")
print("UNSOUND:", bad[:10] if bad else "none")
sys.exit(1 if bad else 0)
