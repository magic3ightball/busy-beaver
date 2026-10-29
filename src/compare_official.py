"""Compare our machines with a reference list by *behaviour*, not by text.

Two machines count as the same when their first STEPS steps match after renaming
states (by first visit), symbols (by first write; 0 stays 0) and, if needed,
mirroring left/right. Undefined transitions that are never reached don't matter.

Run from busy-beaver/: python3 src/compare_official.py ours.txt reference.tsv [steps]
reference.tsv lines: <category>\t<machine>
"""
import sys

STEPS = int(sys.argv[3]) if len(sys.argv) > 3 else 200000


def parse(t):
    parts = t.split("_")
    m = len(parts[0]) // 3
    tab = {}
    for s, p in enumerate(parts):
        for r in range(m):
            c = p[3 * r:3 * r + 3]
            if c == "---":
                continue
            nx = ord(c[2]) - 65
            tab[(s, r)] = (int(c[0]), 1 if c[1] == "R" else -1, nx if nx < len(parts) else -1)
    return tab


def fingerprint(t):
    tab = parse(t)
    tape, h, s = {}, 0, 0
    sid, yid, flip, out = {0: 0}, {0: 0}, None, []
    for _ in range(STEPS):
        r = tape.get(h, 0)
        tr = tab.get((s, r))
        if tr is None:
            out.append("U"); break
        w, d, nx = tr
        if flip is None:
            flip = d  # normalise so the first move is "+"
        if w not in yid:
            yid[w] = len(yid)
        sid.setdefault(s, len(sid))
        out.append(f"{sid[s]}.{yid[r]}.{yid[w]}.{'+' if d == flip else '-'}")
        tape[h] = w; h += d
        if nx < 0:
            out.append("H"); break
        s = nx
    return hash(" ".join(out))


ours = [l.split("\t")[0].strip() for l in open(sys.argv[1]) if l.strip()]
ref = [l.rstrip("\n").split("\t") for l in open(sys.argv[2]) if l.strip()]
refp = {}
for cat, tm in ref:
    refp.setdefault(fingerprint(tm), []).append((cat, tm))
groups = {}
for tm in ours:
    groups.setdefault(fingerprint(tm), []).append(tm)
print(f"{len(ours)} machines -> {len(groups)} distinct behaviours (first {STEPS:,} steps)")
for fp, tms in groups.items():
    hit = refp.get(fp)
    tag = "; ".join(f"{c}: {t}" for c, t in hit) if hit else "not in list"
    print(f"{len(tms)}x  {tms[0]}  ->  {tag}")
