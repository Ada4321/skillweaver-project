#!/usr/bin/env python3
"""Generate the hero figure: one MCTS iteration loop, drawn and animated.

The figure shows the actual engine — a search tree on the left being grown by
four actors on the right (memory, VLM planner, robot skill, VLM verifier) whose
output lands in the demo dataset. Two iterations play per cycle: the first is
rejected by the verifier, the second is accepted, glows, and is distilled back
into memory.

Everything animates off ONE shared `animation-duration`, with each element's
timing baked into its own keyframe percentages. That is why this is generated:
the phase table below is the single source of truth for ~40 keyframe blocks, and
keeping them consistent by hand is not realistic. To retime the animation, edit
PHASES and re-run:

    python3 tools/make_hero.py

It rewrites the <svg class="field"> block in index.html and the marked hero
block in css/style.css, in place.
"""

import math
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "index.html")
CSS = os.path.join(ROOT, "css", "style.css")

CYCLE = "15s"

# ----------------------------------------------------------------------------
# Geometry
# ----------------------------------------------------------------------------
VB_W, VB_H = 560, 470

TREE = {
    "root": (40, 235),
    "A": (100, 178), "B": (100, 292),
    "A1": (160, 146), "A2": (160, 208), "B1": (160, 266), "B2": (160, 324),
}
N1, N2 = (220, 120), (220, 214)          # added by iteration 1 / 2
BASE_EDGES = [("root", "A"), ("root", "B"), ("A", "A1"),
              ("A", "A2"), ("B", "B1"), ("B", "B2")]

CHIP_X, CHIP_W, CHIP_H = 268, 180, 36
CHIPS = [                                  # (id, y, label, glyph, accent)
    ("memory",   44, "MEMORY",       "db",    "var(--teal)"),
    ("planner", 128, "VLM PLANNER",  "spark", "var(--indigo)"),
    ("robot",   212, "ROBOT SKILL",  "grip",  "var(--amber)"),
    ("verifier", 296, "VLM VERIFIER", "spark", "var(--indigo)"),
]
COL_X = CHIP_X + CHIP_W / 2               # 358 — the column's arrow spine

DECK = (326, 372, 58, 44)                 # front card x, y, w, h

# ----------------------------------------------------------------------------
# Phase table — percentages of one cycle. Two MCTS iterations per cycle.
# ----------------------------------------------------------------------------
PHASES = {
    "select":   [(2, 8),   (44, 50)],
    "retrieve": [(8, 13),  (50, 55)],
    "expand":   [(13, 19), (55, 61)],
    "execute":  [(19, 27), (61, 69)],
    "verify":   [(27, 33), (69, 75)],
    "backprop": [(33, 38), (75, 80)],
    "accept":   [(80, 85)],
    # Both outcomes are distilled: the paper writes a memory after EVERY
    # trajectory — a failure lesson for the rejected branch, a success strategy
    # for the accepted one — so the first iteration gets a distill too.
    "distill":  [(38, 44), (85, 92)],
}
RESET = 94          # everything added during the cycle fades out here


def ph(name, i=None):
    w = PHASES[name]
    return w if i is None else w[i]


# ----------------------------------------------------------------------------
# Path helpers
# ----------------------------------------------------------------------------
def poly(pts):
    return "M" + " L".join(f"{x},{y}" for x, y in pts)


def bez(p0, p1, p2, p3, n=90):
    out = []
    for i in range(n + 1):
        t = i / n
        out.append((
            (1-t)**3*p0[0] + 3*(1-t)**2*t*p1[0] + 3*(1-t)*t**2*p2[0] + t**3*p3[0],
            (1-t)**3*p0[1] + 3*(1-t)**2*t*p1[1] + 3*(1-t)*t**2*p2[1] + t**3*p3[1]))
    return out


def bez_d(p0, p1, p2, p3):
    return (f"M{p0[0]},{p0[1]} C{p1[0]},{p1[1]} {p2[0]},{p2[1]} {p3[0]},{p3[1]}")


def length(pts):
    return sum(math.dist(pts[i], pts[i+1]) for i in range(len(pts) - 1))


