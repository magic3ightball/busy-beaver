"""Build web/index.html (Korean explainer) and web/img/*.png from out/ results.

Run from the repo root after the search pipeline (see docs/codex/handoff.md):
    python3 src/build.py
"""
import collections
import glob
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render  # noqa: E402
from PIL import Image, ImageChops  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
WEB = os.path.join(ROOT, "web")
IMG = os.path.join(WEB, "img")
os.makedirs(os.path.join(IMG, "dark"), exist_ok=True)


def tsv(name):
    path = os.path.join(OUT, name)
    if not os.path.exists(path):
        return []
    return [l.rstrip("\n").split("\t") for l in open(path) if l.strip()]


INFO = {}


def img(name, tm, steps, rows=400, max_w=700, min_scale=1, crop=False):
    rows = min(rows, steps + 1)
    light, dark = os.path.join(IMG, name), os.path.join(IMG, "dark", name)
    _, info = render.render(tm, steps, rows=rows, max_w=max_w, min_scale=min_scale,
                            paths={"light": light, "dark": dark})
    if crop:  # trim empty tape on both sides so the shape fills its card
        a = Image.open(light).convert("RGB")
        box = ImageChops.difference(a, Image.new("RGB", a.size, (255, 255, 255))).getbbox()
        if box:
            a.crop(box).save(light)
            Image.open(dark).crop(box).save(dark)
    info["steps"] = steps
    INFO[f"img/{name}"] = info
    return f"img/{name}"


def slug(tm):
    return tm.replace("-", "x").replace("_", "-")


# ------------------------------------------------------------ search numbers
totals = collections.defaultdict(collections.Counter)
best = {}
for f in glob.glob(os.path.join(OUT, "s*_?.err")):
    for line in open(f):
        if not line.startswith("#summary"):
            continue
        parts = line.strip().split("\t")[1:]
        kv = dict(p.split("=", 1) for p in parts if "=" in p)
        d = kv["domain"]
        for k in ("samples", "halt", "cycler", "translated_cycler", "holdout"):
            totals[d][k] += int(kv[k])
        b = int(kv["best_halt"])
        if b > best.get(d, (0, ""))[0]:
            best[d] = (b, parts[-1])


def count(name, pred=lambda r: True):
    return sum(1 for r in tsv(name) if pred(r))


irr = lambda r: r[5] in ("irregular", "few_records")  # noqa: E731
funnel = {}
for key, d, dom in (("6", "BB(6,2)", "BB(6)"), ("25", "BB(2,5)", "BB(2,5)")):
    t = totals[d]
    funnel[dom] = [
        ("무작위로 만든 기계", t["samples"]),
        ("멈춤 (halt)", t["halt"]),
        ("순환 (cycler)으로 판정", t["cycler"]),
        ("평행이동 순환 (translated cycler)으로 판정", t["translated_cycler"]),
        ("10만 걸음 동안 판정 못 함 (holdout)", t["holdout"]),
        ("중복 제거 후 holdout", count(f"u{key}.tsv")),
        ("그중 바운서·카운터 패턴도 아닌 것", count(f"u{key}.tsv", irr)),
        ("1천만 걸음까지 다시 돌려도 불규칙", count(f"deep{key}.tsv", lambda r: r[1] == "holdout" and r[5] == "irregular")),
        (f"그중 {'상태 6개' if key == '6' else '기호 5개'}를 전부 쓰는 것", count(f"full{key}.tsv", lambda r: r[5] == "irregular")),
    ]

# ------------------------------------------------------------ images
print("rendering…", flush=True)
BB5 = "1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA"
CRYPTIDS = [
    ("Antihydra (BB(6))", "1RB1RA_0LC1LE_1LD1LC_1LA0LB_1LF1RE_---0RA",
     "규칙: 수 n을 ⌊3n/2⌋+2로 바꾸기를 반복하며 홀수·짝수 개수를 셉니다. 홀수가 짝수의 두 배보다 많아지는 순간 멈춥니다. "
     "콜라츠 문제와 비슷해서 아무도 멈출지 증명하지 못했습니다. 2024년 6월 mxdys가 처음 보고했습니다."),
    ("Hydra (BB(2,5))", "1RB3RB---3LA1RA_2LA3RA4LB0LB0LA",
     "Antihydra의 '원조'. 2024년 4월 발견된 2상태·5기호 크립티드로, 역시 콜라츠 같은 규칙으로 줄어듭니다."),
    ("Bigfoot (BB(3,3))", "1RB2RA1LC_2LC1RB2RB_---2LA1LA",
     "2023년 10월 발견된 3상태·3기호 크립티드. 이 기계 때문에 BB(3,3)을 끝내려면 수학 난제 하나를 풀어야 합니다."),
]
pics = {
    "bb2": img("bb2.png", "1RB1LB_1LA1RZ", 6, min_scale=40),
    "bb4": img("bb4.png", "1RB1LB_1LA0LC_1RZ1LD_1RD0RA", 107, min_scale=6),
    "bb5_early": img("bb5_early.png", BB5, 3000),
    "bb5_long": img("bb5_long.png", BB5, 47176870),
}
cryptid_html = []
for name, tm, note in CRYPTIDS:
    a = img(f"c_{slug(tm)}_early.png", tm, 3000, crop=True)
    b = img(f"c_{slug(tm)}_long.png", tm, 30000000, crop=True)
    cryptid_html.append((name, tm, note, a, b))

# Class examples drawn from our own full-domain holdouts.
full = tsv("full6.tsv") + tsv("full25.tsv")


def pick(pred, n=3):
    rows = [r for r in full if pred(r)]
    rows.sort(key=lambda r: -int(r[3]))
    return rows[:n]


CLASSES = [
    ("바운서 (bouncer)", "좌우로 왕복하며 테이프를 한 칸씩 넓힙니다. 왕복 시간이 규칙적으로 길어집니다. (휴리스틱으로 판정)",
     pick(lambda r: r[5].startswith("bouncer"))),
    ("카운터 (counter)", "2진수 세기처럼 동작해서 테이프가 아주 천천히(로그 속도로) 자랍니다.",
     pick(lambda r: r[5] == "counter_like" or (r[5] == "irregular" and float(r[6]) < 0.15))),
    ("세제곱근 성장", "폭이 걸음 수의 약 1/3제곱으로 자랍니다. 바운서 안에 또 다른 반복이 들어 있는 경우가 많습니다.",
     pick(lambda r: r[5] == "irregular" and 0.28 <= float(r[6]) <= 0.38)),
    ("제곱근 성장 (복잡한 바운서?)", "폭이 √걸음 수로 자라지만 단순 바운서 검사에는 걸리지 않습니다. Antihydra도 겉보기엔 이 무리에 속합니다.",
     pick(lambda r: r[5] == "irregular" and 0.42 <= float(r[6]) <= 0.58)),
]
class_html = []
for title, desc, rows in CLASSES:
    items = [(r[0], img(f"k_{slug(r[0])}.png", r[0], 2000, max_w=400, crop=True)) for r in rows]
    class_html.append((title, desc, items))

