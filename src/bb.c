// bb.c — small Busy Beaver toolkit.
//
// Turing machines use the bbchallenge "standard text format", e.g. the BB(5)
// champion 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA. States A.., symbols 0..,
// "---" = undefined, any next-state letter past the last state = halt.
// The machine starts in state A on an all-0 tape; the halting transition
// counts as a step (bbchallenge convention).
//
// Subcommands:
//   run     <tm> [limit]                      simulate, print steps / ones
//   check   <tm> [limit]                      run deciders on one machine
//   search  <n> <m> <samples> <seed> <limit>  random TNF walk + deciders
//   diagram <tm> <steps> <rows> <out.bin>     dump space-time rows for rendering
//   cps     <tm|-> [nmax] [maxconf] [kmax]    n-gram Closed Position Set decider (on k-cell blocks)
//
// Deciders (non-halting proofs): cycler (exact configuration repeat, Brent)
// and translated cycler (record-breaking method from the bbchallenge wiki).
// Heuristics (NOT proofs, used only to label holdouts): bouncer, counter.
// n-gram CPS (Nathan Fenner's "simple n-gram CPS", used in the BB(5) proof) is a
// real proof: it builds an over-approximation of every reachable configuration.

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define MAXS 10
#define MAXM 10
#define HALT 99
#define UNDEF -1
#define SNAP 256      // tape cells kept per record for translated cycler
#define RECRING 4096  // records kept per side

typedef struct { int8_t w, d, nx; } Tr;  // d: +1 = R, -1 = L
typedef struct { int n, m; Tr t[MAXS][MAXM]; } TM;

static int parse_tm(const char *s, TM *tm) {
    memset(tm, 0, sizeof *tm);
    const char *u = strchr(s, '_');
    size_t seg = u ? (size_t)(u - s) : strlen(s);
    if (seg % 3 || seg == 0) return -1;
    tm->m = (int)(seg / 3);
    tm->n = 1;
    for (const char *p = s; *p; p++) if (*p == '_') tm->n++;
    if (tm->n > MAXS || tm->m > MAXM) return -1;
    if (strlen(s) != (size_t)tm->n * (seg + 1) - 1) return -1;
    for (int st = 0; st < tm->n; st++)
        for (int r = 0; r < tm->m; r++) {
            const char *c = s + st * (seg + 1) + r * 3;
            Tr *t = &tm->t[st][r];
            if (c[0] == '-') { t->nx = UNDEF; continue; }
            t->w = c[0] - '0';
            t->d = c[1] == 'R' ? 1 : -1;
            int k = c[2] - 'A';
            t->nx = k < tm->n ? k : HALT;
        }
    return 0;
}

static void format_tm(const TM *tm, char *out) {
    char *o = out;
    for (int st = 0; st < tm->n; st++) {
        if (st) *o++ = '_';
        for (int r = 0; r < tm->m; r++) {
            const Tr *t = &tm->t[st][r];
            if (t->nx == UNDEF) { memcpy(o, "---", 3); o += 3; continue; }
            *o++ = '0' + t->w;
            *o++ = t->d > 0 ? 'R' : 'L';
            *o++ = t->nx == HALT ? 'Z' : 'A' + t->nx;
        }
    }
    *o = 0;
}

// ---------------------------------------------------------------- plain run

static int cmd_run(const char *s, uint64_t limit) {
    TM tm;
    if (parse_tm(s, &tm)) { fprintf(stderr, "bad tm\n"); return 2; }
    long size = 1L << 26, head = size / 2, lo = head, hi = head;
    uint8_t *tape = calloc(size, 1);
    int st = 0;
    uint64_t steps = 0;
    const char *why = "limit";
    while (steps < limit) {
        Tr t = tm.t[st][tape[head]];
        if (t.nx == UNDEF) { why = "undefined"; break; }
        tape[head] = t.w;
        head += t.d;
        steps++;
        if (head < lo) lo = head;
        if (head > hi) hi = head;
        if (t.nx == HALT) { why = "halt"; break; }
        st = t.nx;
        if (head <= 0 || head >= size - 1) { why = "tape"; break; }
    }
    long ones = 0;
    for (long i = lo; i <= hi; i++) ones += tape[i] != 0;
    printf("%s steps=%llu nonzero=%ld width=%ld\n", why,
           (unsigned long long)steps, ones, hi - lo + 1);
    free(tape);
    return 0;
}