def head(prev, tip, size=7.5):
    """Filled triangle at `tip`, pointing along prev -> tip."""
    dx, dy = tip[0] - prev[0], tip[1] - prev[1]
    n = math.hypot(dx, dy) or 1
    ux, uy = dx / n, dy / n
    bx, by = tip[0] - ux * size, tip[1] - uy * size
    w = size * 0.52
    return (f"M{tip[0]:.1f},{tip[1]:.1f} L{bx-uy*w:.1f},{by+ux*w:.1f} "
            f"L{bx+uy*w:.1f},{by-ux*w:.1f} Z")


# ----------------------------------------------------------------------------
# Keyframe emitters. Each returns (css_text, class_name).
# ----------------------------------------------------------------------------
KF = []


def _stops(pairs):
    """Collapse (pct, decls) stops into keyframe text, merging equal percents."""
    merged = {}
    for pct, decl in pairs:
        merged.setdefault(round(pct, 3), []).append(decl)
    out = []
    for pct in sorted(merged):
        out.append(f"  {pct:g}% {{ {' '.join(merged[pct])} }}")
    return "\n".join(out)


def kf_show(cid, windows, on="opacity: 1;", off="opacity: 0;", fade=1.0):
    """Visible during each window, invisible outside, with a short crossfade."""
    s = [(0, off)]
    for a, b in windows:
        s += [(max(0.01, a - fade), off), (a, on), (b, on), (min(99.99, b + fade), off)]
    s.append((100, off))
    KF.append(f"@keyframes sw-{cid} {{\n{_stops(s)}\n}}")
    return f"sw-{cid}"


def kf_hold(cid, appear, fade_in=1.2):
    """Fades in at `appear` and holds until the cycle resets."""
    s = [(0, "opacity: 0;"), (max(0.01, appear - fade_in), "opacity: 0;"),
         (appear, "opacity: 1;"), (RESET, "opacity: 1;"), (100, "opacity: 0;")]
    KF.append(f"@keyframes sw-{cid} {{\n{_stops(s)}\n}}")
    return f"sw-{cid}"


def kf_draw(cid, plen, a, b):
    """Strokes the path on between a% and b%, then holds until reset."""
    s = [(0, f"stroke-dashoffset: {plen:.1f}; opacity: 0;"),
         (max(0.01, a - 0.3), f"stroke-dashoffset: {plen:.1f}; opacity: 0;"),
         (a, f"stroke-dashoffset: {plen:.1f}; opacity: 1;"),
         (b, "stroke-dashoffset: 0; opacity: 1;"),
         (RESET, "stroke-dashoffset: 0; opacity: 1;"),
         (100, "stroke-dashoffset: 0; opacity: 0;")]
    KF.append(f"@keyframes sw-{cid} {{\n{_stops(s)}\n}}")
    return f"sw-{cid}"


def kf_flow(cid, plen, windows, dash=16):
    """A short dash travelling the length of the path — the moving token."""
    far, home = -plen, dash
    s = [(0, f"stroke-dashoffset: {home}; opacity: 0;")]
    for a, b in windows:
        s += [(max(0.01, a - 0.2), f"stroke-dashoffset: {home}; opacity: 0;"),
              (a, f"stroke-dashoffset: {home}; opacity: 1;"),
              (b, f"stroke-dashoffset: {far:.1f}; opacity: 1;"),
              (min(99.99, b + 0.2), f"stroke-dashoffset: {home}; opacity: 0;")]
    s.append((100, f"stroke-dashoffset: {home}; opacity: 0;"))
    KF.append(f"@keyframes sw-{cid} {{\n{_stops(s)}\n}}")
    return f"sw-{cid}"


def kf_propose(cid, windows, base=0.42):
    """A proposal pointer: present but quiet, accented only on its own turn.
    Both pointers sit in the figure at all times so the loop keeps its shape;
    without the dimming they read as the planner pointing at two nodes at once."""
    off = f"color: var(--sw-line); opacity: {base};"
    on = "color: var(--indigo); opacity: 1;"
    s = [(0, off)]
    for a, b in windows:
        s += [(max(0.01, a - 1.0), off), (a, on), (b, on), (min(99.99, b + 1.2), off)]
    s.append((100, off))
    KF.append(f"@keyframes sw-{cid} {{\n{_stops(s)}\n}}")
    return f"sw-{cid}"


def kf_chip(cid, accent, windows):
    """Drives the whole chip through `color`; every part inherits currentColor."""
    off, on = "color: var(--sw-off);", f"color: {accent};"
    s = [(0, off)]
    for a, b in windows:
        s += [(max(0.01, a - 1.4), off), (a, on), (b, on), (min(99.99, b + 1.6), off)]
    s.append((100, off))
    KF.append(f"@keyframes sw-{cid} {{\n{_stops(s)}\n}}")
    return f"sw-{cid}"