# Flagged machines: unusual growth rate, still undecided at 1e8 (and run to 1e9).
deep1e9 = {}
for line in open(os.path.join(OUT, "flagged_1e9.txt")) if os.path.exists(os.path.join(OUT, "flagged_1e9.txt")) else []:
    tm, rest = line.split(" ", 1)
    deep1e9[tm] = rest.strip()
odd = {r[0]: r for r in tsv("odd100m.tsv")}
NOTES = {
    "1RB1RB2LB4LA---_2LA4LB3RB1LA2RB": "가장 '들쭉날쭉'한 후보. 오른쪽 끝이 계단처럼 불규칙하게 자라고, 기록 간격의 변화도 덜 규칙적입니다(novelty 0.32).",
    "1RB0RB---1RB2LA_2LA4RA3LB0RB---": "같은 모양이 점점 크게 되풀이되는 자기유사(프랙탈) 구조. 보통 '중첩 카운터'로 설명되는 유형입니다.",
    "1RB---------2LB_2LB3LA0RB4RB1LB": "격자 무늬가 부채꼴로 퍼집니다. 10억 걸음에서 폭 약 28만 칸으로 가장 넓습니다.",
    "1RB---_0RC1RB_1LC0LD_1RE1LE_0LF1LE_0RB1LF": "6상태 전부 사용. 폭이 매우 느리게(10억 걸음에 2,200칸) 자라며 중간에 성장 속도가 바뀝니다.",
    "1RB---_1LC0LF_1RC0RD_1LE1RD_1LB1RB_0RB1LF": "바로 위 기계와 거의 같은 행동(쌍둥이). 서로 동치일 가능성이 큽니다.",
}
flag_html = []
for tm in [l.strip() for l in open(os.path.join(OUT, "flagged.txt"))]:
    a = img(f"f_{slug(tm)}_early.png", tm, 2000, max_w=500, crop=True)
    b = img(f"f_{slug(tm)}_long.png", tm, 100000000, max_w=500, crop=True)
    r = odd.get(tm)
    meta = f"1억 걸음: 폭 {int(r[3]):,}칸, 성장 지수 {r[6]}" if r else ""
    flag_html.append((tm, a, b, meta, deep1e9.get(tm, ""), NOTES.get(tm, "")))
flag_html.sort(key=lambda x: (x[0] not in NOTES, list(NOTES).index(x[0]) if x[0] in NOTES else 0))

# Real proofs: n-gram CPS results (run_search.sh step 6).
CPS = {r[0]: r for r in tsv("cps6.tsv") + tsv("cps25.tsv")}
cps_ok = {d: count(f"cps{d}.tsv", lambda r: r[1] == "cps_proved") for d in ("6", "25")}
cps_left = {d: count(f"cps{d}.tsv", lambda r: r[1] == "cps_fail") for d in ("6", "25")}
flag_proved = sum(1 for f in flag_html if CPS.get(f[0], ["", ""])[1] == "cps_proved")
cmp_lines = [l for l in open(os.path.join(OUT, "official_compare.txt"))][1:] if os.path.exists(os.path.join(OUT, "official_compare.txt")) else []
left_in_list = sum(1 for l in cmp_lines if "not in list" not in l)
for key, dom in (("6", "BB(6)"), ("25", "BB(2,5)")):
    funnel[dom].append(("n-gram CPS로도 증명 못 한 것", cps_left[key]))

# Bouncer decider on what CPS left (run_search.sh step 6, src/bouncer.py).
BNC = [r for r in tsv("bouncer.tsv")]
dom_of = lambda tm: "6" if len(tm.split("_")) == 6 else "25"  # noqa: E731
bnc_ok = {d: sum(1 for r in BNC if dom_of(r[0]) == d and r[1] == "bouncer_proved") for d in ("6", "25")}
bnc_left = {d: sum(1 for r in BNC if dom_of(r[0]) == d and r[1] != "bouncer_proved") for d in ("6", "25")}
bnc_proofs = [(r[0], r[2], r[5]) for r in BNC if r[1] == "bouncer_proved"]
bnc_test = {}
for l in open(os.path.join(OUT, "test_bouncer.txt")) if os.path.exists(os.path.join(OUT, "test_bouncer.txt")) else []:
    nums = [int(x) for x in re.findall(r"\d+", l.split(":", 1)[-1] if ":" in l else l)]
    if l.startswith("random machines"):
        bnc_test["random"], bnc_test["halting"] = int(re.findall(r"\d+", l)[0]), nums[0]
    elif l.startswith("champion halters"):
        bnc_test["long"], bnc_test["long_bad"] = nums[-2], nums[-1]
    elif l.startswith("halters proved"):
        bnc_test["bad"] = nums[0] + nums[1]
    elif l.startswith("rules audited"):
        bnc_test["rules"], bnc_test["rules_bad"] = nums[0], nums[1]
        bnc_test["skipped"] = nums[3] if len(nums) > 3 else 0
for key, dom in (("6", "BB(6)"), ("25", "BB(2,5)")):
    if BNC:
        funnel[dom].append(("바운서 판정기로도 증명 못 한 것", bnc_left[key]))

