#!/bin/sh
# Reproduce the whole pipeline: build, verify, search, deep re-check, page.
# Takes ~10-20 min on a free laptop (longer when other jobs share the CPU).
set -e
cd "$(dirname "$0")"
cc -O2 -Wall -o bb src/bb.c -lm

# 1. Verify against known values.
./bb run 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA   # expect halt steps=47176870 nonzero=4098
./bb run 1RB2LA1RA1RA_1LB1LA3RB1RZ            # expect halt steps=3932964 (BB(2,4))

mkdir -p out
# 2. Random TNF walk: 4 seeds per domain, 100k-step limit.
for s in 1 2 3 4; do
  ./bb search 6 2 2500000 $s 100000 > out/s6_$s.tsv 2> out/s6_$s.err &
  ./bb search 2 5 1000000 $s 100000 > out/s25_$s.tsv 2> out/s25_$s.err &
done
wait

# 3. Dedupe; re-check the heuristically unlabelled ("irregular") ones to 10M.
for d in 6 25; do
  cat out/s${d}_?.tsv | sort -u -t"$(printf '\t')" -k1,1 > out/u$d.tsv
  awk -F'\t' '$6=="irregular"||$6=="few_records"{print $1}' out/u$d.tsv | ./bb check - 10000000 > out/deep$d.tsv
done

# 4. Keep only machines that use every state (BB(6): references F) or every
#    symbol (BB(2,5): writes 4); smaller ones live in already-solved domains.
awk -F'\t' '$2=="holdout" && $1 ~ /F/' out/deep6.tsv > out/full6.tsv
awk -F'\t' '$2=="holdout"{split($1,a,"_"); s=a[1]a[2]; gsub(/[A-Z-]/,"",s); if (s ~ /4/) print}' out/deep25.tsv > out/full25.tsv

# 5. Flag unusual growth (not ~log, ~t^(1/3), ~t^(1/2)), re-check at 1e8 and 1e9.
cat out/full6.tsv out/full25.tsv | awk -F'\t' '$6=="irregular" && !($7<0.15 || ($7>=0.28&&$7<=0.38) || ($7>=0.42&&$7<=0.58))' > out/odd.tsv
cut -f1 out/odd.tsv | ./bb check - 100000000 > out/odd100m.tsv
awk -F'\t' '$6=="irregular"{print $1}' out/odd100m.tsv > out/flagged.txt
cat out/flagged.txt | xargs -P 8 -I{} sh -c 'echo "{} $(./bb run {} 1000000000)"' > out/flagged_1e9.txt

# 6. Real proofs: n-gram CPS on every remaining holdout, first on single cells,
#    then on k-cell blocks (BB(6): k <= 6, BB(2,5): k <= 2). Soundness test first.
python3 src/test_cps.py 30000 1
for d in 6 25; do awk -F'\t' '$6=="irregular"{print $1}' out/full$d.tsv > out/hold$d.txt; done
./bb cps - 12 4000000 6 < out/hold6.txt > out/cps6.tsv
./bb cps - 10 4000000 2 < out/hold25.txt > out/cps25.tsv
cat out/cps6.tsv out/cps25.tsv | awk -F'\t' '$2=="cps_fail"{print $1}' > out/left_after_cps.txt
# Compare the leftovers with the BB(2,5) holdout list on the wiki (out/official25.tsv,
# copied by hand from wiki.bbchallenge.org/wiki/BB(2,5) on 2026-10-20).
python3 src/compare_official.py out/left_after_cps.txt out/official25.tsv 200000 > out/official_compare.txt
# Bouncer decider (symbolic simulation + induction rules) on what CPS left.
# Soundness test first: no halting machine proved, every proved rule replayed for real.
python3 src/test_bouncer.py 3000 1 > out/test_bouncer.txt
python3 src/bouncer.py - 20000 4 < out/left_after_cps.txt > out/bouncer.tsv
awk -F'\t' '$2!="bouncer_proved"{print $1}' out/bouncer.tsv > out/left_after_bouncer.txt

# 7. Diagrams + Korean page.
python3 src/build.py