# ----------------------------------------------------------------------------
# Build the SVG
# ----------------------------------------------------------------------------
S = []                       # svg body lines
I = " " * 12


def add(line=""):
    S.append(I + line if line else "")


def anim(cls, name):
    return f'class="{cls}" style="animation-name: {name};"'


# --- tree --------------------------------------------------------------------
add('<!-- The search tree. Base edges are always present; the two children and')
add('     their scores are grown by the animation, one MCTS iteration each. -->')
add('<g class="sw-tree">')
for a, b in BASE_EDGES:
    add(f'  <path class="sw-edge" d="{poly([TREE[a], TREE[b]])}" />')

# accepted route, revealed once the verifier passes it
acc_pts = [TREE["root"], TREE["A"], TREE["A2"], N2]
acc_len = length(acc_pts)
n_acc = kf_hold("acc-glow", ph("accept", 0)[0] + 1)
add(f'  <path {anim("sw-accept-glow", n_acc)} d="{poly(acc_pts)}" />')

# the two grown edges
e1 = [TREE["A1"], N1]
e2 = [TREE["A2"], N2]
n_e1 = kf_draw("edge1", length(e1), *ph("execute", 0))
n_e2 = kf_draw("edge2", length(e2), *ph("execute", 1))
add(f'  <path class="sw-edge sw-edge--new" '
    f'style="animation-name: {n_e1}; stroke-dasharray: {length(e1):.1f};" d="{poly(e1)}" />')
add(f'  <path class="sw-edge sw-edge--new sw-edge--win" '
    f'style="animation-name: {n_e2}; stroke-dasharray: {length(e2):.1f};" d="{poly(e2)}" />')

# select / backprop tokens travelling the tree
sel1 = [TREE["root"], TREE["A"], TREE["A1"]]
sel2 = [TREE["root"], TREE["A"], TREE["A2"]]
bk1 = [N1, TREE["A1"], TREE["A"], TREE["root"]]
bk2 = [N2, TREE["A2"], TREE["A"], TREE["root"]]
for cid, pts, wins in [("sel1", sel1, [ph("select", 0)]), ("sel2", sel2, [ph("select", 1)]),
                       ("bk1", bk1, [ph("backprop", 0)]), ("bk2", bk2, [ph("backprop", 1)])]:
    L = length(pts)
    nm = kf_flow(cid, L, wins)
    kind = "sw-token--down" if cid.startswith("sel") else "sw-token--up"
    add(f'  <path class="sw-token {kind}" '
        f'style="animation-name: {nm}; stroke-dasharray: 16 {L:.1f};" d="{poly(pts)}" />')

for k, (x, y) in TREE.items():
    add(f'  <circle class="sw-node" cx="{x}" cy="{y}" r="6.5" />')

# grown nodes + verifier verdicts
n_n1 = kf_hold("node1", ph("execute", 0)[1] - 2)
n_n2 = kf_hold("node2", ph("execute", 1)[1] - 2)
add(f'  <circle {anim("sw-node sw-node--dead", n_n1)} cx="{N1[0]}" cy="{N1[1]}" r="6" />')
add(f'  <circle {anim("sw-node sw-node--win", n_n2)} cx="{N2[0]}" cy="{N2[1]}" r="7" />')

n_b1 = kf_hold("badge1", ph("verify", 0)[0] + 1.5)
n_b2 = kf_hold("badge2", ph("verify", 1)[0] + 1.5)
add(f'  <g {anim("sw-badge sw-badge--bad", n_b1)}>')
add(f'    <path class="sw-cross" d="M{N1[0]-4.6},{N1[1]-4.6} L{N1[0]+4.6},{N1[1]+4.6} '
    f'M{N1[0]+4.6},{N1[1]-4.6} L{N1[0]-4.6},{N1[1]+4.6}" />')
add('    <rect class="sw-badge__box" x="240" y="113" width="31" height="15" rx="7.5" />')
add('    <text class="sw-badge__t" x="255.5" y="120.5" text-anchor="middle" '
    'dominant-baseline="central">31</text>')