# Bouncer section (05) and TL;DR line.
bnc_tldr = bnc_block = ""
if BNC:
    nb = bnc_ok["6"] + bnc_ok["25"]
    nl = bnc_left["6"] + bnc_left["25"]
    bnc_tldr = (f'<li>그래도 남은 {len(BNC)}개에는 <b>바운서 판정기</b>를 직접 만들어 씌웠어요. '
                f'<b>{nb}개</b>를 더 증명했고, 나머지 {nl}개는 2진수 카운터처럼 보이는 기계라 이 방법으로는 안 풀렸어요.</li>\n')
    t = bnc_test
    rows = "".join(f'<li><code>{html.escape(tm)}</code><span>{html.escape(rule)}</span></li>' for tm, k, rule in bnc_proofs)
    bnc_block = f'''<h3>진짜 증명 2: 바운서 판정기</h3>
<p>CPS가 못 푼 {len(BNC)}개 중에는 헤드가 테이프 끝과 끝을 오가며(<b>바운스</b>) 한 번 갈 때마다 테이프가 조금씩 길어지는 기계가 있어요. 이런 기계의 테이프는 <b>'같은 조각이 x번 반복'</b>으로 적으면 매번 같은 모양이 됩니다. 그래서 x를 숫자 대신 <b>문자로 둔 채</b> 기계를 돌려요(기호 시뮬레이션).</p>
<ul>
<li><b>건너뛰기</b>: 헤드가 같은 조각을 같은 상태로 통과하면, 조각 x개를 한 번에 건넙니다. x가 몇이든 맞는 이동이에요.</li>
<li><b>귀납 규칙</b>: 같은 모양이 다시 나오면 개수를 x로 바꿔서, "x가 몇이든 이 모양은 다시 이 모양으로 돌아온다"를 기호로 돌려 증명해요. 한 번 왕복하는 사이 안쪽에서 x번 지그재그하는 부분도 먼저 증명한 규칙으로 한 번에 처리합니다.</li>
<li>개수가 줄지 않고 다시 같은 모양이 되는 규칙이, 실제로 돌려서 도착한 테이프에 맞으면 → 영원히 되풀이 → <b>안 멈춤 증명</b>.</li>
</ul>
<p class="side">아이디어는 bbchallenge의 바운서 판정기와 Shawn Ligocki의 증명 시스템에서 가져왔어요. 휴리스틱과 달리 모든 단계가 'x가 몇이든 참'인 이동이라서, 맞으면 증명이고 틀릴 수는 없어요. 대신 못 푸는 기계가 남을 수 있죠.</p>
<div class="result wide">
  <div><b>{nb} / {len(BNC)}</b><span>바운서 판정기로 안 멈춤 증명 (BB(6) {bnc_ok["6"]}개 · BB(2,5) {bnc_ok["25"]}개)</span></div>
  <div><b>{t.get("bad", 0) + t.get("long_bad", 0)} / {t.get("halting", 0) + t.get("long", 0):,}</b><span>실제로 멈추는 기계(검사용 무작위 기계 + BB(2)~BB(6) 챔피언 {t.get("long", 0)}개)를 잘못 '증명'한 수. 크립티드 3개도 증명되지 않음</span></div>
  <div><b>{t.get("rules_bad", 0)} / {t.get("rules", 0):,}</b><span>증명 중에 만든 규칙에 실제 숫자를 넣어 원래 기계로 다시 돌려 봤을 때 틀린 규칙 수 (테이프가 6천 칸을 넘는 {t.get("skipped", 0):,}개는 건너뜀)</span></div>
</div>
<p>증명된 {nb}개와 마지막 규칙이에요. <code>4^(x)</code>는 '4가 x개', <code>A&gt;</code>는 상태 A로 오른쪽을 보는 헤드, <code>0^∞</code>는 끝없는 빈칸입니다. 예를 들어 맨 위 규칙은 "01 바로 뒤에서 상태 B 헤드가 오른쪽을 보고, 오른쪽에 10이 4+2x개 있으면, 한참 뒤 똑같은 모양에 10이 28+8x개가 된다"는 뜻이에요. 28+8x도 4+2x 꼴이라 규칙이 또 맞고, 개수는 계속 커지니 영원히 반복되죠.</p>
<ul class="proofs wide">{rows}</ul>
<p>남은 {nl}개는 바운서가 아니라, 테이프 한쪽에 <b>자릿수가 불규칙하게 바뀌는 작은 구역</b>이 있는 기계예요(2진수 카운터처럼 보여요). 이런 구역은 '같은 조각 x번'으로 적을 수 없어서 이 방법으로는 안 풀려요. 칸 묶음 크기(1~4칸)와 기호 시뮬레이션 길이를 늘려 봐도 결과가 같았어요.</p>
'''


# ------------------------------------------------------------ HTML
# Research-note layout (approved mock: docs/design-refs/mock/note.html).
E = html.escape


def pic(src, alt=""):
    """Light/dark renders swap with the colour scheme."""
    dark = src.replace("img/", "img/dark/", 1)
    return (f'<picture><source srcset="{dark}" media="(prefers-color-scheme: dark)">'
            f'<img src="{src}" loading="lazy" alt="{E(alt)}"></picture>')


def fig(src, cap="", cls=""):
    """A numbered figure; numbers are filled in page order at the end."""
    return (f'<figure class="fig {cls}"><div class="img">{pic(src, re.sub("<[^>]+>", "", cap))}</div>'
            f'<figcaption><b>그림 @@PL@@.</b> {cap}</figcaption></figure>')


def spark(src, label="폭"):
    """Sparkline of occupied tape width over the run (from the figure's rows)."""
    info = INFO.get(src)
    if not info or not info["extents"]:
        return ""
    ys = info["extents"]
    w, h, top = 110, 18, max(ys) or 1
    pts = " ".join(f"{i * w / (len(ys) - 1):.1f},{h - 2 - (h - 4) * y / top:.1f}" for i, y in enumerate(ys))
    ex, ey = w, h - 2 - (h - 4) * ys[-1] / top
    return (f'<span class="spark" title="걸음에 따른 테이프 폭"><svg viewBox="-2 0 {w + 6} {h}" width="{w + 6}" height="{h}" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="1.2"/>'
            f'<circle cx="{ex}" cy="{ey:.1f}" r="2.4" class="end"/></svg>'
            f'<span class="sv">{label} {ys[-1]:,}칸</span></span>')


def funnel_table(title, rows):
    top = rows[0][1] or 1
    out = [f'<div class="funnel"><p class="ft">{E(title)}</p><table><tbody>']
    for i, (label, n) in enumerate(rows):
        w = max(0.6, 100 * (n / top) ** 0.35) if n else 0
        out.append(f'<tr class="{"last" if i == len(rows) - 1 else ""}"><td>{E(label)}</td><td class="num">{n:,}</td>'
                   f'<td class="bar"><span style="width:{w:.1f}%"></span></td></tr>')
    out.append("</tbody></table></div>")
    return "\n".join(out)


CRYPTID_SHORT = {
    "Antihydra (BB(6))": ("Antihydra", "BB(6)", "⌊3n/2⌋+2를 되풀이하며 홀짝을 세는 기계. 콜라츠 문제와 닮아 아무도 멈출지 증명하지 못했어요. 2024년 6월 발견."),
    "Hydra (BB(2,5))": ("Hydra", "BB(2,5)", "Antihydra의 원조. 상태 2개, 기호 5개로 같은 종류의 난제를 품고 있어요. 2024년 4월 발견."),
    "Bigfoot (BB(3,3))": ("Bigfoot", "BB(3,3)", "이 기계 때문에 BB(3,3)을 끝내려면 수학 난제 하나를 먼저 풀어야 해요. 2023년 10월 발견."),
}
parts = []
for name, tm, note, a, b in cryptid_html:
    nm, dom, txt = CRYPTID_SHORT.get(name, (name, "", note))
    parts.append(f'<figure class="card"><div class="pic">{pic(b, nm + " 3천만 걸음")}</div>'
                 f'<h3>{E(nm)} <small>{E(dom)}</small></h3><p>{E(txt)}</p>'
                 f'<p class="tm"><code>{E(tm)}</code></p><p class="tm">{spark(b)}</p></figure>')
cryptid_block = '<div class="cards wide">' + "\n".join(parts) + "</div>"

parts = []
for title, desc, items in class_html:
    thumbs = "".join(f'<div class="th">{pic(src, tm)}</div>' for tm, src in items)
    parts.append(f'<div class="cls"><div class="cl-txt"><h3>{E(title)}</h3><p>{E(desc)}</p></div><div class="thumbs">{thumbs}</div></div>')
class_block = '<div class="classes wide">' + "\n".join(parts) + "</div>"

parts = []
for tm, a, b, meta, d9, note in flag_html:
    d9txt = ""
    if d9:
        w = d9.split("width=")[-1]
        d9txt = f"10억 걸음: 안 멈춤, 폭 {int(w):,}칸" if d9.startswith("limit") else E(d9)
    c = CPS.get(tm)
    cpstxt = f'<p class="proof">✓ 안 멈춤 증명 · n-gram CPS (n={c[2]}, 블록 {c[4]}칸)</p>' if c and c[1] == "cps_proved" else ""
    parts.append(f'<figure class="cand"><div class="pics"><div>{pic(a, "처음 2,000걸음")}<span>처음 2,000걸음</span></div>'
                 f'<div>{pic(b, "1억 걸음 전체")}<span>1억 걸음</span></div></div>'
                 f'<p class="tm"><code>{E(tm)}</code></p><p class="tm">{spark(b)}</p>'
                 f'{cpstxt}<p class="meta">{E(meta)}<br>{d9txt}</p>{"<p>" + E(note) + "</p>" if note else ""}</figure>')
