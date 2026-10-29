# Busy Beaver explorer — handoff

Last updated: 2026-10-21 (bouncer decider added, deployed)

## Objective
A visual, Korean-language Busy Beaver explorer: a fast TM simulator (checked against
BB(5)), a random-sampling search over open domains BB(6) and BB(2,5) with simple
deciders, holdouts rendered as space-time diagrams, and a page explaining it all.

## Layout
- `src/bb.c` — C toolkit (single file). Subcommands:
  - `./bb run <tm> [limit]` — plain simulation → `halt steps=… nonzero=… width=…`
  - `./bb check <tm|-> [limit]` — deciders + heuristics on one machine (or stdin list).
    TSV: tm, result, steps, width, nonzero, label, slope, novelty, period
  - `./bb search <n> <m> <samples> <seed> <limit>` — random TNF walk; prints holdouts
    (stdout) and `#summary` / `#halter` lines (stderr)
  - `./bb diagram <tm> <steps> <rows> <out.bin>` — space-time dump for rendering
  - `./bb cps <tm|-> [nmax] [maxconf] [kmax]` — n-gram CPS proof (Fenner's simple n-gram CPS),
    also on k-cell block machines. TSV: tm, cps_proved|cps_fail, n, configs, k
- `src/bouncer.py` — bouncer decider (Python): symbolic simulation of a run-length k-cell macro
  machine with shift rules + induction rules (Ligocki-style). `python3 src/bouncer.py <tm|-> [maxops] [kmax]`
  → TSV tm, bouncer_proved|halt|bouncer_fail, k, ops, rules, final rule (readable).
- `src/test_bouncer.py` — its soundness test (random halters, long halters at 4 op limits, BB(2..5)/BB(2,4),
  cryptids, and a replay of every accepted rule on the real machine with concrete counts).
- `src/render.py` — PNG renderer + contact sheets (Pillow).
- `src/build.py` — renders `web/img/*.png` and writes `web/index.html` from `out/`.
- `run_search.sh` — whole pipeline end to end.
- `out/` — search results (TSV), `out/img/` scratch contact sheets.
- `web/` — the deliverable page (open via a local server; relative image paths).
  `web/stepper.js` is hand-written (not generated): the in-browser simulator (section II).
  `node src/test_stepper.js` checks its core against `./bb run` (BB(2..5), BB(2,4), a `---` stop).

## Commands that worked
```
cc -O2 -Wall -o bb src/bb.c -lm
./bb run 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA     # halt steps=47176870 nonzero=4098 (0.3 s)
sh run_search.sh                                 # full pipeline
python3 src/build.py                             # page only (~1-6 min, renders 48 PNGs)
python3 src/bouncer.py - 20000 4 < out/left_after_cps.txt > out/bouncer.tsv   # ~1-2 min
python3 src/test_bouncer.py 3000 1               # bouncer soundness test (~5-10 min, all cores)
```
Preview: server `busy-beaver` (port 8971) in `Claude_etc/.claude/launch.json`
(serves `busy-beaver/web`). A file:// static snapshot does NOT load images.

## Deployment
- Vercel project `busy-beaver` (scope magic3ightballs-projects): https://busy-beaver-gamma.vercel.app
- Deploy from `web/`: `npx vercel@latest deploy --prod --yes --scope magic3ightballs-projects`
  (scope is required; delete the `.env.local` OIDC token that `vercel link` creates; `.vercelignore` excludes `.env*`).
- Listed in the deployed-links hub (Claude_etc/deployed-links, Artifact WeMHp8FL1itahUZVD4W9NA).

## Verified results
- Simulator matches BB(2)=6, BB(3)=21, BB(4)=107, BB(5)=47,176,870 (4,098 ones),
  BB(2,4)=3,932,964.
- Deciders: Antihydra, Hydra, Bigfoot, Space Needle stay holdouts (label irregular);
  Lucy's Moonlight gets a `bouncer_p5` label at 1M steps (heuristic false positive —
  it is believed to halt, much later).
- Search (seeds 1-4, limit 100k): BB(6) 10M samples → 68,363 holdouts → 17,997 unique →
  496 unlabelled → 365 irregular at 10M → 58 using all 6 states.
  BB(2,5) 4M samples → 58,391 → 15,250 unique → 1,017 → 696 → 362 using symbol 4.
- 13 flagged (unusual growth exponent, still irregular at 1e8), all run to 1e9 steps:
  none halted. List in `out/flagged.txt`, results `out/flagged_1e9.txt`.
- Page checked in browser: 48/48 images load, no horizontal scroll at 375 px.

## Design notes
- TNF walk: A0 fixed to 1RB; at each undefined transition pick uniformly among
  {written symbol ≤ max+1} × {L,R} × {next state ≤ max+1}; the last free slot becomes 1RZ.
