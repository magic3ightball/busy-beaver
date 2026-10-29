"""Soundness check for src/bouncer.py.

Run from busy-beaver/: python3 src/test_bouncer.py [count] [seed]
1. Random fully specified machines (2-4 states x 2 symbols, 2-3 x 3, 2 x 4): any machine
   that halts in `bb check` (1M steps) but is 'bouncer_proved' = a bug.
2. Known halters (BB(2..5) champions, BB(2,4)) must not be proved; the cryptids
   (Antihydra, Hydra, Bigfoot) must not be proved either.
   Long halters (most likely to fool a prover): uniform random machines almost never
   run long before halting (the whole BB(6) search's longest halter took 174 steps), so
   the known champions are used instead, including the BB(6) champion, which runs far
   beyond anything simulated here before it halts. Each is decided at op limits from
   60 to 20000, so proofs are attempted at many moments before the halt.
3. Rule audit: every induction rule the prover accepts (on all machines above plus the
   15 leftovers) is replayed on the real machine with concrete counts (several random
   values >= the rule's minimums): P(e) must reach P(e + d) by plain simulation.
"""
import os
import random
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
import bouncer as B  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 1
SHAPES = [(2, 2), (3, 2), (4, 2), (2, 3), (3, 3), (2, 4)]
HALTERS = ["1RB1LB_1LA1RZ", "1RB1RZ_1LB0RC_1LC1LA", "1RB1LB_1LA0LC_1RZ1LD_1RD0RA",
           "1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA", "1RB2LA1RA1RA_1LB1LA3RB1RZ",
           "1RB2LB1RZ_2LA2RB1LB",                              # BB(2,3), 38 steps
           "1RB1RA_1RC1RZ_1LD0RF_1RA0LE_0LD1RC_1RA0RE"]        # BB(6) champion (mxdys 2025)
CRYPTIDS = ["1RB1RA_0LC1LE_1LD1LC_1LA0LB_1LF1RE_---0RA", "1RB3RB---3LA1RA_2LA3RA4LB0LB0LA",
            "1RB2RA1LC_2LC1RB2RB_---2LA1LA"]
STEP_CAP = 300000   # base replay budget; grows with the instance width W as + 2 W^2
MAX_CELLS = 6000    # rules whose instance would be wider are counted as skipped


def rand_tm(rng, n, m):
    out = []
    for s in range(n):
        seg = ""
        for r in range(m):
            nx = rng.randrange(n + 1)
            seg += f"{rng.randrange(m)}{rng.choice('LR')}{'Z' if nx == n else chr(65 + nx)}"
        out.append(seg)
    return "_".join(out)


def std_config(key, cs, k):
    """Expand a macro shape + concrete counts to (state, cells, head index)."""
    s, f, k0, k1 = key
    left, right = [], []
    i = 0
    for x in k0:
        left.extend(x * cs[i])
        i += 1
    runs = []
    for x in k1:
        runs.append(x * cs[i])
        i += 1
    for r in reversed(runs):
        right.extend(r)
    cells = left + right
    if f == 1:
        head = len(left)
        if head == len(cells):
            cells.append(0)
    else:
        if not left:
            cells.insert(0, 0)
            head = 0
        else:
            head = len(left) - 1
    return s, cells, head