add('  </g>')
add(f'  <g {anim("sw-badge sw-badge--good", n_b2)}>')
add(f'    <path class="sw-check" d="M{N2[0]-3.4},{N2[1]} L{N2[0]-0.8},{N2[1]+2.8} '
    f'L{N2[0]+3.8},{N2[1]-3} " />')
add('    <rect class="sw-badge__box" x="240" y="207" width="39" height="15" rx="7.5" />')
add('    <text class="sw-badge__t" x="259.5" y="214.5" text-anchor="middle" '
    'dominant-baseline="central">100</text>')
add('  </g>')
add('</g>')
add()

# --- phase caption -----------------------------------------------------------
add('<!-- Names the MCTS phase currently playing, so the loop is readable. -->')
add('<text class="sw-cap sw-cap--static" x="140" y="400" text-anchor="middle">mcts</text>')
for name in PHASES:
    nm = kf_show(f"cap-{name}", PHASES[name], fade=0.4)
    add(f'<text {anim("sw-cap", nm)} x="140" y="400" text-anchor="middle">{name}</text>')
add('<text class="sw-label" x="128" y="96" text-anchor="middle">search tree</text>')
add()

# --- actor column ------------------------------------------------------------
GLYPH = {
    "spark": ('<path class="sw-glyph-f" d="M0,-7.6 C0.8,-2.4 2.4,-0.8 7.6,0 '
              'C2.4,0.8 0.8,2.4 0,7.6 C-0.8,2.4 -2.4,0.8 -7.6,0 '
              'C-2.4,-0.8 -0.8,-2.4 0,-7.6 Z" />'),
    "grip": ('<path class="sw-glyph-s" d="M0,-8 L0,-2.5 M-6.5,-2.5 L6.5,-2.5 '
             'M-6.5,-2.5 L-6.5,5 M6.5,-2.5 L6.5,5" />'),
    "db": ('<g class="sw-glyph-s">'
           '<ellipse cx="0" cy="-6" rx="7.5" ry="3" />'
           '<path d="M-7.5,-6 L-7.5,3 A7.5,3 0 0 0 7.5,3 L7.5,-6" />'
           '<path d="M-7.5,-1.5 A7.5,3 0 0 0 7.5,-1.5" /></g>'),
}
CHIP_WIN = {
    "memory":  ph("retrieve") + ph("distill"),
    "planner": ph("expand"),
    "robot":   ph("execute"),
    "verifier": ph("verify") + ph("accept"),
}
add('<!-- Who does what. Two VLM roles share the sparkle mark because they are')
add('     the same model; the robot carries a parallel-jaw gripper. -->')
for cid, y, label, glyph, accent in CHIPS:
    nm = kf_chip(f"chip-{cid}", accent, sorted(CHIP_WIN[cid]))
    add(f'<g {anim("sw-chip", nm)}>')
    add(f'  <rect class="sw-chip__glow" x="{CHIP_X}" y="{y}" width="{CHIP_W}" '
        f'height="{CHIP_H}" rx="11" />')
    add(f'  <rect class="sw-chip__box" x="{CHIP_X}" y="{y}" width="{CHIP_W}" '
        f'height="{CHIP_H}" rx="11" />')
    add(f'  <g transform="translate({CHIP_X + 23},{y + CHIP_H / 2:g})">{GLYPH[glyph]}</g>')
    add(f'  <text class="sw-chip__t" x="{CHIP_X + 45}" y="{y + CHIP_H / 2:g}" '
        f'dominant-baseline="central">{label}</text>')
    add('</g>')
add()

# --- arrows ------------------------------------------------------------------
add('<!-- The engine loop: memory feeds the planner, the planner proposes a')
add('     skill, the robot executes it, the verifier scores it, and what passes')
add('     goes to the dataset and back into memory. -->')
ARROWS = [
    # (id, kind, path-points, flow windows)
    ("retrieve", "line", [(COL_X, 84), (COL_X, 121)], ph("retrieve")),
    ("planrobot", "line", [(COL_X, 168), (COL_X, 205)],
     [(a, a + 4) for a, _ in ph("execute")]),
    ("robotver", "line", [(COL_X, 252), (COL_X, 289)],
     [(a, a + 4) for a, _ in ph("verify")]),
    ("accept", "line", [(COL_X, 336), (COL_X, 367)], ph("accept")),
]
for cid, _kind, pts, wins in ARROWS:
    L = length(pts)
    nm = kf_flow(cid, L, wins, dash=12)
    add(f'<path class="sw-arrow" d="{poly(pts)}" />')
    add(f'<path class="sw-head" d="{head(pts[-2], pts[-1])}" />')
    add(f'<path class="sw-token sw-token--arrow" '
        f'style="animation-name: {nm}; stroke-dasharray: 12 {L:.1f};" d="{poly(pts)}" />')