// ------------------------------------------------------------ analysis core

typedef struct { uint64_t step; long u; long gapmin; int state; uint8_t snap[SNAP]; } Rec;

enum { R_HALT, R_CYCLER, R_TCYCLER, R_HOLDOUT, R_TAPE, R_UNDEF };
static const char *RNAME[] = {"halt", "cycler", "translated_cycler", "holdout", "tape_limit", "undefined"};

typedef struct {
    int result;
    uint64_t steps;
    long width, ones;
    uint64_t period;  // cycle period for (translated) cyclers
    char label[32];   // heuristic label for holdouts
    double slope;     // d log(width) / d log(steps) over second half
    double novelty;   // distinct second differences of record times / window
} Result;

typedef struct {
    long size;
    uint8_t *tape, *saved;
    Rec *rec[2];       // [0] = right side, [1] = left side
    uint64_t *rtimes;  // all record times (both sides), for heuristics
    long nrt, maxrt;
} Work;

static Work *work_new(uint64_t limit) {
    Work *w = calloc(1, sizeof *w);
    w->size = (long)(2 * limit + 2 * SNAP + 16);
    if (w->size > (1L << 27)) w->size = 1L << 27;
    w->tape = calloc(w->size, 1);
    w->saved = calloc(w->size, 1);
    w->rec[0] = calloc(RECRING, sizeof(Rec));
    w->rec[1] = calloc(RECRING, sizeof(Rec));
    w->maxrt = 1 << 20;
    w->rtimes = calloc(w->maxrt, sizeof(uint64_t));
    return w;
}

static uint64_t rng_state;
static uint64_t rnd(void) {  // xorshift64*
    rng_state ^= rng_state >> 12; rng_state ^= rng_state << 25; rng_state ^= rng_state >> 27;
    return rng_state * 2685821657736338717ULL;
}

// Fill an undefined transition the way a TNF tree walk would: new symbols and
// new states may only be introduced in order. The last free slot becomes halt.
static void tnf_fill(TM *tm, int st, int r) {
    int defined = 0, maxs = 0, maxm = 1;
    for (int a = 0; a < tm->n; a++)
        for (int b = 0; b < tm->m; b++) {
            Tr *t = &tm->t[a][b];
            if (t->nx == UNDEF) continue;
            defined++;
            if (t->nx != HALT && t->nx > maxs) maxs = t->nx;
            if (t->w > maxm) maxm = t->w;
        }
    Tr *t = &tm->t[st][r];
    if (defined == tm->n * tm->m - 1) { t->w = 1; t->d = 1; t->nx = HALT; return; }
    int ns = maxs + 2 < tm->n ? maxs + 2 : tm->n;  // states A..(maxs+1)
    int nm = maxm + 2 < tm->m ? maxm + 2 : tm->m;  // symbols 0..(maxm+1)
    uint64_t k = rnd() % (uint64_t)(ns * nm * 2);
    t->nx = (int8_t)(k % ns); k /= ns;
    t->w = (int8_t)(k % nm); k /= nm;
    t->d = k ? 1 : -1;
}

// Is the d1 sequence of record times growing by a constant per period
// (bouncer), or growing geometrically (counter)? Heuristic labels only.
static int cmp_long(const void *a, const void *b) {
    long x = *(const long *)a, y = *(const long *)b;
    return (x > y) - (x < y);
}

