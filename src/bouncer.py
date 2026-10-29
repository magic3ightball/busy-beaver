"""Bouncer decider: real non-halting proofs by symbolic simulation with induction rules.

Run from busy-beaver/:
    python3 src/bouncer.py <tm|-> [maxops] [kmax]     # '-' reads machines from stdin
TSV out: tm, result, k, ops, rules, note
    result = bouncer_proved (never halts, proved) | halt (seen halting) | bouncer_fail

Why not the plain record-formula bouncer decider: the leftovers bounce a *variable*
number of times inside one cycle (the head zig-zags over a run that it eats one copy
at a time), so one cycle is not a fixed list of shift rules. This is the same idea one
level up (Ligocki-style proof system):

* Tape = run-length encoded macro cells (k base cells each), head between cells facing
  a side. halves[d] = stack of [cell, count] runs on side d, top = next to the head.
* Shift rule ("chain"): if state s reading cell x exits the far side in state s, then
  s x^e -> y^e s for every e >= 0, done as one move.
* Induction rules: whenever the run-length *shape* (state, facing, cell symbols) repeats,
  take the two count vectors A -> B, replace the counts that changed (and long unchanged
  ones) by m_i + y_i with fresh variables y_i >= 0, and symbolically run the shape until
  it reaches the same shape with counts m_i + y_i + (B_i - A_i). The symbolic run may
  only use (a) a macro step on a cell (taking one copy needs the count's constant >= 1,
  so it is true for every y), (b) shift rules, (c) earlier proved rules. Every move is
  valid for all values of the variables, so the rule P(e) -> P(e + d) holds whenever
  each generalised count e_i >= m_i.
* A proved rule with some d_i < 0 is applied as many times as the shrinking counts allow
  (count computed symbolically, linear in the variables). A proved rule with every
  d_i >= 0 applies forever: if it matches a configuration the real run reached, the
  machine never halts. That is the proof. An inner zig-zag rule applied a symbolic number
  of times inside the outer bounce is what turns these bouncers into proofs.

Counts are linear forms with non-negative integer coefficients: tuple (c0, c1, ..., cV)
= c0 + c1 y1 + ... ; ">= k for all y >= 0" is c0 >= k. All rewrites are identities, so
a failed match only costs a proof, never soundness. `src/test_bouncer.py` checks that no
halting machine is ever proved.
"""
import sys

MAXRULES = 400
PROOF_OPS = 2000
MAXATTEMPTS = 400
TRIES = [(0, 1), (1, 1), (2, 1), (3, 1), (0, 2), (3, 2), (0, 3), (3, 3), (0, 4), (3, 4)]


def parse(tm):
    segs = tm.split("_")
    n, m = len(segs), len(segs[0]) // 3
    T = []
    for seg in segs:
        row = []
        for r in range(m):
            c = seg[3 * r:3 * r + 3]
            q = ord(c[2]) - 65
            row.append(None if c[0] == "-" or not 0 <= q < n else (int(c[0]), 1 if c[1] == "R" else 0, q))
        T.append(row)
    return T, n, m


# ---------------------------------------------------------------- linear counts
def lin(c, V):
    return (c,) + (0,) * V


def ladd(a, b):
    return tuple(x + y for x, y in zip(a, b))


def lscale(a, k):
    return tuple(x * k for x in a)


def lge(a, k):
    return a[0] >= k and all(x >= 0 for x in a[1:])


def lzero(a):
    return not any(a)


# ---------------------------------------------------------------- macro machine
class Macro:
    """k-cell macro machine of a TM. Macro state = (state, facing)."""

    def __init__(self, T, n, m, k):
        self.T, self.k = T, k
        self.V = 0                 # number of variables in the counts being simulated
        self.zero = (0,) * k
        self.cap = k * n * m ** k + 1
        self.cache = {}

    def step(self, s, f, x):
        """Enter cell x (a k-tuple, left to right) facing f in state s.
        Returns (y, t, d) = written cell, new state, exit side; or 'halt' / 'loop'."""
        key = (s, f, x)
        r = self.cache.get(key)
        if r is None:
            r = self.cache[key] = self._run(s, f, x)
        return r

    def _run(self, s, f, x):
        k, T = self.k, self.T
        c = list(x)
        p = 0 if f else k - 1
        for _ in range(self.cap):
            tr = T[s][c[p]]
            if tr is None:
                return "halt"
            c[p], d, s = tr
            p += 1 if d else -1
            if p == k or p < 0:
                return (tuple(c), s, d)
        return "loop"