# propose: planner -> the node being expanded (one per iteration)
PROP = [("prop1", (264, 142), (234, 130), (202, 138), (176, 143), 0),
        ("prop2", (264, 156), (232, 170), (202, 194), (177, 203), 1)]
for cid, p0, p1, p2, p3, it in PROP:
    pts = bez(p0, p1, p2, p3)
    L = length(pts)
    nm = kf_flow(cid, L, [ph("expand", it)], dash=14)
    nm_dim = kf_propose(cid + "-dim", [ph("expand", it)])
    add(f'<g class="sw-propose" style="animation-name: {nm_dim};">')
    add(f'  <path class="sw-arrow sw-arrow--dash" d="{bez_d(p0, p1, p2, p3)}" />')
    add(f'  <path class="sw-head" d="{head(pts[-6], pts[-1])}" />')
    add('</g>')
    add(f'<path class="sw-token sw-token--arrow" '
        f'style="animation-name: {nm}; stroke-dasharray: 14 {L:.1f};" '
        f'd="{bez_d(p0, p1, p2, p3)}" />')

# distill: verifier -> memory, the long return arc
# Control points at 556 put the curve's apex near x=529 (a cubic reaches
# only ~3/4 of the way to its controls), clearing the outcome labels.
d0, d1, d2, d3 = (448, 314), (556, 300), (556, 76), (448, 62)
dpts = bez(d0, d1, d2, d3)
dL = length(dpts)
add(f'<path class="sw-arrow sw-arrow--dash" d="{bez_d(d0, d1, d2, d3)}" />')
add(f'<path class="sw-head" d="{head(dpts[-6], dpts[-1])}" />')
for cid, kind, it in [("distill-fail", "fail", 0), ("distill-ok", "ok", 1)]:
    nm = kf_flow(cid, dL, [ph("distill", it)], dash=18)
    add(f'<path class="sw-token sw-token--arrow sw-token--{kind}" '
        f'style="animation-name: {nm}; stroke-dasharray: 18 {dL:.1f};" '
        f'd="{bez_d(d0, d1, d2, d3)}" />')

add('<text class="sw-label" x="368" y="102" text-anchor="start">retrieve</text>')
add('<text class="sw-label" x="368" y="354" text-anchor="start">accept</text>')
add('<text class="sw-label" x="212" y="178" text-anchor="middle">propose</text>')
add('<text class="sw-label" x="486" y="176" text-anchor="middle">distill</text>')
for cid, kind, word, it in [("out-fail", "fail", "lesson", 0),
                            ("out-ok", "ok", "strategy", 1)]:
    nm = kf_show(cid, [ph("distill", it)], fade=0.6)
    add(f'<text class="sw-label sw-label--sub sw-outcome sw-label--{kind}" '
        f'style="animation-name: {nm};" x="486" y="194" '
        f'text-anchor="middle">{word}</text>')
add()

# --- dataset deck ------------------------------------------------------------
dx, dy, dw, dh = DECK
n_deck = kf_show("deck", [(ph("accept", 0)[0] + 2, ph("accept", 0)[1] + 4)], fade=1.2)
add('<!-- Verified demonstrations. The deck pulses as each one lands. -->')
add(f'<g class="sw-deck">')
add(f'  <rect class="sw-card sw-card--back" x="{dx+10}" y="{dy+10}" width="{dw}" height="{dh}" rx="7" />')
add(f'  <rect class="sw-card sw-card--mid" x="{dx+5}" y="{dy+5}" width="{dw}" height="{dh}" rx="7" />')
add(f'  <rect class="sw-card" x="{dx}" y="{dy}" width="{dw}" height="{dh}" rx="7" />')
add(f'  <path class="sw-card__line" d="M{dx+9},{dy+13} L{dx+43},{dy+13} '
    f'M{dx+9},{dy+22} L{dx+35},{dy+22} M{dx+9},{dy+31} L{dx+43},{dy+31}" />')
add(f'  <rect {anim("sw-card sw-card--new", n_deck)} x="{dx-5}" y="{dy-5}" '
    f'width="{dw}" height="{dh}" rx="7" />')