static void label_holdout(Work *w, Result *res) {
    long n = w->nrt;
    {   // novelty: collapse bursts of records (gap < 8 steps) into events, then
        // count distinct second differences of event times in the tail window.
        static long ev[1 << 20], d2[400];
        long ne = 0;
        for (long i = 0; i < n; i++)
            if (i == 0 || w->rtimes[i] - w->rtimes[i - 1] >= 8) ev[ne++] = (long)w->rtimes[i];
        if (ne >= 40) {
            long N = ne / 2 < 400 ? ne / 2 : 400, k = 0;
            for (long i = ne - N; i < ne; i++)
                d2[k++] = (ev[i] - ev[i - 1]) - (ev[i - 1] - ev[i - 2]);
            qsort(d2, k, sizeof(long), cmp_long);
            long distinct = 1;
            for (long i = 1; i < k; i++) distinct += d2[i] != d2[i - 1];
            res->novelty = (double)distinct / k;
        }
    }
    strcpy(res->label, "irregular");
    if (n < 40) { strcpy(res->label, res->slope < 0.25 ? "counter_like" : "few_records"); return; }
    uint64_t *t = w->rtimes;
    long N = n / 2 < 400 ? n / 2 : 400, b = n - N;  // tail only: skip start-up transient
    // bouncer: the gaps between records grow linearly, possibly with a
    // different rate in each phase. Test e[i] = d1[i] - d1[i-P] for being
    // P-periodic with positive sum over one period.
    for (int P = 1; P <= 40 && 4 * P < N - 2; P++) {
        int ok = 1; long sum = 0;
        for (long i = b + 2 * P + 1; i < n && ok; i++) {
            long e0 = (long)(t[i] - t[i - 1]) - (long)(t[i - P] - t[i - P - 1]);
            long e1 = (long)(t[i - P] - t[i - P - 1]) - (long)(t[i - 2 * P] - t[i - 2 * P - 1]);
            if (e0 != e1) ok = 0;
            if (i >= n - P) sum += e0;
        }
        if (ok && sum > 0) { snprintf(res->label, sizeof res->label, "bouncer_p%d", P); return; }
    }
    // counter: record times roughly double (geometric growth) over the tail
    long K = 12; if (n < K + 2) return;
    double r0 = 0, r1 = 1e9;
    for (long i = n - K; i < n; i++) {
        double r = (double)t[i] / (double)(t[i - 1] ? t[i - 1] : 1);
        if (r > r0) r0 = r;
        if (r < r1) r1 = r;
    }
    if (res->slope < 0.25 && r1 > 1.05) strcpy(res->label, "counter_like");
}

// Run a machine (filling undefined transitions randomly if fill != 0).
static void analyze(TM *tm, uint64_t limit, int fill, Work *w, Result *res) {
    memset(res, 0, sizeof *res);
    long size = w->size, head = size / 2, lo = head, hi = head;
    uint8_t *tape = w->tape;  // all-zero on entry; cleared again at the end
    int st = 0;
    uint64_t steps = 0;
    // Brent cycler state
    uint64_t sv_step = 0, power = 1; long sv_head = head, sv_lo = lo, sv_hi = hi; int sv_st = 0;
    w->saved[head] = 0;
    // translated cycler state
    long nrec[2] = {0, 0}, gapmin[2] = {0, 0};
    w->nrt = 0;
    // width checkpoint for slope
    uint64_t half_step = 0; long half_width = 1;
    res->result = R_HOLDOUT;

    while (steps < limit) {
        Tr t = tm->t[st][tape[head]];
        if (t.nx == UNDEF) {
            if (!fill) { res->result = R_UNDEF; break; }
            tnf_fill(tm, st, tape[head]);
            continue;
        }
        tape[head] = t.w;
        head += t.d;
        steps++;
        if (t.nx == HALT) { res->result = R_HALT; if (head < lo) lo = head; if (head > hi) hi = head; break; }
        st = t.nx;
        if (head < SNAP || head >= size - SNAP) { res->result = R_TAPE; break; }

        for (int s = 0; s < 2; s++) {  // gap minima in mirrored coords u = dir*head
            long u = s == 0 ? head : -head;
            if (u < gapmin[s]) gapmin[s] = u;
        }
        int side = -1;
        if (head > hi) { hi = head; side = 0; }
        else if (head < lo) { lo = head; side = 1; }

        if (side >= 0) {
            if (w->nrt < w->maxrt) w->rtimes[w->nrt++] = steps;
            int dir = side == 0 ? 1 : -1;
            long u = dir * head;
            Rec *ring = w->rec[side];
            long k = nrec[side];
            // look back for an earlier record in the same state with matching tape
            long running = u;  // min u over [t_j, now]
            for (long j = k - 1, back = 0; j >= 0 && back < RECRING - 1; j--, back++) {
                Rec *rj = &ring[j % RECRING], *rn = &ring[(j + 1) % RECRING];
                long g = j + 1 < k ? rn->gapmin : gapmin[side];
                if (g < running) running = g;
                if (rj->u < running) running = rj->u;
                if (rj->state != st) continue;
                long L = rj->u - running;
                if (L >= SNAP) break;
                int same = 1;
                for (long i = 0; i <= L; i++)
                    if (rj->snap[i] != tape[head - dir * i]) { same = 0; break; }
                if (same) {
                    res->result = R_TCYCLER;
                    res->period = steps - rj->step;
                    goto done;
                }
            }
            Rec *r = &ring[k % RECRING];
            r->step = steps; r->u = u; r->state = st; r->gapmin = gapmin[side];
            for (long i = 0; i < SNAP; i++) r->snap[i] = tape[head - dir * i];
            nrec[side] = k + 1;
            gapmin[side] = u;
        }

        // cycler: exact configuration repeat against the saved snapshot
        if (st == sv_st && head == sv_head && lo == sv_lo && hi == sv_hi &&
            memcmp(tape + lo, w->saved + lo, hi - lo + 1) == 0) {
            res->result = R_CYCLER;
            res->period = steps - sv_step;
            break;
        }
        if (steps - sv_step >= power) {
            power *= 2; sv_step = steps; sv_head = head; sv_lo = lo; sv_hi = hi; sv_st = st;
            memcpy(w->saved + lo, tape + lo, hi - lo + 1);
        }
        if (steps == limit / 2) { half_step = steps; half_width = hi - lo + 1; }
    }
done:
    res->steps = steps;
    res->width = hi - lo + 1;
    for (long i = lo; i <= hi; i++) res->ones += tape[i] != 0;
    memset(tape + lo, 0, hi - lo + 1);
    if (half_step && res->width > half_width)
        res->slope = log((double)res->width / half_width) / log((double)steps / half_step);
    if (res->result == R_HOLDOUT || res->result == R_TAPE) label_holdout(w, res);
}