def push(half, x, e, zero):
    if half and half[-1][0] == x:
        half[-1][1] = ladd(half[-1][1], e)
    elif half or x != zero:      # zeros next to 0^inf vanish
        half.append([x, e])


def normalize(half, zero):
    """Drop runs with count 0, merge equal neighbours, drop outer zeros."""
    out = []
    for x, e in half:
        if lzero(e):
            continue
        if out and out[-1][0] == x:
            out[-1][1] = ladd(out[-1][1], e)
        else:
            out.append([x, e])
    while out and out[0][0] == zero:
        out.pop(0)
    half[:] = out


def shape(s, f, H):
    return (s, f, tuple(r[0] for r in H[0]), tuple(r[0] for r in H[1]))


def counts(H):
    return [r[1] for r in H[0]] + [r[1] for r in H[1]]


def macro_step(M, s, f, H):
    """One move. Returns (status, s, f, based) with status 'ok' | 'halt' | 'loop' |
    'drift' (shift rule into blank tape: runs off forever); based = took >= 1 base step."""
    front, back = H[f], H[1 - f]
    x = front[-1][0] if front else M.zero
    r = M.step(s, f, x)
    if isinstance(r, str):
        return r, s, f, False
    y, t, d = r
    if d == f and t == s:                      # shift rule over the whole run
        if not front:
            return "drift", s, f, False
        _, e = front.pop()
        push(back, y, e, M.zero)
        return "ok", s, f, False
    if front:
        e = front[-1][1]
        if not lge(e, 1):
            return "stuck", s, f, False
        e = ladd(e, lin(-1, len(e) - 1))
        if lzero(e):
            front.pop()
        else:
            front[-1][1] = e
    one = lin(1, M.V)
    if d == f:
        push(back, y, one, M.zero)
        return "ok", t, f, True
    push(front, y, one, M.zero)
    return "ok", t, d, True