add('</g>')
add(f'<text class="sw-label" x="{dx + dw/2:g}" y="448" text-anchor="middle">verified demos</text>')

SVG_BODY = "\n".join(S)
SVG = f'''<svg class="field" viewBox="0 0 {VB_W} {VB_H}" role="img"
            aria-label="The SkillWeaver engine: a Monte Carlo tree search grows a tree of interaction skills. Memory feeds a VLM planner, which proposes a skill; a learned robot skill executes it; a VLM verifier scores the result, sending it back up the tree, into the verified-demonstration dataset, and back into memory.">
{SVG_BODY}
          </svg>'''

# ----------------------------------------------------------------------------
# CSS
# ----------------------------------------------------------------------------
CSS_BLOCK = """/* >>> HERO FIGURE — generated by tools/make_hero.py, do not edit by hand >>> */
/* One MCTS iteration loop. Every animated element shares --sw-cycle and carries
   its own phase window in its keyframe percentages, so the whole figure stays in
   step without a scheduler. */
.field {
  width: 100%;
  height: auto;
  overflow: visible;
  --sw-cycle: %CYCLE%;
  --sw-off: #6B7688;
  --sw-line: #39424F;
}

.field [style*="animation-name"],
.field .sw-chip {
  animation-duration: var(--sw-cycle);
  animation-timing-function: linear;
  animation-iteration-count: infinite;
  animation-fill-mode: both;
}

/* ---- search tree ---- */
.field .sw-edge {
  fill: none;
  stroke: var(--sw-line);
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.field .sw-edge--new {
  stroke: var(--amber);
  stroke-width: 2.2;
  opacity: 0;
}

.field .sw-edge--win {
  stroke: var(--amber);
}

.field .sw-accept-glow {
  fill: none;
  stroke: url(#swWin);
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
  opacity: 0;
  filter: drop-shadow(0 0 7px rgba(255, 176, 32, 0.4));
}

.field .sw-node {
  fill: #161C27;
  stroke: #8892A6;
  stroke-width: 1.6;
}

.field .sw-node--dead {
  fill: none;
  stroke: var(--rose);
  opacity: 0;
}

.field .sw-node--win {
  fill: var(--amber);
  stroke: none;
  opacity: 0;
  filter: drop-shadow(0 0 8px rgba(255, 176, 32, 0.55));
}

/* The travelling token: a short dash swept along the path by dashoffset, which
   is better supported than offset-path and needs no extra element. */
.field .sw-token {
  fill: none;
  stroke-width: 3;
  stroke-linecap: round;
  opacity: 0;
}

.field .sw-token--down { stroke: var(--indigo); }
.field .sw-token--up { stroke: var(--teal); }

.field .sw-token--arrow {
  stroke: currentColor;
  stroke-width: 2.6;
  color: var(--teal);
}

/* What a distilled trajectory contributes depends on its verdict. */
.field .sw-token--fail { color: var(--rose); }
.field .sw-token--ok { color: var(--teal); }

/* ---- verifier verdicts ---- */
.field .sw-badge { opacity: 0; }

.field .sw-badge__box {
  fill: none;
  stroke-width: 1.2;
}

.field .sw-badge__t {
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
}

.field .sw-badge--bad .sw-badge__box { stroke: var(--rose); }
.field .sw-badge--bad .sw-badge__t { fill: var(--rose); }
.field .sw-badge--good .sw-badge__box { stroke: var(--teal); }
.field .sw-badge--good .sw-badge__t { fill: var(--teal); }

.field .sw-cross {
  fill: none;
  stroke: var(--rose);
  stroke-width: 1.8;
  stroke-linecap: round;
}

.field .sw-check {
  fill: none;
  stroke: #0A0D13;
  stroke-width: 1.9;
  stroke-linecap: round;
  stroke-linejoin: round;
}

/* ---- actor chips ---- */
.field .sw-chip {
  color: var(--sw-off);
}

.field .sw-chip__glow {
  fill: none;
  stroke: currentColor;
  stroke-width: 7;
  opacity: 0.13;
}

.field .sw-chip__box {
  fill: currentColor;
  fill-opacity: 0.09;
  stroke: currentColor;
  stroke-opacity: 0.6;
  stroke-width: 1.5;
}

.field .sw-glyph-f {
  fill: currentColor;
}

.field .sw-glyph-s {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.field .sw-chip__t {
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.07em;
  fill: currentColor;
}

/* ---- arrows ---- */
.field .sw-arrow {
  fill: none;
  stroke: var(--sw-line);
  stroke-width: 1.5;
  stroke-linecap: round;
}

.field .sw-arrow--dash {
  stroke-dasharray: 3 4.5;
}

.field .sw-head {
  fill: var(--sw-line);
}

.field .sw-propose {
  color: var(--sw-line);
  opacity: 0.42;
}

.field .sw-propose .sw-arrow { stroke: currentColor; }
.field .sw-propose .sw-head { fill: currentColor; }

/* ---- dataset ---- */
.field .sw-card {
  fill: #0F1420;
  stroke: #8892A6;
  stroke-width: 1.4;
}

.field .sw-card--back { opacity: 0.28; }
.field .sw-card--mid { opacity: 0.55; }

.field .sw-card--new {
  stroke: var(--teal);
  opacity: 0;
  filter: drop-shadow(0 0 8px rgba(45, 212, 191, 0.4));
}

.field .sw-card__line {
  stroke: #8892A6;
  stroke-width: 1.3;
  stroke-linecap: round;
  opacity: 0.5;
}

/* ---- labels ---- */
.field .sw-label {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  fill: #8892A6;
}

.field .sw-label--sub {
  font-size: 10px;
  letter-spacing: 0.08em;
}

.field .sw-label--fail { fill: var(--rose); }
.field .sw-label--ok { fill: var(--teal); }

/* Only one outcome word is on screen at a time. */
.field .sw-outcome { opacity: 0; }

.field .sw-cap {
  font-family: var(--mono);
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  fill: var(--amber);
  opacity: 0;
}

.field .sw-cap--static { opacity: 0; }

%KEYFRAMES%

/* Reduced motion: hold the finished state — both children expanded, both
   verdicts in, the accepted route lit — and stop every loop. */
@media (prefers-reduced-motion: reduce) {
  .field [style*="animation-name"],
  .field .sw-chip {
    animation: none !important;
  }

  .field .sw-edge--new,
  .field .sw-node--dead,
  .field .sw-node--win,
  .field .sw-badge,
  .field .sw-accept-glow,
  .field .sw-card--new {
    opacity: 1;
    stroke-dashoffset: 0;
  }

  .field .sw-token {
    display: none;
  }

  .field .sw-cap { opacity: 0; }
  .field .sw-cap--static { opacity: 1; }
}
/* <<< HERO FIGURE <<< */"""