- Translated cycler: wiki record-breaking method, 256-cell snapshots, 4096 records/side.
- Cycler: Brent-style snapshot at doubling step counts, compare only when state/head/
  range match.
- Bouncer heuristic: record-time gaps whose lag-P difference is P-periodic. Counter:
  slope < 0.15 or geometric record times. Neither is a proof.
- "novelty" (distinct 2nd differences of record events) turned out not to separate
  cryptids from ordinary holdouts; kept in output but not used for flagging.

## Design polish (started 2026-10-20)
- User wants the site and graphs to look more beautiful before the decider/stepper work.
- Mood reference board: `docs/design-refs/index.html` (preview server `busy-beaver-refs`, port 8972).
  6 moods (mono, night, editorial, vintage, pastel, neon), ~34 captured references with source links,
  plus our own diagrams re-rendered per mood by `python3 docs/design-refs/moods.py` (palettes in MOODS).
- Reference images are private copies for viewing only; `docs/` is not deployed. Do not move them into `web/`.
- Captures were made with Playwright from `Claude_etc/squishy-lab/node_modules/playwright` (no new install).
- User picks (10-20): moods 1 (mono/Tufte) + 4 (vintage plates), plus Hubble, Gravitational Waves,
  Wolfram TM pictures, Fidenza, Lenia, Growing NCA, A Year in Flights.