# ---------------------------------------------------------------- rules
class Rule:
    """P(e) -> P(result) for every count vector e with e_i = m_i + p_i y_i (y_i >= 0) on
    generalised runs and e_i == value on the others. spec[i] = (gen, m_or_value, p);
    result[i] is a linear form in the rule's variables y_j (one per generalised run).
    diff[i] = constant change when the rule is a pure shift e -> e + d (d_i a multiple
    of p_i, so the rule can be applied again), else None."""

    def __init__(self, key, spec, result):
        self.key, self.spec, self.result = key, spec, result
        V = sum(1 for g, _, _ in spec if g)
        self.diff, j = [], 0
        for (g, v, p), r in zip(spec, result):
            if g:
                unit = [0] * V
                unit[j] = p
                j += 1
                ok = list(r[1:]) == unit and (r[0] - v) % p == 0
                self.diff.append(r[0] - v if ok else None)
            else:
                self.diff.append(r[0] - v if not any(r[1:]) else None)
        self.shift = (all(d is not None for d in self.diff)
                      and all(d == 0 for (g, _, _), d in zip(spec, self.diff) if not g))
        if self.shift:
            self.infinite = all(d >= 0 for d in self.diff)
        else:
            # Its result matches its own pattern again for every y >= 0?
            self.infinite = all(
                (r[0] >= v and (r[0] - v) % p == 0 and all(c % p == 0 for c in r[1:])) if g
                else r == lin(v, V) for (g, v, p), r in zip(spec, result))

    def target(self, cs):
        """Concrete result counts for concrete start counts (used by the audit)."""
        ys = [(e - v) // p for (g, v, p), e in zip(self.spec, cs) if g]
        return [r[0] + sum(c * y for c, y in zip(r[1:], ys)) for r in self.result]


def apply_rule(rule, H, V):
    """Apply a matching rule (a shift rule as often as allowed). Returns 'inf', True, None."""
    cs = counts(H)
    rs, ys = [], []
    for (g, v, p), d, e in zip(rule.spec, rule.diff, cs):
        if not g:
            if e != lin(v, V):
                return None
            continue
        if not lge(e, v) or (e[0] - v) % p or any(c % p for c in e[1:]):
            return None
        ys.append(((e[0] - v) // p,) + tuple(c // p for c in e[1:]))
        if rule.shift and d < 0:
            a = -d
            if any(c % a for c in e[1:]):
                return None
            rs.append(((e[0] - v) // a + 1,) + tuple(c // a for c in e[1:]))
    if rule.infinite:
        return "inf"
    allc = [run for h in (0, 1) for run in H[h]]
    if not rule.shift:
        for run, r in zip(allc, rule.result):
            e = lin(r[0], V)
            for c, y in zip(r[1:], ys):
                if c:
                    e = ladd(e, lscale(y, c))
            run[1] = e
        return True
    r = None
    for ri in rs:
        if all(all(x <= y for x, y in zip(ri, rj)) for rj in rs):
            r = ri
            break
    if r is None:
        return None
    for run, d in zip(allc, rule.diff):
        if d:
            run[1] = ladd(run[1], lscale(r, d))
    return True


def try_rules(rules, s, f, H, V):
    """Apply the first matching rule. Returns (result of apply_rule or None, rule)."""
    for rule in rules.get(shape(s, f, H), ()):
        res = apply_rule(rule, H, V)
        if res is not None:
            return res, rule
    return None, None


def show_rule(rule):
    """Readable rule, tape left to right, e.g. '0^∞ <A 4^(1+2x) 2 0^∞  →  4^(5+2x)'."""
    names = "xyzuvw"
    s, f, k0, k1 = rule.key

    def tape(exps):
        cells = [(x, e) for x, e in zip(k0, exps[:len(k0)])]
        right = [(x, e) for x, e in zip(k1, exps[len(k0):])][::-1]
        out = ["0^∞"] + [f"{''.join(map(str, x))}{e}" for x, e in cells]
        out.append(f"{chr(65 + s)}>" if f else f"<{chr(65 + s)}")
        return " ".join(out + [f"{''.join(map(str, x))}{e}" for x, e in right] + ["0^∞"])

    def ex(c0, cs):
        terms = [str(c0)] if c0 or not any(cs) else []
        terms += [(f"{c}" if c != 1 else "") + names[j] for j, c in enumerate(cs) if c]
        t = "+".join(terms)
        return "" if t == "1" else ("^" + t if t.isdigit() else f"^({t})")

    start, j = [], 0
    for g, v, p in rule.spec:
        if g:
            cs = [0] * len(rule.result[0][1:])
            cs[j] = p
            j += 1
            start.append(ex(v, cs))
        else:
            start.append(ex(v, []))
    return tape(start) + "  →  " + tape([ex(r[0], r[1:]) for r in rule.result])


def prove_rule(M, rules, key, A, B, mode, p=1):
    """Generalise the counts that changed between two visits A, B of the same shape (and,
    for mode < 3, long unchanged ones) to m_i + p y_i, run symbolically until the visit
    that corresponds to B, and read the result counts off as linear forms."""
    s0, f0, k0, k1 = key
    spec = []
    for a, b in zip(A, B):
        d = b - a
        if d:
            m0 = max(-d, 0) + mode if mode < 3 else min(a, b)
            m0 = min(m0, a)
            spec.append((True, a - (a - m0) // p * p, p))   # m <= a, m = a (mod p)
        elif a >= 2 and mode < 3:
            spec.append((True, min(a, 1 + mode), 1))
        else:
            spec.append((False, a, 1))
    V = sum(1 for g, _, _ in spec if g)
    if V == 0:
        return None
    start, vi = [], 0
    for g, v, q in spec:
        e = lin(v, V)
        if g:
            e = e[:1 + vi] + (q,) + e[2 + vi:]
            vi += 1
        start.append(e)
    H = [[], []]
    i = 0
    for h, syms in ((0, k0), (1, k1)):
        for x in syms:
            H[h].append([x, start[i]])
            i += 1
    yA = [(a - v) // q for a, (g, v, q) in zip(A, spec) if g]
    s, f, based = s0, f0, False
    M.V = V
    for _ in range(PROOF_OPS):
        # Stop at the visit that corresponds to B (the generic run evaluated at A gives B);
        # earlier visits of the same shape are other, less useful rules.
        if based and s == s0 and f == f0 and shape(s, f, H) == key:
            cs = counts(H)
            if [e[0] + sum(c * y for c, y in zip(e[1:], yA)) for e in cs] == list(B):
                return Rule(key, spec, cs)
        res, _ = try_rules(rules, s, f, H, V)
        if res == "inf":
            return None
        if res:
            based = True
            normalize(H[0], M.zero)
            normalize(H[1], M.zero)
            continue
        st, s, f, b = macro_step(M, s, f, H)
        if st != "ok":
            return None
        based = based or b
    return None


# ---------------------------------------------------------------- decider
def decide_k(T, n, m, k, maxops, collect=None):
    M = Macro(T, n, m, k)
    H = [[], []]
    s, f = 0, 1
    rules = {}
    nrules = 0
    hist = {}
    failed = set()
    attempts = 0
    for op in range(maxops):
        res, rule = try_rules(rules, s, f, H, 0)
        if res == "inf":
            return "proved", op, nrules, show_rule(rule)
        if res:
            normalize(H[0], M.zero)
            normalize(H[1], M.zero)
            continue
        # Record the configuration only here, right before a real move, so two equal
        # records always have >= 1 base step between them.
        key = shape(s, f, H)
        cs = [c[0] for c in counts(H)]
        prev = hist.get(key)
        hist[key] = cs
        if prev is not None:
            if prev == cs:
                return "proved", op, nrules, "cycle"
            fk = (key, tuple((b > a) - (b < a) for a, b in zip(prev, cs)))
            if fk not in failed and nrules < MAXRULES and attempts < MAXATTEMPTS:
                attempts += 1
                rule = None
                for mode, p in TRIES:
                    rule = prove_rule(M, rules, key, prev, cs, mode, p)
                    M.V = 0
                    if rule:
                        break
                if rule:
                    rules.setdefault(key, []).append(rule)
                    nrules += 1
                    if collect is not None:
                        collect.append((k, rule))
                    res, rule = try_rules(rules, s, f, H, 0)
                    if res == "inf":
                        return "proved", op, nrules, show_rule(rule)
                    if res:
                        normalize(H[0], M.zero)
                        normalize(H[1], M.zero)
                        continue
                else:
                    failed.add(fk)
        st, s, f, _ = macro_step(M, s, f, H)
        if st == "halt":
            return "halt", op, nrules, ""
        if st in ("loop", "drift"):
            return "proved", op, nrules, st
        if st != "ok":
            return "fail", op, nrules, st
    return "fail", maxops, nrules, ""


def decide(tm, maxops=20000, kmax=4, collect=None):
    T, n, m = parse(tm)
    last = None
    for k in range(1, kmax + 1):
        if m ** k > 4096:
            break
        r = decide_k(T, n, m, k, maxops, collect)
        if r[0] in ("proved", "halt"):
            return r[0], k, r[1], r[2], r[3]
        last = r
    return "fail", kmax, last[1] if last else 0, last[2] if last else 0, last[3] if last else ""


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "-"
    maxops = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
    kmax = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    tms = [l.strip() for l in sys.stdin if l.strip()] if arg == "-" else [arg]
    for tm in tms:
        res, k, ops, nr, note = decide(tm, maxops, kmax)
        name = {"proved": "bouncer_proved", "halt": "halt", "fail": "bouncer_fail"}[res]
        print(f"{tm}\t{name}\t{k}\t{ops}\t{nr}\t{note}")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