static int check_one(const char *s, uint64_t limit);
static int cmd_check(const char *s, uint64_t limit) {
    if (strcmp(s, "-")) return check_one(s, limit);
    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        line[strcspn(line, "\t\r\n")] = 0;
        if (*line) check_one(line, limit);
        fflush(stdout);
    }
    return 0;
}

static Work *check_work;
static int check_one(const char *s, uint64_t limit) {
    TM tm;
    if (parse_tm(s, &tm)) { fprintf(stderr, "bad tm\n"); return 2; }
    if (!check_work) check_work = work_new(limit);
    Work *w = check_work;
    Result r;
    analyze(&tm, limit, 0, w, &r);
    if (getenv("BBDEBUG"))
        for (long i = w->nrt > 60 ? w->nrt - 60 : 0; i < w->nrt; i++)
            fprintf(stderr, "%llu%c", (unsigned long long)w->rtimes[i], i + 1 < w->nrt ? ' ' : '\n');
    printf("%s\t%s\t%llu\t%ld\t%ld\t%s\t%.3f\t%.3f\t%llu\n",
           s, RNAME[r.result], (unsigned long long)r.steps, r.width, r.ones,
           r.label, r.slope, r.novelty, (unsigned long long)r.period);
    return 0;
}

static int cmd_search(int n, int m, long samples, uint64_t seed, uint64_t limit) {
    Work *w = work_new(limit);
    rng_state = seed * 0x9E3779B97F4A7C15ULL + 1;
    long count[6] = {0};
    uint64_t best = 0; char bestm[128] = "", buf[128];
    for (long i = 0; i < samples; i++) {
        TM tm; memset(&tm, 0, sizeof tm); tm.n = n; tm.m = m;
        for (int a = 0; a < n; a++) for (int b = 0; b < m; b++) tm.t[a][b].nx = UNDEF;
        tm.t[0][0] = (Tr){1, 1, 1};  // TNF: A0 = 1RB
        Result r;
        analyze(&tm, limit, 1, w, &r);
        count[r.result]++;
        format_tm(&tm, buf);
        if (r.result == R_HALT && r.steps > best) { best = r.steps; strcpy(bestm, buf); }
        if (r.result == R_HOLDOUT || r.result == R_TAPE)
            printf("%s\t%s\t%llu\t%ld\t%ld\t%s\t%.3f\t%.3f\n", buf, RNAME[r.result],
                   (unsigned long long)r.steps, r.width, r.ones, r.label, r.slope, r.novelty);
        if (r.result == R_HALT && r.steps > 1000)
            fprintf(stderr, "#halter\t%s\t%llu\n", buf, (unsigned long long)r.steps);
    }
    fprintf(stderr, "#summary\tdomain=BB(%d,%d)\tsamples=%ld\tlimit=%llu", n, m, samples,
            (unsigned long long)limit);
    for (int k = 0; k < 6; k++) fprintf(stderr, "\t%s=%ld", RNAME[k], count[k]);
    fprintf(stderr, "\tbest_halt=%llu\t%s\n", (unsigned long long)best, bestm);
    return 0;
}