- Applied and deployed 2026-10-20: "field atlas" style — parchment page, Noto Serif KR +
  EB Garamond + IBM Plex Mono (Google Fonts), roman-numeral sections, every figure a numbered
  "도판" plate on navy (#0b1026) with a gold hairline, Tufte dot-bars in the funnel tables,
  width sparklines next to cryptids/flagged machines (from `render()` info["extents"]).
- Diagram palette (`src/render.py`): navy bg, cream/teal/gold/lavender/pink…, vermilion head.
  Downsampled columns are faded by zero-density so long runs show texture instead of a solid block.
- Checked: 49/49 images load, 16 sparklines, light + dark, no horizontal scroll at 375 px.
- User feedback after deploy (10-20): the field-atlas look is "너무 별로" — wants something **modern**.
  New board `docs/design-refs/modern.html` (3 directions: dark product / light minimal / interactive
  explainer, 11 site captures in `docs/design-refs/modern/`). Waiting for picks before restyling again.
  Picks: Vercel, Stripe, Anthropic research post, Rauno → **light minimal** restyle (built 10-20, not deployed yet):
  sticky blurred nav, hero (big Pretendard title + colourful fan diagram), 4-number stat row, "01…06" mono
  section labels, rounded figure cards ("그림 N"), pill funnel bars, Geist Mono for code/numbers.
  Diagrams render twice (`web/img/` light, `web/img/dark/` dark) via `render(paths=...)`, swapped with
  `<picture>`; stepper colours follow prefers-color-scheme. Fonts: Pretendard (jsDelivr) + Geist Mono (Google).
- User still dislikes it (10-20). Review: only the hero follows the refs; the rest is a CSS reskin of the
  same dense layout, diagrams sit as slivers in big empty cards. Live site is still field-atlas. See
  `docs/design-refs/compare-refs-vs-page.jpg`. Next: hero + one-section mock for approval first.
- Mock built: `docs/design-refs/mock/index.html` (served at :8972/mock/), images from
  `python3 docs/design-refs/mock/mock.py` (render large → crop to ink → LANCZOS downscale).
  Hero A = BB(5) black silhouette, Hero B = colourful fan bleeding off the edge, + cryptid card section.
  Screenshots mock-desk-*.png / mock-phone-*.png. User rejected both (landing-page mood/layout is the problem).
- Direction now: research note + interactive explainer + simulator. Mock `docs/design-refs/mock/note.html`
  (:8972/mock/note.html): paper-style header + TOC + TL;DR, section 01 with two live widgets (BB(2) step-by-step
  with rule highlight + explanation; space-time builder for BB(2)/(3)/(4)) and a wide figure. Tested with
  Playwright (BB(2) stops at 6, BB(4) at 107, no errors, no h-scroll at 390 px). Approved.
- Whole site rebuilt in that style and **deployed 2026-10-20** (live check: 42 images, widgets + simulator OK): `src/build.py` HTML section rewritten
  (TOC + TL;DR + sections 01-06 + sources; cryptid cards, class rows, candidate cards; images cropped to ink
  via `img(..., crop=True)`), widgets in hand-written `web/explainer.js`, simulator restyled.
  Checked desktop/phone/dark: 42 images load, no console errors, widgets and simulator stop correctly.

## Real deciders (2026-10-20)
- n-gram CPS in `src/bb.c` (`cps_n`, `macro_build`). Soundness test `python3 src/test_cps.py 30000 <seed>`:
  random 2-4 state machines, any halting machine marked proved = bug. Seeds 1-4: 0 unsound.
  Halters BB(2..5), BB(2,4) and the cryptids Antihydra/Hydra/Bigfoot are all `cps_fail` (as they must be).
- Results: 405/420 full-domain holdouts proved non-halting (BB(6) 55/58, BB(2,5) 350/362), incl. all 13 flagged.
  Leftovers in `out/left_after_cps.txt` (15, mostly sqrt-growth bouncers).
- `src/compare_official.py` matches machines by behaviour (state/symbol renaming + mirror; self-tested on a
  transformed Hydra). `out/official25.tsv` = BB(2,5) holdout sections copied from the wiki page on 10-20
  (extracted via WebFetch summary — may have transcription gaps). None of our 12 BB(2,5) leftovers is in it.
- Page: TL;DR, section 05 "진짜 증명" result cards, funnel last row, section 06 now "모두 안 멈춤" with proof badges.
  Deployed 2026-10-20; live check: 42 images, 13 proof badges, '405 / 420', widgets + simulator OK, no errors.

## Bouncer decider (2026-10-21)
- Plain record-formula bouncer decider (w0 u^(a+n) ... ; shift rules) proved 0/15: the leftovers zig-zag a
  *variable* number of times inside one bounce, and some work in phases (count x -> 4x+12).
- What works: `src/bouncer.py`. Tape = stacks of [macro cell, count] runs, head between cells facing a side.
  Shift rule over a whole run; when a run-length shape repeats (A -> B), counts that changed become m + p*y
  (p = 1..4 for parity classes), the shape is simulated symbolically until the visit matching B, and the result
  counts are read off as linear forms -> rule. Rules apply a symbolic number of times inside later proofs.
  A rule whose result fits its own pattern again (counts never shrink) that matches a configuration the real
  run reached = non-halting proof. Every move is valid for all y >= 0 (taking one copy needs const >= 1).
- Bug found and fixed during development: re-recording the same config after a rule proof looked like a cycle
  (false proof). Records now happen only right before a real move.
- Soundness: `python3 src/test_bouncer.py 3000 <seed>`, seeds 1-3 all pass (seed 1 in out/test_bouncer.txt):
  ~1,400 random halters per seed never proved; champions BB(2..5), BB(2,3), BB(2,4) and the BB(6) champion,
  each decided at 5 op limits (60..20000), never proved; cryptids never proved; 1,743 / 1,846 / 2,046 accepted
  rules replayed on the real machine with concrete counts, 0 wrong (57 skipped: instance > 6,000 cells).
  Uniform random machines almost never halt late (whole BB(6) search's longest halter: 174 steps), so the
  champions are the "long halter" set.
- Test pitfalls fixed: a worker died expanding a rule with a huge count (Pool hung forever) -> size cap +
  ProcessPoolExecutor; Antihydra's real 3a/2-type rules need ~10M steps to replay -> cap = 300k + 2 W^2.
- Results (`out/bouncer.tsv`, 20000 ops, k <= 4): 5/15 proved (BB(6) 2/3, BB(2,5) 3/12). The other 10
  (`out/left_after_bouncer.txt`) all show a small irregularly changing patch near one end (binary-counter-like);
  run-length shapes cannot describe that. Same 5/15 at 5000 ops, k <= 3.
- Page: TL;DR line, section 05 "진짜 증명 2: 바운서 판정기" (method, 3 result cards, the 5 final rules), funnel
  row "바운서 판정기로도 증명 못 한 것" (BB(6) 1, BB(2,5) 9). Built 2026-10-21; Playwright check: 42/42 images,
  0 console errors, no h-scroll at 390 px (light + dark), BB(2) widget 6, BB(4) 107, simulator stops.
  **Deployed 2026-10-21** (user approved); live check same results (42/42 images, 5 proof rows, cards 5/15 · 0/1,398 · 0/1,743).

## Next recommended step
- The 10 counter-like leftovers need a different decider (e.g. finite-automata based, like bbchallenge's FAR).
- BB(6): compare the 1 remaining BB(6) leftover with the official holdout file (needs a download; ask first).
- In-browser stepper: DONE 2026-10-20 (section II "직접 돌려 보기"): presets, custom input, step/play,
  speed 3 steps/s … 1M steps/frame, live rule highlight, tape strip, space-time canvas (last 360 rows,
  8 snapshots/frame at fast speeds). BB(5) runs to 47,176,870 / 4,098 in the page. Stepper changes were
  made after the 10-20 deploy; redeploy once approved.
  Hidden Browser pane throttles rAF: front the tab (tabs_select) before timing "play".

## Risks / caveats
- Nothing here is a cryptid claim. Random holdouts are almost certainly decidable by
  bbchallenge's stronger deciders. Do not post to bbchallenge forums/Discord.
- Wiki numbers (holdout counts etc.) were read on 2026-10-20 and change often.
- `out/` is regenerable; not a git repo yet.