flag_block = '<div class="cands wide">' + "\n".join(parts) + "</div>"

b6, b25 = best.get("BB(6,2)", (0, "")), best.get("BB(2,5)", (0, ""))
n_samples = totals["BB(6,2)"]["samples"] + totals["BB(2,5)"]["samples"]
n_full = count("full6.tsv", lambda r: r[5] == "irregular") + count("full25.tsv", lambda r: r[5] == "irregular")

CSS = """
:root {
  --bg: #ffffff; --fg: #141414; --fg2: #3d3d3d; --muted: #8a8a8a; --line: #e8e8e8; --soft: #f7f7f5;
  --accent: #ff5a1f; --hl: #ffe6d9; --blue: #635bff; --hlb: #e7e5ff; --cell0: #f1f1f1; --cell1: #141414;
  --sans: "Pretendard Variable", Pretendard, -apple-system, "Apple SD Gothic Neo", system-ui, sans-serif;
  --mono: "Geist Mono", ui-monospace, Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --bg: #0d0d0d; --fg: #ececec; --fg2: #c4c4c4; --muted: #8a8a8a; --line: #242424; --soft: #151515;
    --hl: #3a2216; --hlb: #23214a; --cell0: #222222; --cell1: #ececec; }
}
:root[data-theme="dark"] { --bg: #0d0d0d; --fg: #ececec; --fg2: #c4c4c4; --muted: #8a8a8a; --line: #242424; --soft: #151515;
  --hl: #3a2216; --hlb: #23214a; --cell0: #222222; --cell1: #ececec; }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 24px; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 17px/1.8 var(--sans); -webkit-font-smoothing: antialiased; word-break: keep-all; }
a { color: var(--fg); text-decoration-color: var(--line); text-underline-offset: 3px; }
.page { max-width: 1180px; margin: 0 auto; padding: 0 28px 120px; display: grid; grid-template-columns: 190px minmax(0, 660px) 230px; gap: 0 44px; }
.page > * { grid-column: 2; min-width: 0; }
.page > .wide { grid-column: 2 / 4; }
.top { grid-column: 1 / -1; display: flex; justify-content: space-between; align-items: center; height: 60px; border-bottom: 1px solid var(--line);
  font-size: .88rem; color: var(--muted); margin-bottom: 64px; }
.top b { color: var(--fg); font-weight: 650; }
.top a { color: inherit; text-decoration: none; margin-left: 20px; }
.toc { grid-column: 1; grid-row: 2 / span 200; position: sticky; top: 28px; align-self: start; font-size: .86rem; line-height: 1.5; padding-top: 6px; }
.toc p { font: 500 .72rem var(--mono); color: var(--muted); margin: 0 0 12px; letter-spacing: .04em; }
.toc a { display: flex; gap: 10px; color: var(--muted); text-decoration: none; padding: 5px 0; }
.toc a span { font-family: var(--mono); font-size: .75rem; min-width: 1.4em; }
.toc a.on { color: var(--fg); font-weight: 600; }
.kicker { font: 500 .78rem var(--mono); color: var(--accent); margin: 0 0 14px; letter-spacing: .02em; }
h1 { font-size: 2.6rem; line-height: 1.18; letter-spacing: -.035em; margin: 0 0 14px; font-weight: 700; }
.dek { font-size: 1.18rem; color: var(--fg2); margin: 0 0 22px; line-height: 1.6; }
.meta-row { display: flex; flex-wrap: wrap; gap: 6px 18px; font: .8rem var(--mono); color: var(--muted); padding-bottom: 28px; border-bottom: 1px solid var(--line); margin: 0; }
.tldr { margin: 32px 0 8px; padding: 20px 24px; background: var(--soft); border-radius: 12px; }
.tldr p { margin: 0 0 8px; font: 600 .78rem var(--mono); color: var(--muted); letter-spacing: .04em; }
.tldr ul { margin: 0; padding-left: 1.1em; color: var(--fg2); font-size: .98rem; line-height: 1.7; }
.tldr b { color: var(--fg); }
h2 { font-size: 1.7rem; letter-spacing: -.03em; line-height: 1.3; margin: 96px 0 8px; font-weight: 700; }
h2 small { display: block; font: 500 .78rem var(--mono); color: var(--muted); letter-spacing: .02em; margin-bottom: 10px; }
h3 { font-size: 1.15rem; letter-spacing: -.02em; margin: 40px 0 4px; font-weight: 700; }
p { color: var(--fg2); margin: 16px 0; }
p b, li b { color: var(--fg); }
ul { color: var(--fg2); padding-left: 1.2em; }
li { margin: 6px 0; }
mark { background: var(--hl); color: var(--fg); padding: 1px 4px; border-radius: 4px; }
mark.b { background: var(--hlb); }
code { font: .84em var(--mono); background: var(--soft); border: 1px solid var(--line); padding: 1px 5px; border-radius: 5px; word-break: break-all; }
.side { grid-column: 3; font-size: .82rem; line-height: 1.6; color: var(--muted); margin: 0; align-self: start; border-left: 2px solid var(--line); padding-left: 14px; }
.side b { color: var(--fg2); }
.warn { border-left: 3px solid var(--accent); background: var(--soft); border-radius: 0 10px 10px 0; padding: 14px 18px; font-size: .95rem; color: var(--fg2); }
/* widgets */
.widget { margin: 28px 0; border: 1px solid var(--line); border-radius: 14px; padding: 20px; background: var(--bg); }
.w-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 16px; font: 500 .75rem var(--mono); color: var(--muted); }
.w-head b { color: var(--fg); font-family: var(--sans); font-size: .92rem; white-space: nowrap; }
.w-head span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tape { display: grid; grid-template-columns: repeat(13, 1fr); gap: 4px; position: relative; padding-top: 30px; }
.tape span { aspect-ratio: 1; border-radius: 6px; background: var(--cell0); display: flex; align-items: center; justify-content: center;
  font: 500 .8rem var(--mono); color: var(--muted); transition: background .2s; }
.tape span.one { background: var(--cell1); color: var(--bg); }
.tape span.hd { box-shadow: 0 0 0 2px var(--accent); }
.tape .badge { position: absolute; top: 0; height: 22px; padding: 0 8px; border-radius: 6px; background: var(--accent); color: #fff;
  font: 600 .75rem/22px var(--mono); transform: translateX(-50%); white-space: nowrap; font-style: normal; }
.rules { display: grid; grid-template-columns: auto 1fr 1fr; gap: 6px; margin-top: 18px; font: .82rem var(--mono); align-items: center; }
.rules div { padding: 8px 10px; border-radius: 8px; background: var(--soft); text-align: center; color: var(--fg2); }
.rules .h { background: none; color: var(--muted); padding: 0 10px; font-size: .72rem; }
.rules .on { background: var(--accent); color: #fff; }
.say { margin: 16px 0 0; min-height: 3.4em; font-size: .95rem; color: var(--fg); }
.say .n { font-family: var(--mono); color: var(--muted); margin-right: 8px; }
.ctrl { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; align-items: center; }
.ctrl button, .ctrl select, .stepper button, .stepper select, .stepper input[type=text], .stepper #st-tm {
  font: 600 .85rem var(--sans); height: 36px; padding: 0 14px; border-radius: 999px; border: 1px solid var(--line); background: var(--bg); color: var(--fg); cursor: pointer; }
.ctrl button.pri, .stepper button.primary { background: var(--fg); color: var(--bg); border-color: var(--fg); }
button:disabled { opacity: .4; cursor: default; }
.ctrl .count { margin-left: auto; font: .8rem var(--mono); color: var(--muted); }
.widget canvas { width: 100%; height: auto; display: block; border-radius: 8px; background: var(--soft); image-rendering: pixelated; }
/* full simulator */
.stepper { margin: 28px 0; border: 1px solid var(--line); border-radius: 14px; padding: 20px; }
.st-top { display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center; font-size: .88rem; color: var(--muted); }
.st-top label { display: flex; align-items: center; gap: 8px; }
.st-in { display: flex; flex: 1 1 300px; gap: 6px; }
.stepper #st-tm { flex: 1; min-width: 0; font: .78rem var(--mono); border-radius: 10px; cursor: text; }
.st-err { color: var(--accent); font-size: .85rem; margin: 6px 0; min-height: 1.2em; }
.st-grid { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr); gap: 20px; align-items: start; }
.stepper .frame { border-radius: 10px; overflow: hidden; background: var(--soft); }
.stepper canvas { width: 100%; height: auto; display: block; image-rendering: pixelated; }
.st-cap { font-size: .78rem; color: var(--muted); margin: 8px 0 0; }
.st-tape { margin-bottom: 12px; }
.st-hlabel { font: .75rem var(--mono); color: var(--muted); }
.st-hlabel b { color: var(--accent); margin-left: 4px; }
.st-strip { display: grid; grid-template-columns: repeat(21, 1fr); gap: 2px; margin-top: 6px; }
.st-strip span { aspect-ratio: 1; display: flex; align-items: center; justify-content: center; font: 500 .58rem var(--mono); color: var(--bg); border-radius: 3px; }
.st-strip span.hd { box-shadow: 0 0 0 2px var(--accent); position: relative; z-index: 1; }
.st-rules { width: 100%; border-collapse: separate; border-spacing: 4px; font: .78rem var(--mono); }
.st-rules th { color: var(--muted); font-weight: 500; font-size: .7rem; }
.st-rules td { text-align: center; background: var(--soft); border-radius: 6px; padding: 4px; }
.st-rules td code { background: none; border: 0; padding: 0; }
.st-rules td.on { background: var(--accent); }
.st-rules td.on code { color: #fff; }
.st-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 12px 0 4px; }
.st-stats div { border-top: 1px solid var(--line); padding-top: 6px; }
.st-stats dt { font-size: .72rem; color: var(--muted); }
.st-stats dd { margin: 0; font: 600 1rem var(--sans); font-variant-numeric: tabular-nums; }
.st-status { font-size: .88rem; margin: 6px 0 0; color: var(--fg2); }
.st-status[data-s="halt"] { color: var(--blue); font-weight: 600; }
.st-status[data-s="undef"], .st-status[data-s="edge"] { color: var(--accent); }
.st-ctrl { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 14px; }
.st-speed { display: flex; align-items: center; gap: 8px; font-size: .82rem; color: var(--muted); flex: 1 1 260px; }
.st-speed input { flex: 1; accent-color: var(--accent); }
/* figures */
.fig { margin: 32px 0; }
.fig .img { background: var(--bg); border: 1px solid var(--line); border-radius: 14px; padding: 24px; }
.fig img { width: 100%; display: block; image-rendering: pixelated; max-height: 560px; object-fit: contain; }
.fig figcaption { font-size: .86rem; color: var(--muted); margin-top: 10px; max-width: 660px; }
.fig figcaption b { color: var(--fg); }
.pair2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.pair2 .fig { margin: 24px 0; }
.pair2 .fig .img { padding: 16px; }
.pair2 .fig img { max-height: 280px; }
/* tables */
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th, td { border-bottom: 1px solid var(--line); padding: 10px 8px; text-align: left; vertical-align: top; }
th { font: 500 .75rem var(--mono); color: var(--muted); }
td.num { text-align: right; font: .85rem var(--mono); font-variant-numeric: tabular-nums; white-space: nowrap; }
.funnels { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 28px 0 8px; }
.funnel { border: 1px solid var(--line); border-radius: 14px; padding: 18px 18px 10px; }
.funnel .ft { margin: 0 0 6px; font-weight: 650; color: var(--fg); font-size: .95rem; }
.funnel td { border: 0; padding: 4px 6px; font-size: .82rem; color: var(--fg2); }
.funnel td.bar { width: 30%; vertical-align: middle; }
.funnel td.bar span { display: block; height: 6px; border-radius: 99px; background: var(--fg); min-width: 6px; }
.funnel tr.last td { color: var(--fg); font-weight: 650; }
.funnel tr.last td.bar span { background: var(--accent); }
.note { font-size: .86rem; color: var(--muted); }
/* cards */
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 32px 0; }
.card { margin: 0; }
.card .pic { border: 1px solid var(--line); border-radius: 14px; padding: 18px; aspect-ratio: 4 / 3; display: flex; align-items: flex-end; justify-content: center; }
.card .pic img, .cand img, .th img { width: 100%; height: 100%; object-fit: contain; object-position: bottom; display: block; image-rendering: pixelated; }
.card .pic picture { width: 100%; height: 100%; display: block; }
.card h3 { margin: 16px 0 2px; display: flex; align-items: baseline; gap: 8px; }
.card h3 small { font: 500 .74rem var(--mono); color: var(--muted); }
.card p { font-size: .92rem; margin: 6px 0; }
.tm { margin: 6px 0; display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: center; }
.tm code { font-size: .72rem; color: var(--muted); }
.spark { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); white-space: nowrap; }
.spark svg { overflow: visible; color: var(--fg); }
.spark .end { fill: var(--accent); }
.spark .sv { font: .74rem var(--mono); }
.classes { margin: 28px 0; border-top: 1px solid var(--line); }
.cls { display: grid; grid-template-columns: 260px 1fr; gap: 24px; padding: 20px 0; border-bottom: 1px solid var(--line); align-items: center; }
.cls h3 { margin: 0 0 4px; font-size: 1rem; }
.cls p { margin: 0; font-size: .88rem; }
.thumbs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.th { aspect-ratio: 4 / 3; border: 1px solid var(--line); border-radius: 10px; padding: 8px; }
.th picture { width: 100%; height: 100%; display: block; }
.cands { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px 24px; margin: 28px 0; }
.cand { margin: 0; border: 1px solid var(--line); border-radius: 14px; padding: 16px; }
.cand .pics { display: grid; grid-template-columns: 1fr 2fr; gap: 10px; }
.cand .pics > div { aspect-ratio: 3 / 4; background: var(--bg); display: flex; flex-direction: column; }
.cand .pics > div:last-child { aspect-ratio: auto; }
.cand picture { flex: 1; min-height: 0; display: block; }
.cand .pics span { font: .68rem var(--mono); color: var(--muted); margin-top: 4px; }
.cand .meta { font: .74rem/1.6 var(--mono); color: var(--muted); margin: 6px 0; }
.proof { display: inline-block; font: 600 .76rem var(--sans); color: var(--blue); background: var(--hlb); border-radius: 6px; padding: 2px 8px; margin: 8px 0 2px; }
.result { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 24px 0; }
.result div { border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; }
.result b { display: block; font-size: 1.5rem; letter-spacing: -.03em; color: var(--fg); font-variant-numeric: tabular-nums; }
.result span { font-size: .82rem; color: var(--muted); line-height: 1.5; display: block; }
.cand p { font-size: .88rem; margin: 6px 0 0; }
.proofs { list-style: none; padding: 0; margin: 20px 0; border-top: 1px solid var(--line); }
.proofs li { padding: 10px 0; border-bottom: 1px solid var(--line); display: flex; flex-direction: column; gap: 4px; }
.proofs code { font-size: .72rem; color: var(--muted); overflow-wrap: anywhere; }
.proofs span { font: .8rem/1.6 var(--mono); overflow-wrap: anywhere; }
.sources li { font-size: .9rem; }
@media (max-width: 1080px) {
  .page { grid-template-columns: minmax(0, 1fr); max-width: 720px; }
  .page > *, .page > .wide, .side, .toc { grid-column: 1; }
  .toc { display: none; }
  .side { border-left: 0; padding: 10px 14px; background: var(--soft); border-radius: 10px; margin: 4px 0 8px; }
  .top { margin-bottom: 40px; }
}
@media (max-width: 640px) {
  .page { padding: 0 18px 80px; }
  h1 { font-size: 2rem; } body { font-size: 16px; }
  .top a:not(:first-child) { display: none; }
  .tape { grid-template-columns: repeat(9, 1fr); }
  .tape span:nth-child(-n+2), .tape span:nth-last-child(-n+3) { display: none; }
  .widget, .stepper { padding: 14px; }
  .fig .img { padding: 12px; }
  .pair2, .funnels, .cards, .cands, .result { grid-template-columns: 1fr; }
  .st-grid { grid-template-columns: 1fr; }
  .cls { grid-template-columns: 1fr; gap: 12px; }
}
"""