// ------------------------------------------------------------------ diagram
// Binary output: int32 width, int32 rows, int64 steps-per-row, int32 head-offset
// for each row, then rows*width symbol bytes. Pass 1 finds the visited range.

static int cmd_diagram(const char *s, uint64_t steps, long rows, const char *out) {
    TM tm;
    if (parse_tm(s, &tm)) { fprintf(stderr, "bad tm\n"); return 2; }
    long size = 1L << 26;
    uint8_t *tape = calloc(size, 1);
    long lo = 0, hi = 0;
    uint64_t done_steps = 0;
    for (int pass = 0; pass < 2; pass++) {
        memset(tape, 0, size);
        long head = size / 2, plo = head, phi = head;
        int st = 0, halted = 0;
        uint64_t every = steps / rows ? steps / rows : 1;
        long width = hi - lo + 1, row = 0;
        FILE *f = NULL;
        if (pass == 1) {
            f = fopen(out, "wb");
            int32_t W = (int32_t)width, H = (int32_t)rows; int64_t E = (int64_t)every;
            fwrite(&W, 4, 1, f); fwrite(&H, 4, 1, f); fwrite(&E, 8, 1, f);
        }
        uint8_t *line = calloc(width + 1, 1);
        int32_t *heads = calloc(rows, 4);
        uint64_t k = 0;
        for (;;) {
            if (pass == 1 && k % every == 0 && row < rows) {
                memcpy(line, tape + lo, width);
                if (!halted) heads[row] = (int32_t)(head - lo); else heads[row] = -1;
                fwrite(line, 1, width, f);
                row++;
            }
            if (k >= steps || halted) { if (pass == 0 || row >= rows) break; else { k++; continue; } }
            Tr t = tm.t[st][tape[head]];
            if (t.nx == UNDEF) { halted = 1; continue; }
            tape[head] = t.w; head += t.d; k++;
            if (head < plo) plo = head;
            if (head > phi) phi = head;
            if (t.nx == HALT) halted = 1; else st = t.nx;
            if (head <= 0 || head >= size - 1) halted = 1;
        }
        if (pass == 0) { lo = plo; hi = phi; done_steps = k; }
        else { fwrite(heads, 4, rows, f); fclose(f); }
        free(line); free(heads);
    }
    printf("width=%ld steps=%llu\n", hi - lo + 1, (unsigned long long)done_steps);
    free(tape);
    return 0;
}

// ---------------------------------------------------------------- n-gram CPS
//
// Abstract configuration = (left n-gram, state, head symbol, right n-gram).
// The n-grams are the n cells next to the head on each side, packed base m with
// the cell adjacent to the head as the lowest digit. Two sets over-approximate
// every n-gram (window of n consecutive cells) that can occur in the left / right
// half-tape. Start: all zeros. Step right: write w, push w onto the left gram
// (new left window, added to the left set), the new head symbol is the right
// gram's lowest digit, and the right gram's far cell may be any x such that the
// resulting window is in the right set. Steps left are mirrored. When the sets
// stop growing and no reachable abstract configuration can halt (or hit "---"),
// no real configuration can either: the machine never halts.

typedef struct { uint64_t *k; size_t cap, n; } HSet;  // open addressing, key 0 reserved

static void hs_init(HSet *h, size_t cap) { h->cap = cap; h->n = 0; h->k = calloc(cap, sizeof *h->k); }
static void hs_free(HSet *h) { free(h->k); h->k = 0; }
static uint64_t hs_mix(uint64_t x) { x ^= x >> 33; x *= 0xff51afd7ed558ccdULL; x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53ULL; return x ^ (x >> 33); }
static int hs_has(const HSet *h, uint64_t key) {
    key++;
    for (size_t i = hs_mix(key) & (h->cap - 1);; i = (i + 1) & (h->cap - 1)) {
        if (!h->k[i]) return 0;
        if (h->k[i] == key) return 1;
    }
}
static int hs_add(HSet *h, uint64_t key) {  // 1 if newly added
    if (2 * (h->n + 1) > h->cap) {
        HSet g; hs_init(&g, h->cap * 2);
        for (size_t i = 0; i < h->cap; i++) if (h->k[i]) hs_add(&g, h->k[i] - 1);
        hs_free(h); *h = g;
    }
    key++;
    for (size_t i = hs_mix(key) & (h->cap - 1);; i = (i + 1) & (h->cap - 1)) {
        if (!h->k[i]) { h->k[i] = key; h->n++; return 1; }
        if (h->k[i] == key) return 0;
    }
}

