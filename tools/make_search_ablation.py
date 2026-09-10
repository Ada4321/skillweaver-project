#!/usr/bin/env python3
"""Generate the MCTS-vs-linear panel of the Ablations section.

Left: two search animations that share one cycle, so they can be compared
while they play. They use the hero figure's visual language (tools/make_hero.py):
dark space panel, small dark nodes, amber for an edge being grown, rose ring for
a rejected node, amber glow for the accepted one, the teal->indigo->amber
gradient for the accepted path, and an indigo token travelling down to the
node being selected.

  MCTS    Each expansion proposes two skills and the verifier checks both. A
          failed child is never expanded again; the search goes back to the
          last verified node, so a successful prefix is never re-executed.
  Linear  One skill per step. After a failure the chain just keeps growing
          until it runs into the maximum depth; then the whole chain is thrown
          away and the next attempt starts from scratch on a second row, with
          the discarded attempt left greyed out above it.

Both run every skill execution at the same speed and fail at the same hard
step, so the difference in finishing time comes from the search alone.

Right: tab:execution-search-ablation (b) from the paper, transposed so it fits
a half-width column.

Every animated element gets its keyframes from the timeline below, and the
same timeline drives --frames, which renders stills with cairosvg -- there is
no browser on the cluster to watch the animation in. Colours are presentation
attributes; the CSS animates opacity, stroke, stroke-dashoffset and scale.

    python3 tools/make_search_ablation.py [--html PATH] [--css PATH] [--frames DIR]

--frames writes search_ablation_frames.png into DIR; keep DIR outside the repo.

Rewrites the marked block inside #panel-abl-mcts and the marked CSS block, in
place; running it twice changes nothing.
"""
import argparse
import io
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEF_HTML = ROOT / "index.html"
DEF_CSS = ROOT / "css" / "style.css"

CYCLE = 18.0
FADE0, FADE1 = 16.6, 17.3          # everything clears before the loop restarts
HOLD = 16.0                        # the still shown under prefers-reduced-motion
VB_W = 620
M_H, L_H = 190, 146

# The hero's palette (css/style.css `.field`).
SPACE = "#0A0D13"
SW_LINE = "#39424F"
NODE_FILL, NODE_STROKE = "#161C27", "#8892A6"
LABEL = "#8892A6"
TEAL, INDIGO, AMBER, ROSE = "#2DD4BF", "#7C83F7", "#FFB020", "#F4566E"
MONO = "Space Mono, ui-monospace, monospace"
R = 7


def f(x):
    s = f"{x:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def hexlerp(a, b, u):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * u):02X}" for x, y in zip(ca, cb))


# ----------------------------------------------------------------------------
# Animated element model
# ----------------------------------------------------------------------------
class El:
    def __init__(self, uid, tag, attrs=None, children=(), origin=None, dash=None, cls=""):
        self.uid, self.tag, self.attrs = uid, tag, dict(attrs or {})
        self.children, self.origin, self.dash, self.cls = list(children), origin, dash, cls
        self.tracks = {}                      # prop -> [(t, v)]

    def track(self, prop, pairs):
        self.tracks[prop] = sorted(pairs, key=lambda p: p[0])
        return self

    def value(self, prop, t):
        tr = self.tracks[prop]
        if t <= tr[0][0]:
            return tr[0][1]
        for (t0, v0), (t1, v1) in zip(tr, tr[1:]):
            if t0 <= t <= t1:
                u = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                return hexlerp(v0, v1, u) if isinstance(v0, str) else v0 + (v1 - v0) * u
        return tr[-1][1]


def appear(t_in, dur=0.18, level=1.0, dim=None, out=(FADE0, FADE1)):
    p = [(0.0, 0.0), (t_in, 0.0), (t_in + dur, level)]
    if dim:
        t_dim, to = dim
        p += [(t_dim, level), (t_dim + 0.5, to)]
        level = to
    return p + [(out[0], level), (out[1], 0.0), (CYCLE, 0.0)]


def pop(t_in, lo=0.6):
    return [(0.0, lo), (t_in, lo), (t_in + 0.12, 1.15), (t_in + 0.26, 1.0), (CYCLE, 1.0)]


def once(t_in, dur=0.18):
    """Shows and stays; the enclosing node group owns the fade-out."""
    return [(0.0, 0.0), (t_in, 0.0), (t_in + dur, 1.0), (CYCLE, 1.0)]