def audit_rule(T, rule, k, rng):
    """Replay one rule with concrete counts. Returns None if fine, else a message."""
    key = rule.key
    for trial in range(4):
        cs = [v + p * rng.choice([0, 1, 2, 3, 7]) if g else v for g, v, p in rule.spec]
        ct = rule.target(cs)
        W = sum(len(x) * e for x, e in zip(key[2] + key[3], cs)) + sum(len(x) * e for x, e in zip(key[2] + key[3], ct))
        if W > MAX_CELLS:
            return "skip"
        cap = STEP_CAP + 2 * W * W
        s, cells, head = std_config(key, cs, k)
        ts, tcells, thead = std_config(key, ct, k)
        tz = [i for i, c in enumerate(tcells) if c]
        a0 = min(tz + [thead])
        tb = bytes(tcells[a0:max(tz + [thead]) + 1])
        off = thead - a0
        pad = cap + len(tb) + 8
        tape = bytearray(pad) + bytearray(cells) + bytearray(pad)
        h = pad + head
        lo, hi = pad, pad + len(cells) - 1
        ok = False
        for step in range(1, cap + 1):
            tr = T[s][tape[h]]
            if tr is None:
                return f"halted after {step} steps with counts {cs}"
            tape[h], d, s = tr
            if d:
                h += 1
                hi = max(hi, h)
            else:
                h -= 1
                lo = min(lo, h)
            if s == ts and tape[h] == tb[off]:
                a = h - off
                b = a + len(tb)
                if (tape[a:b] == tb and tape[lo:a].count(0) == max(0, a - lo)
                        and tape[b:hi + 1].count(0) == max(0, hi + 1 - b)):
                    ok = True
                    break
        if not ok:
            return f"target not reached in {cap} steps, counts {cs}"
    return None


def work_long(tm):
    return tm, [B.decide(tm, ops, 3)[0] for ops in (60, 250, 1000, 4000, 20000)]


def work(tm):
    rules = []
    res = B.decide(tm, 3000, 3, rules)
    T, n, m = B.parse(tm)
    rng = random.Random(hash(tm) & 0xffffffff)
    bad = []
    for k, rule in rules:
        msg = audit_rule(T, rule, k, rng)
        if msg == "skip":
            bad.append("skip")
        elif msg:
            bad.append((k, rule.key, rule.spec, rule.result, msg))
    return tm, res[0], len(rules), bad


def main():
    rng = random.Random(SEED)
    tms = [rand_tm(rng, *rng.choice(SHAPES)) for _ in range(N)]
    inp = "\n".join(tms) + "\n"
    chk = subprocess.run(["./bb", "check", "-", "1000000"], input=inp, capture_output=True, text=True).stdout
    res = {l.split("\t")[0]: l.split("\t")[1] for l in chk.split("\n") if l}
    left = [l.strip() for l in open("out/left_after_cps.txt") if l.strip()]
    allm = tms + HALTERS + CRYPTIDS + left
    with ProcessPoolExecutor() as pool:   # a dead worker raises instead of hanging
        out = list(pool.map(work, allm, chunksize=8))
        outl = list(pool.map(work_long, HALTERS, chunksize=1))
    long_bad = [tm for tm, rs in outl if "proved" in rs]
    got = {tm: r for tm, r, _, _ in out}
    halts = [t for t in tms if res.get(t) == "halt"] + HALTERS
    unsound = [t for t in halts if got[t] == "proved"]
    cryp = [t for t in CRYPTIDS if got[t] == "proved"]
    nrules = sum(nr for _, _, nr, _ in out)
    badr = [(tm, b) for tm, _, _, bs in out for b in bs if b != "skip"]
    skipped = sum(1 for _, _, _, bs in out for b in bs if b == "skip")
    proved = sum(1 for t in tms if got[t] == "proved")
    print(f"random machines {N}: halting {len(halts) - len(HALTERS)}, proved non-halting {proved}, "
          f"seen halting {sum(1 for t in tms if got[t] == 'halt')}")
    print(f"halters proved: {len(unsound)}  cryptids proved: {len(cryp)}  "
          f"leftovers proved: {sum(1 for t in left if got[t] == 'proved')}/{len(left)}")
    print(f"champion halters checked at 5 op limits: {len(HALTERS)}, proved: {len(long_bad)}")
    print(f"rules audited: {nrules - skipped}, failed audit: {len(badr)}, skipped (instance > {MAX_CELLS} cells): {skipped}")
    for tm, b in badr[:10]:
        print("  BAD RULE", tm, b)
    bad = unsound + cryp + long_bad
    print("UNSOUND:", bad[:10] if bad else "none")
    sys.exit(1 if bad or badr else 0)


if __name__ == "__main__":
    main()