// Generic transition table so CPS can also run on block ("macro") machines.
#define G_HALT 127
#define G_UNDEF 126
#define G_LOOP 125  // the head never leaves the block: no successor, never halts
typedef struct { int ns, nm; int8_t *w, *d, *nx; } GT;

// Block machine: k cells per macro symbol. Macro state = state * 2 + side, side 0 = head
// on the block's left cell (entered moving right), 1 = on its right cell.
static int macro_build(const TM *tm, int k, GT *g) {
    int nm = 1;
    for (int i = 0; i < k; i++) nm *= tm->m;
    if (nm > 125 || 2 * tm->n > 120) return -1;
    g->ns = 2 * tm->n; g->nm = nm;
    size_t sz = (size_t)g->ns * nm;
    g->w = malloc(sz); g->d = malloc(sz); g->nx = malloc(sz);
    long guard = (long)tm->n * k * nm + 2;  // more steps than (state, pos, block) combinations
    for (int q = 0; q < tm->n; q++)
        for (int side = 0; side < 2; side++)
            for (int b = 0; b < nm; b++) {
                int cell[16], x = b;  // k <= 7 (m^k <= 125)
                for (int i = 0; i < k; i++) { cell[i] = x % tm->m; x /= tm->m; }
                int pos = side ? k - 1 : 0, st = q, res = G_LOOP, dir = 0;
                for (long t = 0; t < guard; t++) {
                    const Tr *tr = &tm->t[st][cell[pos]];
                    if (tr->nx == UNDEF) { res = G_UNDEF; break; }
                    cell[pos] = tr->w;
                    pos += tr->d;
                    if (tr->nx == HALT) { res = G_HALT; break; }
                    st = tr->nx;
                    if (pos < 0 || pos >= k) { dir = pos < 0 ? -1 : 1; res = 0; break; }
                }
                size_t i = (size_t)(2 * q + side) * nm + b;
                int nb = 0;
                for (int j = k - 1; j >= 0; j--) nb = nb * tm->m + cell[j];
                g->w[i] = (int8_t)nb; g->d[i] = (int8_t)dir;
                g->nx[i] = res ? (int8_t)res : (int8_t)(2 * st + (dir < 0));
            }
    return 0;
}
static void gt_free(GT *g) { free(g->w); free(g->d); free(g->nx); }

#define CPS_PACK(l, r, q, s) (((uint64_t)(l) << 39) | ((uint64_t)(r) << 14) | ((uint64_t)(q) << 7) | (uint64_t)(s))
#define CPS_GRAM ((1ULL << 25) - 1)