# ----------------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------------
def cubic_pts(p0, p1, p2, p3, n=64):
    out = []
    for i in range(n + 1):
        s = i / n
        a, b, c, d = (1 - s) ** 3, 3 * (1 - s) ** 2 * s, 3 * (1 - s) * s * s, s ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def plen(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def seg(p, q):
    """Leave the parent's right rim and enter the child's left rim, both horizontally."""
    (x1, y1), (x2, y2) = p, q
    s, e = (x1 + R, y1), (x2 - R, y2)
    cx = (s[0] + e[0]) / 2
    return s, (cx, y1), (cx, y2), e


def chain_path(points):
    """One path rim-to-rim along a chain of node centres, running through each inner node."""
    parts, total = [f"M{f(points[0][0] + R)},{f(points[0][1])}"], 0.0
    for i, (p, q) in enumerate(zip(points, points[1:])):
        s, c1, c2, e = seg(p, q)
        parts.append(f"C{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} {f(e[0])},{f(e[1])}")
        total += plen(cubic_pts(s, c1, c2, e))
        if i < len(points) - 2:
            parts.append(f"L{f(q[0] + R)},{f(q[1])}")
            total += 2 * R
    return " ".join(parts), total


def check_d(cx, cy, k=1.0):
    return (f"M{f(cx - 3.1 * k)},{f(cy + 0.2 * k)} L{f(cx - 0.9 * k)},{f(cy + 2.4 * k)} "
            f"L{f(cx + 3.2 * k)},{f(cy - 2.3 * k)}")


def cross_d(cx, cy, s=2.7):
    return f"M{f(cx - s)},{f(cy - s)} L{f(cx + s)},{f(cy + s)} M{f(cx + s)},{f(cy - s)} L{f(cx - s)},{f(cy + s)}"


def label(x, y, text, fill=LABEL, anchor="middle"):
    return (f'<text x="{f(x)}" y="{f(y)}" text-anchor="{anchor}" font-family="{MONO}" font-size="10" '
            f'letter-spacing="1" fill="{fill}">{text}</text>')


def gradient(gid, x1, x2):
    return (f'<defs><linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{f(x1)}" y1="0" '
            f'x2="{f(x2)}" y2="0"><stop offset="0" stop-color="{TEAL}"/><stop offset="0.55" '
            f'stop-color="{INDIGO}"/><stop offset="1" stop-color="{AMBER}"/></linearGradient></defs>')


# ----------------------------------------------------------------------------
# Builders
# ----------------------------------------------------------------------------
def edge(uid, p, q, t_draw, t_verdict, dim=None, out=(FADE0, FADE1)):
    s, c1, c2, e = seg(p, q)
    d = f"M{f(s[0])},{f(s[1])} C{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} {f(e[0])},{f(e[1])}"
    L = plen(cubic_pts(s, c1, c2, e))
    # grown in amber like the hero's new edges, settles to the tree line once judged
    return (El(uid, "path", {"d": d, "fill": "none", "stroke": SW_LINE, "stroke-width": "1.8",
                             "stroke-linecap": "round"}, dash=f"{f(L)} {f(L)}")
            .track("o", appear(t_draw, dur=0.05, dim=dim, out=out))
            .track("d", [(0.0, L), (t_draw, L), (t_draw + 0.45, 0.0), (CYCLE, 0.0)])
            .track("c", [(0.0, AMBER), (t_verdict, AMBER), (t_verdict + 0.4, SW_LINE), (CYCLE, SW_LINE)]))


def node(uid, cx, cy, ok, t_show, t_verdict, dim=None, out=(FADE0, FADE1)):
    ring = (f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{R}" fill="{NODE_FILL}" stroke="{NODE_STROKE}" '
            f'stroke-width="1.6"/>')
    if ok:
        body = (f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{R}" fill="{NODE_FILL}" stroke="{TEAL}" stroke-width="1.8"/>'
                f'<path d="{check_d(cx, cy)}" fill="none" stroke="{TEAL}" stroke-width="1.6" '
                f'stroke-linecap="round" stroke-linejoin="round"/>')
    else:
        body = (f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{R}" fill="{NODE_FILL}" stroke="{ROSE}" stroke-width="1.8"/>'
                f'<path d="{cross_d(cx, cy)}" fill="none" stroke="{ROSE}" stroke-width="1.6" stroke-linecap="round"/>')
    verdict = (El(uid + "-v", "g", children=[body], origin=(cx, cy))
               .track("o", once(t_verdict)).track("s", pop(t_verdict)))
    return El(uid, "g", children=[ring, verdict]).track("o", appear(t_show, dim=dim, out=out))


def token(uid, points, t_arrive):
    """The hero's selection token: a short indigo dash running down to the chosen node."""
    d, L = chain_path(points)
    dur = max(0.25, L / 700)
    t0 = t_arrive - dur
    return (El(uid, "path", {"d": d, "fill": "none", "stroke": INDIGO, "stroke-width": "3",
                             "stroke-linecap": "round"}, dash=f"16 {f(L + 32)}")
            .track("o", [(0.0, 0.0), (t0, 0.0), (t0 + 0.03, 1.0), (t_arrive, 1.0), (t_arrive + 0.06, 0.0), (CYCLE, 0.0)])
            .track("d", [(0.0, 16.0), (t0, 16.0), (t_arrive, -(L - 16)), (CYCLE, -(L - 16))]))


def glow(uid, points, t, gid):
    d, L = chain_path(points)
    return (El(uid, "path", {"d": d, "fill": "none", "stroke": f"url(#{gid})", "stroke-width": "3",
                             "stroke-linecap": "round", "stroke-linejoin": "round"},
               dash=f"{f(L)} {f(L)}", cls="sa-glow")
            .track("o", appear(t, dur=0.05)).track("d", [(0.0, L), (t, L), (t + 1.0, 0.0), (CYCLE, 0.0)]))


def goal(uid, cx, cy, t):
    body = (f'<circle cx="{f(cx)}" cy="{f(cy)}" r="7.5" fill="{AMBER}"/>'
            f'<path d="{check_d(cx, cy)}" fill="none" stroke="{SPACE}" stroke-width="1.9" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')
    # Fades only after everything else is gone: fading together with the teal
    # verdict it covers, the two blend for most of a second.
    return (El(uid, "g", children=[body], origin=(cx, cy), cls="sa-goal")
            .track("o", appear(t, out=(FADE1, FADE1 + 0.3))).track("s", pop(t)))


def count_label(uid, x, y, n, t):
    """Shown once the trajectory is lit: how many expansions it took."""
    return (El(uid, "g", children=[
        f'<text x="{f(x)}" y="{f(y)}" text-anchor="end" font-family="{MONO}" font-size="13" '
        f'font-weight="700" letter-spacing="2" fill="{AMBER}">{n} EXPANSIONS</text>'])
        .track("o", appear(t, dur=0.3)))


def root(cx, cy):
    return (f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{R}" fill="{NODE_FILL}" stroke="{NODE_STROKE}" stroke-width="1.6"/>'
            + label(cx, cy + 22, "START"))


# ----------------------------------------------------------------------------
# Shared pacing
# ----------------------------------------------------------------------------
# Every skill execution takes EXEC seconds in both animations, its verdict
# landing VERDICT seconds in, and both fail about as often: MCTS executes 8
# skills in 4 expansions (3 fail); linear executes 11, one expansion each
# (4 fail), plus a restart. The goals are reached at ~9.3 s and ~12.7 s --
# roughly the 891 s / 645 s wall-clock ratio of tab:execution-search-ablation (b).
EXEC, VERDICT = 0.95, 0.8


# ----------------------------------------------------------------------------
# MCTS: branch 2, depth 4
# ----------------------------------------------------------------------------
M_POS = {"R": (40, 95), "A": (165, 95), "A2": (165, 155), "B": (290, 95), "B2": (290, 35),
         "C": (415, 155), "C2": (415, 95), "D": (540, 95), "D2": (540, 35)}
M_OK = {"A": True, "A2": True, "B": True, "B2": False, "C": False, "C2": True, "D": True, "D2": False}
M_PATH = ["R", "A", "B", "C2", "D"]
M_PARENTS = {"A": "R", "A2": "R", "B": "A", "B2": "A", "C": "B", "C2": "B", "D": "C2", "D2": "C2"}
# (parent, expansion start, children in execution order). Both children are
# proposed together and executed one after the other -- conf/mcts/default.yaml;
# the parallel env pool (mcts=parallel) is opt-in.
M_EXP = [("R", 0.5, ["A", "A2"]),
         ("A", 2.7, ["B", "B2"]),
         ("B", 5.0, ["C", "C2"]),
         ("C2", 7.55, ["D2", "D"])]
M_RESELECT = [("B", 6.34)]           # back to the verified node before its other child
M_GLOW = 9.45


def path_to(key):
    chain = [key]
    while chain[-1] != "R":
        chain.append(M_PARENTS[chain[-1]])
    return [M_POS[k] for k in reversed(chain)]


def build_mcts():
    P = "sa-m"
    dim = (M_GLOW, 0.35)
    edges, nodes, tokens = [], [], []
    for parent, t0, kids in M_EXP:
        if parent != "R":
            tokens.append(token(f"{P}-sel-{parent}", path_to(parent), t0 - 0.05))
        for k, child in enumerate(kids):
            t_v = t0 + VERDICT + k * EXEC
            keep = child in M_PATH
            edges.append(edge(f"{P}-e-{child}", M_POS[parent], M_POS[child], t0, t_v,
                              dim=None if keep else dim))
            nodes.append(node(f"{P}-{child}", *M_POS[child], M_OK[child], t0 + 0.45, t_v,
                              dim=None if keep else dim))
    for key, t in M_RESELECT:
        tokens.append(token(f"{P}-resel-{key}", path_to(key), t))
    pts = [M_POS[k] for k in M_PATH]
    return ([gradient("saWinM", pts[0][0], pts[-1][0])] + edges
            + [glow(f"{P}-glow", pts, M_GLOW, "saWinM")] + tokens
            + [root(*M_POS["R"])] + nodes + [goal(f"{P}-goal", *pts[-1], M_GLOW + 1.0),
                                             count_label(f"{P}-count", 612, 182, len(M_EXP), M_GLOW + 1.3)])


# ----------------------------------------------------------------------------
# Linear: branch 1, restart at max depth
# ----------------------------------------------------------------------------
L_X = [36 + 86 * i for i in range(7)]
L_Y1, L_Y2 = 44, 108
L_WALL = 594
L_RUN1 = [True, True, False, False, True, False]     # 3 of 4 steps done at max depth
L_RUN2 = [True, True, False, True, True]             # recovers within it
L_T1, L_T2 = 0.5, 8.1
L_WALL_HIT = L_T1 + EXEC * len(L_RUN1) + 0.05        # 6.25
L_GHOST = (L_WALL_HIT + 0.45, 0.28)                  # the discarded attempt stays, greyed out
L_ROOT2 = L_WALL_HIT + 0.75
L_GLOW = L_T2 + EXEC * (len(L_RUN2) - 1) + VERDICT + 0.15


def build_linear():
    P = "sa-l"
    edges, nodes = [], []
    for run, steps, t0, y, dim in (("r1", L_RUN1, L_T1, L_Y1, L_GHOST),
                                   ("r2", L_RUN2, L_T2, L_Y2, None)):
        for i, ok in enumerate(steps):
            te = t0 + EXEC * i
            edges.append(edge(f"{P}-e-{run}-{i}", (L_X[i], y), (L_X[i + 1], y), te, te + VERDICT, dim=dim))
            nodes.append(node(f"{P}-{run}-{i}", L_X[i + 1], y, ok, te + 0.45, te + VERDICT, dim=dim))
    wall = (f'<path d="M{L_WALL},24 L{L_WALL},122" stroke="{SW_LINE}" stroke-width="1.6" '
            f'stroke-dasharray="3 4.5" stroke-linecap="round"/>' + label(614, 14, "MAX DEPTH", anchor="end"))
    flash = (El(f"{P}-wall-hit", "g", children=[
        f'<path d="M{L_WALL},24 L{L_WALL},122" stroke="{ROSE}" stroke-width="2" stroke-dasharray="3 4.5" '
        f'stroke-linecap="round"/>' + label(614, 14, "MAX DEPTH", fill=ROSE, anchor="end")])
        .track("o", [(0.0, 0.0), (L_WALL_HIT, 0.0), (L_WALL_HIT + 0.15, 1.0), (L_WALL_HIT + 0.9, 1.0),
                     (L_WALL_HIT + 1.3, 0.0), (CYCLE, 0.0)]))
    root2 = (El(f"{P}-root2", "g", children=[
        f'<circle cx="{L_X[0]}" cy="{L_Y2}" r="{R}" fill="{NODE_FILL}" stroke="{NODE_STROKE}" stroke-width="1.6"/>'
        + label(L_X[0], L_Y2 + 22, "RESTART", fill=INDIGO)])
        .track("o", appear(L_ROOT2, dur=0.3)))
    pts = [(L_X[i], L_Y2) for i in range(len(L_RUN2) + 1)]
    return ([gradient("saWinL", pts[0][0], pts[-1][0]), wall] + edges
            + [glow(f"{P}-glow", pts, L_GLOW, "saWinL"), root(L_X[0], L_Y1), root2, flash]
            + nodes + [goal(f"{P}-goal", *pts[-1], L_GLOW + 1.0),
                       count_label(f"{P}-count", 612, 140, len(L_RUN1) + len(L_RUN2), L_GLOW + 1.3)])


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------
def render(x, mode, t=None):
    if isinstance(x, str):
        return x
    a = dict(x.attrs)
    head = ""
    if mode == "page":
        head = f'id="{x.uid}" class="sa{(" " + x.cls) if x.cls else ""}"'
    else:
        if "o" in x.tracks:
            a["opacity"] = f(x.value("o", t))
        if "c" in x.tracks:
            a["stroke"] = x.value("c", t)
        if "d" in x.tracks:
            a["stroke-dasharray"] = x.dash
            a["stroke-dashoffset"] = f(x.value("d", t))
        if "s" in x.tracks:
            s, (cx, cy) = x.value("s", t), x.origin
            a["transform"] = f"translate({f(cx)} {f(cy)}) scale({f(s)}) translate({f(-cx)} {f(-cy)})"
    attrs = " ".join(filter(None, [head] + [f'{k}="{v}"' for k, v in a.items()]))
    inner = "".join(render(c, mode, t) for c in x.children)
    if x.tag == "g" or inner:
        return f"<{x.tag} {attrs}>{inner}</{x.tag}>"
    return f"<{x.tag} {attrs}/>"


def walk(items):
    for x in items:
        if isinstance(x, El):
            yield x
            yield from walk(x.children)


def pct(t):
    return f(t / CYCLE * 100) + "%"


PROP_CSS = {
    "o": lambda v: f"opacity: {f(v)};",
    "c": lambda v: f"stroke: {v};",
    "d": lambda v: f"stroke-dashoffset: {f(v)};",
    "s": lambda v: f"transform: scale({f(v)});",
}


def css_for(x):
    decl = [f"animation-name: {x.uid};"]
    if "s" in x.tracks:
        cx, cy = x.origin
        decl += ["transform-box: view-box;", f"transform-origin: {f(cx)}px {f(cy)}px;"]
    if "d" in x.tracks:
        decl.append(f"stroke-dasharray: {x.dash};")
    hold = [PROP_CSS[p](x.value(p, HOLD)) for p in x.tracks]
    out = [f"#{x.uid} {{ " + " ".join(decl + hold) + " }", f"@keyframes {x.uid} {{"]
    for t in sorted({t for tr in x.tracks.values() for t, _ in tr}):
        parts = [PROP_CSS[p](v) for p, tr in x.tracks.items() for tt, v in tr if abs(tt - t) < 1e-9]
        out.append(f"  {pct(t)} {{ " + " ".join(parts) + " }")
    out.append("}")
    return "\n".join(out)


BEGIN_H = "<!-- >>> SEARCH ABLATION — generated by tools/make_search_ablation.py, do not edit by hand >>> -->"
END_H = "<!-- <<< SEARCH ABLATION <<< -->"
BEGIN_C = "/* >>> SEARCH ABLATION — generated by tools/make_search_ablation.py, do not edit by hand >>> */"
END_C = "/* <<< SEARCH ABLATION <<< */"

TABLE = """<div class="table-wrap abl-table" role="region" tabindex="0" aria-label="MCTS versus linear skill sequencing efficiency">
  <table>
    <thead>
      <tr>
        <th scope="col">Search</th>
        <th scope="col">Linear</th>
        <th scope="col" class="ours">MCTS (ours)</th>
      </tr>
    </thead>
    <tbody>
      <tr><th scope="row">Breadth</th><td>1</td><td class="ours">2</td></tr>
      <tr><th scope="row">Max Depth</th><td>20</td><td class="ours">4</td></tr>
      <tr><th scope="row">Max Simulation Rounds</th><td>20</td><td class="ours">20</td></tr>
      <tr><th scope="row">Expansions / traj.</th><td>6.74</td><td class="ours"><b>3.60</b></td></tr>
      <tr><th scope="row">Time / traj. (s)</th><td>891</td><td class="ours"><b>645</b></td></tr>
    </tbody>
  </table>
</div>
<p class="table-note">Tested on five long-horizon tasks under the same simulation budget. <b>MCTS needs fewer expansions and
  less wall-clock time</b> per successful trajectory, by reusing successful skill prefixes across branches.</p>"""


def html_block(m_els, l_els):
    m_svg = (f'<svg class="search-anim" viewBox="0 0 {VB_W} {M_H}" role="img" aria-label="MCTS: each expansion '
             f'proposes two skills and the verifier checks both; failed branches are dropped and search resumes '
             f'from the last verified node until the four-step trajectory is accepted.">\n'
             + "\n".join(render(e, "page") for e in m_els) + "\n</svg>")
    l_svg = (f'<svg class="search-anim" viewBox="0 0 {VB_W} {L_H}" role="img" aria-label="Linear skill '
             f'sequencing: the chain keeps growing after failures until it reaches the maximum depth, is '
             f'discarded, and restarts from scratch before it succeeds.">\n'
             + "\n".join(render(e, "page") for e in l_els) + "\n</svg>")
    return "\n".join([
        BEGIN_H,
        '<div class="abl-split">',
        '  <div class="abl-anims">',
        '    <figure class="abl-anim">',
        '      <figcaption class="abl-anim__cap"><b>MCTS</b><span>failed branch dropped &middot; verified prefix kept</span></figcaption>',
        m_svg,
        '    </figure>',
        '    <figure class="abl-anim">',
        '      <figcaption class="abl-anim__cap"><b>Linear</b><span>chain grows on failure &middot; restarts at max depth</span></figcaption>',
        l_svg,
        '    </figure>',
        '    <div class="abl-legend"><span><i class="k-pass"></i>verifier pass</span><span><i class="k-fail"></i>verifier fail</span><span><i class="k-win"></i>accepted trajectory</span></div>',
        '  </div>',
        '  <div class="abl-side">',
        TABLE,
        '  </div>',
        '</div>',
        END_H,
    ])


def css_block(els):
    static = f"""{BEGIN_C}
.abl-split {{
  display: grid;
  grid-template-columns: 1.25fr 1fr;
  gap: 36px;
  align-items: center;
}}

.abl-anims {{
  display: grid;
  gap: 14px;
}}

/* The hero's space panel, glows scaled down to a card. */
.abl-anim {{
  margin: 0;
  background:
    radial-gradient(420px 200px at 88% 0%, rgba(124, 131, 247, 0.2), transparent 62%),
    radial-gradient(360px 200px at 100% 100%, rgba(255, 176, 32, 0.1), transparent 62%),
    radial-gradient(340px 220px at 0% 35%, rgba(45, 212, 191, 0.12), transparent 62%),
    var(--space);
  border-radius: var(--radius);
  padding: 14px 18px 12px;
}}

.abl-anim__cap {{
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
  font-family: var(--mono);
  font-size: 0.72rem;
  color: var(--on-space-mute);
  margin: 0 0 4px;
}}

.abl-anim__cap b {{
  color: var(--on-space);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}}

.search-anim {{
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
}}

.abl-legend {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  font-family: var(--mono);
  font-size: 0.7rem;
  color: var(--mute);
  padding: 0 2px;
}}

.abl-legend i {{
  display: inline-block;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  margin-right: 7px;
  vertical-align: -1px;
  background: {NODE_FILL};
}}

.abl-legend .k-pass {{ box-shadow: inset 0 0 0 1.8px var(--teal); }}
.abl-legend .k-fail {{ box-shadow: inset 0 0 0 1.8px var(--rose); }}
.abl-legend .k-win {{ background: var(--amber); box-shadow: 0 0 6px rgba(255, 176, 32, 0.55); }}

/* Transposed to three columns, so the global 560px floor would only force a
   scrollbar in a half-width column. */
.abl-table table {{
  min-width: 0;
}}

.abl-table .ours {{
  background: rgba(124, 131, 247, 0.055);
}}

.abl-side .table-note {{
  margin-top: 14px;
}}

@media (max-width: 900px) {{
  .abl-split {{
    grid-template-columns: 1fr;
  }}
}}

/* One shared cycle; each element's timing is baked into its own keyframes. */
.search-anim .sa {{
  animation-duration: {f(CYCLE)}s;
  animation-timing-function: linear;
  animation-iteration-count: infinite;
  animation-fill-mode: both;
}}

.search-anim .sa-glow {{
  filter: drop-shadow(0 0 7px rgba(255, 176, 32, 0.4));
}}

.search-anim .sa-goal {{
  filter: drop-shadow(0 0 8px rgba(255, 176, 32, 0.55));
}}
"""
    rules = "\n".join(css_for(x) for x in els)
    tail = f"""
/* The per-element #id rules set animation-name at (1,0,0), which a plain
   `animation: none` here would lose to -- hence !important. Without motion each
   element rests at its HOLD state: both searches finished, trajectory lit. */
@media (prefers-reduced-motion: reduce) {{
  .search-anim .sa {{
    animation: none !important;
  }}
}}
{END_C}"""
    return static + "\n" + rules + "\n" + tail


def patch_html(path, block):
    h = path.read_text()
    p0 = h.index('id="panel-abl-mcts"')
    p1 = h.find('id="panel-abl-', p0 + 10)
    p1 = len(h) if p1 == -1 else p1
    ind = "        "
    new = "\n".join((ind + ln) if ln.strip() else ln for ln in block.split("\n"))
    if BEGIN_H in h[p0:p1]:
        a = h.index(BEGIN_H, p0)
        b = h.index(END_H, a) + len(END_H)
    else:
        a = h.index('<div class="media media--placeholder">', p0)
        assert a < p1, "placeholder not inside #panel-abl-mcts"
        b = h.index("</div>", h.index("placeholder__text", a)) + len("</div>")
    a = h.rindex("\n", 0, a) + 1
    path.write_text(h[:a] + new + h[b:])


def patch_css(path, block):
    c = path.read_text()
    if BEGIN_C in c:
        a, b = c.index(BEGIN_C), c.index(END_C) + len(END_C)
        c = c[:a] + block + c[b:]
    else:
        c = c.rstrip("\n") + "\n\n" + block + "\n"
    path.write_text(c)


def frame_png(els, h, t):
    import cairosvg
    from PIL import Image
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VB_W} {h}" width="{VB_W}" height="{h}">'
           f'<rect width="100%" height="100%" fill="{SPACE}"/>'
           + "".join(render(e, "frame", t) for e in els) + "</svg>")
    return Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode()))).convert("RGB")