TOC = [("s01", "01", "튜링 기계"), ("s02", "02", "직접 돌려 보기"), ("s03", "03", "BB(n)"), ("s04", "04", "크립티드"),
       ("s05", "05", "무작위 탐색"), ("s06", "06", "눈에 띄던 후보"), ("sources", "—", "출처")]
toc_html = "".join(f'<a href="#{i}"><span>{n}</span>{E(t)}</a>' for i, n, t in TOC)

PAGE = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Busy Beaver 탐험기</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="page">
<div class="top"><span><b>Busy Beaver</b> 연구 노트</span><span><a href="#s02">시뮬레이터</a><a href="#s05">탐색 결과</a><a href="#sources">출처</a></span></div>
<nav class="toc" aria-label="목차"><p>목차</p>{toc_html}</nav>

<p class="kicker">연구 노트 · 2026년 10월 20일</p>
<h1>Busy Beaver 탐험기</h1>
<p class="dek">멈추는 작은 기계는 얼마나 오래 일할 수 있을까. 기계를 직접 한 걸음씩 돌려 보면서, {n_samples // 10000:,}만 개를 무작위로 시험한 결과까지 따라가 봅니다.</p>
<p class="meta-row"><span>읽는 데 약 10분</span><span>위젯 2개 · 시뮬레이터 1개</span><span>C·JS 시뮬레이터로 BB(5) 재현</span></p>
<div class="tldr"><p>요약</p><ul>
<li><b>BB(5) = 47,176,870걸음.</b> 2024년에 증명됐고, 이 노트의 시뮬레이터로 똑같이 재현했어요.</li>
<li>무작위로 만든 기계 <b>{n_samples // 10000:,}만 개</b> 중 <b>{n_full:,}개</b>는 간단한 판정기로 결론이 안 났어요.</li>
<li>직접 만든 <b>n-gram CPS 판정기</b>로 그중 <b>{cps_ok["6"] + cps_ok["25"]:,}개</b>가 '절대 안 멈춤'을 증명했어요. 눈에 띄던 후보 {len(flag_html)}개도 {"모두" if flag_proved == len(flag_html) else str(flag_proved) + "개가"} 증명돼서, 새 크립티드는 없었어요.</li>
{bnc_tldr}</ul></div>

<h2 id="s01"><small>01</small>튜링 기계는 이렇게 움직여요</h2>
<p>칸이 끝없이 이어진 <mark class="b">테이프</mark>가 있고, 그 위에서 <mark>헤드</mark> 하나가 한 칸씩 움직입니다. 헤드는 지금 자기 <b>상태</b>(A, B, …)와 발밑 칸의 기호를 보고, 규칙표에서 딱 한 줄을 골라 따라요. 규칙 한 줄은 <b>① 기호를 쓰고 ② 왼쪽이나 오른쪽으로 한 칸 가고 ③ 상태를 바꾸는</b> 일을 합니다.</p>
<p class="side"><b>표기법</b><br><code>1RB</code> = 1을 쓰고, 오른쪽(R)으로 한 칸, 상태 B로. <code>1RZ</code>의 Z는 멈춤. 규칙표 전체는 <code>1RB1LB_1LA1RZ</code>처럼 한 줄로 씁니다(bbchallenge 표준 형식).</p>
<div class="widget" id="w1">
  <div class="w-head"><b>한 걸음씩 따라가기</b><span>BB(2) 챔피언 · 1RB1LB_1LA1RZ</span></div>
  <div class="tape" id="w1-tape"></div>
  <div class="rules" id="w1-rules"></div>
  <p class="say" id="w1-say"></p>
  <div class="ctrl"><button type="button" class="pri" id="w1-step">한 걸음 →</button><button type="button" id="w1-reset">처음으로</button><span class="count" id="w1-count"></span></div>
</div>
<p>여섯 걸음 만에 멈추죠. 상태가 2개인 기계 중에 <b>멈추면서</b> 이보다 오래 일하는 기계는 없습니다. 그래서 BB(2) = 6이에요. 언제나 상태 A, 전부 0인 테이프에서 시작하고, 멈추는 걸음도 1걸음으로 셉니다.</p>

<h3>걸음을 쌓으면 그림이 돼요</h3>
<p>매 걸음의 테이프를 한 줄로 찍고, 위에서 아래로 쌓으면 기계의 일생이 한 장의 그림이 됩니다. 이런 그림을 <b>시공간 다이어그램</b>이라고 불러요. 기계를 바꿔 가며 재생해 보세요.</p>
<p class="side">한 줄 = 한 순간의 테이프. <mark>주황</mark> 칸이 그때 헤드가 있던 자리예요. 아주 긴 실행은 여러 칸을 한 점으로 줄여 그리고, 0이 많이 섞인 곳일수록 흐리게 칠합니다.</p>
<div class="widget" id="w2">
  <div class="w-head"><b>시공간 다이어그램 만들기</b><span id="w2-name"></span></div>
  <canvas id="w2-cv" width="440" height="220" aria-label="시공간 다이어그램"></canvas>
  <div class="ctrl"><select id="w2-sel" aria-label="기계"><option value="0">BB(2) · 6걸음</option><option value="1">BB(3) · 21걸음</option><option value="2" selected>BB(4) · 107걸음</option></select>
    <button type="button" class="pri" id="w2-play">▶ 재생</button><button type="button" id="w2-reset">처음으로</button><span class="count" id="w2-count"></span></div>
</div>
<p>상태가 5개만 돼도 이야기가 완전히 달라집니다. BB(5) 챔피언은 <b>47,176,870걸음</b>을 일하고 멈춰요. 같은 방식으로 그리면 아래처럼 됩니다.</p>
{fig(pics["bb5_long"], f'BB(5) 챔피언 <code>{BB5}</code>의 실행 전체. 테이프 폭이 12,289칸까지 넓어졌다가 멈춥니다. 다음 장의 시뮬레이터에서 직접 끝까지 돌려 볼 수 있어요.', "wide")}

<h2 id="s02"><small>02</small>직접 돌려 보기</h2>
<p>아래 시뮬레이터는 위 위젯과 같은 일을 훨씬 빨리 합니다. 속도를 끝까지 올리면 BB(5) 챔피언도 브라우저에서 끝까지(47,176,870걸음) 돌아가요. 크립티드나 직접 만든 규칙 문자열도 넣어 보세요.</p>
<p class="side">이 시뮬레이터의 결과는 C 시뮬레이터(<code>./bb run</code>)와 걸음 수·남은 1의 개수·테이프 폭까지 똑같은지 검사했습니다.</p>
<div id="stepper" class="stepper wide">
  <div class="st-top">
    <label>기계 <select id="st-preset"></select></label>
    <span class="st-in"><input id="st-tm" spellcheck="false" autocomplete="off" aria-label="규칙 문자열"><button id="st-load" type="button">불러오기</button></span>
  </div>
  <p id="st-err" class="st-err" role="alert"></p>
  <div class="st-grid">
    <div><div class="frame"><canvas width="520" height="360" aria-label="시공간 다이어그램"></canvas></div><p class="st-cap" id="st-rowinfo"></p></div>
    <div>
      <div class="st-tape"><span class="st-hlabel">헤드 · 상태 <b id="st-state">A</b></span><div id="st-strip" class="st-strip"></div></div>
      <div class="scroll"><table id="st-rules" class="st-rules"></table></div>
      <dl class="st-stats"><div><dt>걸음</dt><dd id="st-steps">0</dd></div><div><dt>0 아닌 칸</dt><dd id="st-nz">0</dd></div><div><dt>테이프 폭</dt><dd id="st-width">1</dd></div></dl>
      <p class="st-status" id="st-status"></p>
    </div>
  </div>
  <div class="st-ctrl">
    <button id="st-play" type="button" class="primary">▶ 실행</button><button id="st-step" type="button">한 걸음</button><button id="st-reset" type="button">처음으로</button>
    <label class="st-speed">속도 <input id="st-speed" type="range" min="0" max="8" value="2"> <span id="st-speed-lbl"></span></label>
  </div>
</div>

<h2 id="s03"><small>03</small>Busy Beaver 수 BB(n)</h2>
<p>상태가 n개인 기계 중 <b>멈추는 기계</b>가 일할 수 있는 최대 걸음 수가 BB(n)입니다. 기호를 m개 쓰면 BB(n, m). 어려운 점은 아직 안 멈춘 기계가 <b>영원히 안 멈춘다는 것</b>을 하나하나 증명해야 한다는 거예요. 이걸 모든 기계에 대해 판정하는 프로그램은 존재할 수 없어서(정지 문제), n이 조금만 커져도 BB(n)은 증명이 거의 불가능해집니다.</p>
<p class="side"><b>10↑↑4</b>는 10의 10제곱의 10제곱의 10제곱처럼 지수를 탑으로 쌓은 수예요. 10↑↑10↑↑10↑↑8은 그 탑의 높이가 또 탑입니다.</p>
<div class="scroll wide"><table>
<tr><th>영역</th><th>값 / 현재 하한</th><th>상태</th></tr>
<tr><td>BB(2), BB(3), BB(4)</td><td class="num">6, 21, 107</td><td>해결 (1960~80년대)</td></tr>
<tr><td><b>BB(5)</b></td><td class="num"><b>47,176,870</b></td><td><b>해결 (2024년 6월).</b> 챔피언은 1을 4,098개 남김. Coq(Rocq) 증명 보조기로 5상태 기계 181,385,789개를 전부 판정.</td></tr>
<tr><td>BB(2,4)</td><td class="num">3,932,964</td><td>해결 (BB(5) 논문에서 함께)</td></tr>
<tr><td>BB(6)</td><td class="num">&gt; 10↑↑10↑↑10↑↑8</td><td>미해결. 2025년 6월 mxdys가 찾은 챔피언 <code>1RB1RA_1RC1RZ_1LD0RF_1RA0LE_0LD1RC_1RA0RE</code>. 판정 안 된 기계 663개(동치 제외, 2026-10-16 기준). Antihydra 등 크립티드 존재.</td></tr>
<tr><td>BB(2,5)</td><td class="num">&gt; 10↑↑4</td><td>미해결. 챔피언 Daniel Yuan (2024년 6월). 공식 holdout 59개(2026-10-09 기준). 크립티드 Hydra.</td></tr>
<tr><td>BB(3,3)</td><td class="num">≥ 119,112,334,170,342,541</td><td>미해결. 챔피언 Ligocki 부부 (2007). 남은 holdout 6개(실질 4개). 크립티드 Bigfoot.</td></tr>
</table></div>
<p>이 노트의 C 시뮬레이터로 BB(5) 챔피언을 돌리면 <b>정확히 47,176,870걸음</b>에 멈추고 1이 <b>4,098개</b> 남습니다(약 0.3초). BB(2)=6, BB(3)=21, BB(4)=107, BB(2,4)=3,932,964도 모두 일치했어요.</p>

<h2 id="s04"><small>04</small>크립티드: 멈출지 아무도 모르는 기계</h2>
<p>몇몇 작은 기계는 분석해 보면 <b>콜라츠 문제(3n+1 문제)와 닮은 수학 난제</b>로 바뀝니다. bbchallenge에서는 이런 기계를 <b>크립티드</b>라고 불러요. 크립티드가 하나라도 있으면, 그 영역의 BB 값은 그 난제를 풀기 전까지 확정할 수 없습니다.</p>
{cryptid_block}
<p class="note">그림: 각 기계의 3천만 걸음. 위에서 아래로 시간, 가로는 테이프. 작은 선은 걸음에 따른 테이프 폭이에요.</p>

<h2 id="s05"><small>05</small>무작위로 기계를 만들어 시험해 봤어요</h2>
<p>BB(6)과 BB(2,5)는 기계가 너무 많아서 전부 돌릴 수 없어요. 그래서 <b>무작위로 기계를 만들어</b> 돌렸습니다. 규칙을 미리 다 정하지 않고, 정해지지 않은 규칙(<code>---</code>)을 만나면 그때 무작위로 채웠어요. 그리고 각 기계에 <b>판정기</b>를 씌웠습니다.</p>
<ul>
<li><b>순환</b>: 테이프·헤드·상태가 예전과 똑같아지면 영원히 반복 → 안 멈춤(증명).</li>
<li><b>평행이동 순환</b>: 같은 무늬가 옆으로 옮겨 가며 반복 → 안 멈춤(증명).</li>
<li><b>바운서·카운터 검사</b>: 테이프 끝 기록 시각이 규칙적으로 늘어나는지 보는 휴리스틱. 증명이 아니라 분류 표시예요.</li>
<li><b>걸음 제한</b>: 10만 걸음 안에 판정이 안 되면 holdout으로 남깁니다.</li>
</ul>
<p class="side">상태를 5개 이하만 쓰는 기계는 사실상 5상태 기계라서, 이미 전부 판정된 BB(5) 영역이에요. 그래서 마지막에 '전부 쓰는 것'만 남겼습니다.</p>
<div class="funnels wide">{funnel_table(f"BB(6) · 무작위 기계 {totals['BB(6,2)']['samples']:,}개", funnel["BB(6)"])}{funnel_table(f"BB(2,5) · 무작위 기계 {totals['BB(2,5)']['samples']:,}개", funnel["BB(2,5)"])}</div>
<p class="note">막대는 작은 수도 보이도록 압축한 눈금이에요(정비례 아님). 찾은 가장 오래 걸린 멈춤 기계: BB(6) {b6[0]:,}걸음, BB(2,5) {b25[0]:,}걸음. 챔피언과는 비교도 안 돼요. 좋은 기계는 정말 드뭅니다.</p>
<p>같은 방법으로 Antihydra·Hydra·Bigfoot을 검사하면 모두 '불규칙 holdout'으로 남아요. 판정기가 크립티드를 잘못 '해결'하지 않는다는 확인입니다.</p>

<h3>진짜 증명: n-gram CPS</h3>
<p>위 판정기로 결론이 안 난 {n_full:,}개에 더 강한 판정기를 직접 만들어 씌웠어요. BB(5) 증명에도 쓰인 <b>n-gram CPS</b>(Closed Position Set)예요. 헤드 양옆의 n칸만 기억하는 대신, 테이프에 나타날 수 있는 n칸 조각을 <b>넉넉하게 모두</b> 모아 두고 더 늘어나지 않을 때까지 넓힙니다. 그렇게 닫힌 집합 안에서 멈춤 규칙에 닿는 경우가 하나도 없으면, 실제 기계도 절대 멈추지 않아요.</p>
<p class="side">칸 하나씩이 아니라 <b>칸 k개를 한 기호로 묶은 블록 기계</b> 위에서도 돌려요. 2진수 세기처럼 정확한 개수가 필요한 기계는 이렇게 해야 풀립니다.</p>
<div class="result wide">
  <div><b>{cps_ok["6"] + cps_ok["25"]:,} / {n_full:,}</b><span>안 멈춤 증명 (BB(6) {cps_ok["6"]}개 · BB(2,5) {cps_ok["25"]}개)</span></div>
  <div><b>0 / 14,149</b><span>검사용 무작위 기계 3만 개 중 실제로 멈추는 기계를 잘못 '증명'한 수</span></div>
  <div><b>{cps_left["6"] + cps_left["25"]}개</b><span>남은 기계. 그중 BB(2,5) {cps_left["25"]}개를 위키의 공식 미해결 목록과 동작으로 맞춰 보니 겹치는 기계 {left_in_list}개</span></div>
</div>
<p>남은 기계는 대부분 테이프 폭이 √걸음 속도로 자라요. 공식 목록에 없다는 건 bbchallenge의 더 강한 판정기로 이미 풀렸다는 뜻이라, 이것도 새 발견은 아닙니다. 공식 목록 비교는 BB(2,5)만 했어요. BB(6) 남은 {cps_left["6"]}개는 공식 목록 파일과 아직 맞춰 보지 않았어요.</p>
{bnc_block}
<h3>남은 기계들은 어떻게 생겼나</h3>
<p>테이프 폭이 걸음 수에 따라 어떻게 자라는지(폭 ∝ 걸음<sup>지수</sup>)로 무리를 나눴어요. 그림은 각 기계의 처음 2,000걸음입니다.</p>
{class_block}

<h2 id="s06"><small>06</small>눈에 띄던 후보, 모두 안 멈춤</h2>
<p class="warn"><b>결론: 새 크립티드가 아니었어요.</b> 아래 기계들은 처음 판정기로는 결론이 안 났고, 성장 속도가 흔한 무리에서 벗어나 '이상해 보인다'고 표시했던 것들이에요. 10억 걸음까지 돌려도 멈추지 않았는데, 그건 증명이 아니었죠. 이번에 만든 n-gram CPS 판정기로 {flag_proved}/{len(flag_html)}개 모두 <b>절대 멈추지 않는다는 증명</b>이 나왔어요. 멈출지 모르는 '크립티드'와는 정반대인 평범한 기계였던 거예요.</p>
<p>성장 지수는 1천만→1억 걸음 사이 폭 증가로 계산했어요. 파란 표시는 증명에 쓰인 n칸 조각 길이와 블록 크기예요.</p>
{flag_block}

<h2 id="sources"><small>—</small>출처</h2>
<ul class="sources">
<li><a href="https://wiki.bbchallenge.org/wiki/Busy_Beaver_Challenge">bbchallenge wiki — Busy Beaver Challenge</a></li>
<li><a href="https://wiki.bbchallenge.org/wiki/BB(5)">BB(5)</a> · <a href="https://wiki.bbchallenge.org/wiki/BB(6)">BB(6)</a> · <a href="https://wiki.bbchallenge.org/wiki/BB(2,5)">BB(2,5)</a> · <a href="https://wiki.bbchallenge.org/wiki/BB(3,3)">BB(3,3)</a></li>
<li><a href="https://wiki.bbchallenge.org/wiki/Cryptids">Cryptids</a> · <a href="https://wiki.bbchallenge.org/wiki/Antihydra">Antihydra</a></li>
<li><a href="https://wiki.bbchallenge.org/wiki/Standard_Text_Format">Standard Text Format</a> · <a href="https://wiki.bbchallenge.org/wiki/Translated_cycler">Translated cycler</a></li>
<li><a href="https://arxiv.org/abs/2509.12337">bbchallenge Collaboration, "Determination of the fifth Busy Beaver value", arXiv:2509.12337 (2025)</a></li>
</ul>
<p class="note">수치는 2026-10-20에 위 위키에서 확인했어요. holdout 개수 등은 계속 바뀝니다.</p>
</div>
<script src="explainer.js" defer></script>
<script src="stepper.js" defer></script>
</body>
</html>
"""
_n = iter(range(1, 1000))
PAGE = re.sub("@@PL@@", lambda m: str(next(_n)), PAGE)
open(os.path.join(WEB, "index.html"), "w").write(PAGE)
print("wrote web/index.html")