// 1 = proved non-halting, 0 = not proved (halt reachable or too big). *nconf = abstract configs.
static int cps_n(const GT *g, int n, size_t maxconf, size_t *nconf) {
    int m = g->nm;
    uint64_t M = 1, top;
    for (int i = 0; i < n; i++) { if (M > CPS_GRAM / m) return 0; M *= m; }
    top = M / m;  // weight of the far digit
    HSet L, R, C;
    hs_init(&L, 1024); hs_init(&R, 1024); hs_init(&C, 4096);
    size_t qcap = 4096, qn = 0;
    uint64_t *queue = malloc(qcap * sizeof *queue);
    hs_add(&L, 0); hs_add(&R, 0);
    hs_add(&C, CPS_PACK(0, 0, 0, 0));
    queue[qn++] = CPS_PACK(0, 0, 0, 0);
    int ok = 1;
    for (;;) {
        int grew = 0;
        while (qn && ok) {
            uint64_t c = queue[--qn];
            uint64_t l = c >> 39, r = (c >> 14) & CPS_GRAM;
            int q = (c >> 7) & 127, s = c & 127;
            size_t ti = (size_t)q * m + s;
            int nx = g->nx[ti], w = g->w[ti];
            if (nx == G_UNDEF || nx == G_HALT) { ok = 0; break; }
            if (nx == G_LOOP) continue;
            uint64_t succ[128]; int ns = 0;
            if (g->d[ti] > 0) {  // move right
                uint64_t l2 = (l * m + w) % M;
                if (hs_add(&L, l2)) grew = 1;
                int hs = (int)(r % m);
                uint64_t rest = r / m;
                for (int x = 0; x < m; x++) {
                    uint64_t r2 = rest + (uint64_t)x * top;
                    if (hs_has(&R, r2)) succ[ns++] = CPS_PACK(l2, r2, nx, hs);
                }
            } else {  // move left
                uint64_t r2 = (r * m + w) % M;
                if (hs_add(&R, r2)) grew = 1;
                int hs = (int)(l % m);
                uint64_t rest = l / m;
                for (int x = 0; x < m; x++) {
                    uint64_t l2 = rest + (uint64_t)x * top;
                    if (hs_has(&L, l2)) succ[ns++] = CPS_PACK(l2, r2, nx, hs);
                }
            }
            for (int i = 0; i < ns; i++)
                if (hs_add(&C, succ[i])) {
                    if (C.n > maxconf) { ok = 0; break; }
                    if (qn == qcap) queue = realloc(queue, (qcap *= 2) * sizeof *queue);
                    queue[qn++] = succ[i];
                }
        }
        if (!ok || !grew) break;
        // The gram sets grew: earlier configurations may now have new successors.
        for (size_t i = 0; i < C.cap; i++) if (C.k[i]) {
            if (qn == qcap) queue = realloc(queue, (qcap *= 2) * sizeof *queue);
            queue[qn++] = C.k[i] - 1;
        }
    }
    *nconf = C.n;
    free(queue); hs_free(&L); hs_free(&R); hs_free(&C);
    return ok;
}

// Try block sizes k = 1..kmax and gram lengths n = 1..nmax (cheapest first).
static int cps_one(const char *s, int nmax, size_t maxconf, int kmax) {
    TM tm;
    if (parse_tm(s, &tm)) { fprintf(stderr, "bad tm\n"); return 2; }
    size_t nc = 0;
    for (int k = 1; k <= kmax; k++) {
        GT g;
        if (macro_build(&tm, k, &g)) break;
        for (int n = 1; n <= nmax; n++)
            if (cps_n(&g, n, maxconf, &nc)) {
                printf("%s\tcps_proved\t%d\t%zu\t%d\n", s, n, nc, k);
                gt_free(&g);
                return 0;
            }
        gt_free(&g);
    }
    printf("%s\tcps_fail\t%d\t%zu\t%d\n", s, nmax, nc, kmax);
    return 0;
}

static int cmd_cps(const char *s, int nmax, size_t maxconf, int kmax) {
    if (strcmp(s, "-")) return cps_one(s, nmax, maxconf, kmax);
    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        line[strcspn(line, "\t\r\n")] = 0;
        if (*line) cps_one(line, nmax, maxconf, kmax);
        fflush(stdout);
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc >= 3 && !strcmp(argv[1], "run"))
        return cmd_run(argv[2], argc > 3 ? strtoull(argv[3], 0, 10) : 100000000ULL);
    if (argc >= 3 && !strcmp(argv[1], "check"))
        return cmd_check(argv[2], argc > 3 ? strtoull(argv[3], 0, 10) : 1000000ULL);
    if (argc >= 7 && !strcmp(argv[1], "search"))
        return cmd_search(atoi(argv[2]), atoi(argv[3]), atol(argv[4]),
                          strtoull(argv[5], 0, 10), strtoull(argv[6], 0, 10));
    if (argc >= 6 && !strcmp(argv[1], "diagram"))
        return cmd_diagram(argv[2], strtoull(argv[3], 0, 10), atol(argv[4]), argv[5]);
    if (argc >= 3 && !strcmp(argv[1], "cps"))
        return cmd_cps(argv[2], argc > 3 ? atoi(argv[3]) : 8, argc > 4 ? strtoull(argv[4], 0, 10) : 2000000,
                       argc > 5 ? atoi(argv[5]) : 1);
    fprintf(stderr, "usage: bb run|check|search|diagram|cps ...\n");
    return 2;
}