def frames(outdir, m_els, l_els, times):
    from PIL import Image, ImageDraw
    tiles = []
    for t in times:
        tile = Image.new("RGB", (VB_W, 22 + M_H + 6 + L_H), "white")
        d = ImageDraw.Draw(tile)
        d.text((8, 5), f"t = {t:.1f} s", fill=(20, 20, 20))
        tile.paste(frame_png(m_els, M_H, t), (0, 22))
        tile.paste(frame_png(l_els, L_H, t), (0, 22 + M_H + 6))
        tiles.append(tile)
    cols, gap = 4, 14
    rows = math.ceil(len(tiles) / cols)
    tw, th = tiles[0].size
    sheet = Image.new("RGB", (cols * tw + (cols - 1) * gap, rows * th + (rows - 1) * gap), (150, 156, 166))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % cols) * (tw + gap), (i // cols) * (th + gap)))
    outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / "search_ablation_frames.png"
    sheet.save(p)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", type=Path, default=DEF_HTML)
    ap.add_argument("--css", type=Path, default=DEF_CSS)
    ap.add_argument("--frames", type=Path)
    args = ap.parse_args()
    m_els, l_els = build_mcts(), build_linear()
    animated = list(walk(m_els)) + list(walk(l_els))
    ids = [x.uid for x in animated]
    assert len(ids) == len(set(ids)), "duplicate element ids"
    patch_html(args.html, html_block(m_els, l_els))
    cb = css_block(animated)
    patch_css(args.css, cb)
    print(f"{len(animated)} animated elements, css block {len(cb) / 1024:.1f} KB")
    if args.frames:
        times = [2.3, 3.6, 4.5, 5.9, 6.2, 6.6, 7.3, 8.4, 9.35, 10.1, 11.0, 12.0, 13.0, 14.6, 16.2, 17.0]
        print("frames:", frames(args.frames, m_els, l_els, times))


if __name__ == "__main__":
    main()