CSS_BLOCK = (CSS_BLOCK.replace("%CYCLE%", CYCLE)
             .replace("%KEYFRAMES%", "\n\n".join(KF)))

# ----------------------------------------------------------------------------
# Patch the two files
# ----------------------------------------------------------------------------
html = open(HTML).read()
a = html.index('<svg class="field"')
b = html.index("</svg>") + len("</svg>")
# The gradient the accepted route is painted with lives in <defs>.
defs = ('<defs>\n'
        '              <linearGradient id="swWin" gradientUnits="userSpaceOnUse" '
        'x1="40" y1="0" x2="230" y2="0">\n'
        '                <stop offset="0" stop-color="#2DD4BF" />\n'
        '                <stop offset="0.55" stop-color="#7C83F7" />\n'
        '                <stop offset="1" stop-color="#FFB020" />\n'
        '              </linearGradient>\n'
        '            </defs>\n')
svg = SVG.replace("\n" + " " * 12, "\n" + " " * 12, 1)
svg = svg.replace(">\n", ">\n" + " " * 12 + defs, 1)
open(HTML, "w").write(html[:a] + svg + html[b:])

css = open(CSS).read()
start = css.index("/* >>> HERO FIGURE") if ">>> HERO FIGURE" in css else None
if start is None:
    # First run: replace the old hand-written signature section.
    start = css.index("/* ============================================================\n"
                      "   Signature")
    end = css.index("/* ============================================================\n   Stat strip")
else:
    end = css.index("/* <<< HERO FIGURE <<< */") + len("/* <<< HERO FIGURE <<< */\n")
open(CSS, "w").write(css[:start] + CSS_BLOCK + "\n" + css[end:])

print(f"svg      : {len(SVG)} chars, {SVG.count('<path')} paths")
print(f"keyframes: {len(KF)} blocks")
print(f"css block: {len(CSS_BLOCK)} chars")
print(f"cycle    : {CYCLE}")
