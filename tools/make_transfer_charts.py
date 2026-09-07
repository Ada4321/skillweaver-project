#!/usr/bin/env python3
"""Generate the two sim-to-sim transfer charts, side by side.

These are fig:libero_fewshot and fig:simpler_zeroshot in the paper (Figures 4
and 5), printed there as a pair of small matplotlib panels. On the page they
are native SVG in the same hand as the other charts, so the section reads as
one set of figures rather than two screenshots.

Unlike the LIBERO-PRO charts these bars are categories, not a baseline against
ours: every bar is our data. They therefore take the spectrum ramp -- each bar
its own hue, all clearly one series -- and only the reference line stays grey,
because that one really is the baseline.

The ramp is one continuous sweep across the pair rather than a full sweep
repeated twice, which is what made the two panels look like the same picture:
the left chart runs teal to indigo and the right one picks up at indigo and
carries on to amber. Each gradient spans its own first and last bar CENTRES,
not the plot box, so the last bar on the left and the first bar on the right
land on exactly the same indigo and the seam does not jump.

Numbers come from the figures' own plotting script, transcribed once:

    /data/user_data/hez2/corl_build/plot_row_figs.py

Re-run after they change:

    python3 tools/make_transfer_charts.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "index.html")

RISE = 0.62       # matches the bar charts above; all bars climb together
LABEL = RISE * 0.7

VB_W, VB_H = 560, 314
PAD_L, PAD_R = 56, 14
Y_TOP, Y_BOT = 36, 252
Y_MAX = 112       # headroom above the 100 gridline for the value labels
GRID = (0, 25, 50, 75, 100)
BAR_MAX = 70

CHARTS = [
    dict(key="fewshot", grad="fewshotBar", stops=["g-a", "g-b"],
         title="Zero- and few-shot sim-to-sim transfer to LIBERO-Object",
         desc="Success rate on LIBERO-Object after training on SkillWeaver data "
              "with 0, 1 or 5 ground-truth demonstrations per task added, "
              "against a 50-demonstration ground-truth-only baseline.",
         labels=["0", "1", "5"], values=[66.0, 63.4, 82.2],
         xlabel="GT demos per task added to SW data",
         ref=95.0, ref_label="50 GT demos only"),
    dict(key="simpler", grad="simplerBar", stops=["g-b", "g-c"],
         title="Zero-shot transfer to SIMPLER-WidowX",
         desc="Zero-shot success rate on four SIMPLER-WidowX tasks after "
              "training on SkillWeaver data alone.",
         labels=["Eggplant", "Carrot", "Spoon", "Stack cube"],
         values=[91.7, 75.0, 62.5, 79.2],
         xlabel="SIMPLER-WidowX task", ref=None, ref_label=None),
]

X0, X1 = PAD_L, VB_W - PAD_R


def y_of(v):
    return Y_BOT - v / float(Y_MAX) * (Y_BOT - Y_TOP)


def build(c):
    n = len(c["values"])
    cat = (X1 - X0) / float(n)
    bw = min(BAR_MAX, cat * 0.5)
    first, last = X0 + 0.5 * cat, X1 - 0.5 * cat
    L = ['<svg class="chart chart--sm chart--play chart--%s" '
         'viewBox="0 0 %d %d" role="img" aria-labelledby="%sTitle %sDesc">'
         % (c["key"], VB_W, VB_H, c["key"], c["key"]),
         '  <title id="%sTitle">%s</title>' % (c["key"], c["title"]),
         '  <desc id="%sDesc">%s</desc>' % (c["key"], c["desc"]),
         '  <defs>',
         '    <linearGradient id="%s" gradientUnits="userSpaceOnUse" '
         'x1="%.1f" y1="0" x2="%.1f" y2="0">' % (c["grad"], first, last),
         '      <stop class="%s" offset="0" />' % c["stops"][0],
         '      <stop class="%s" offset="1" />' % c["stops"][1],
         '    </linearGradient>',
         '  </defs>',
         '  <g class="grid">']
    for v in GRID:
        y = y_of(v)
        L += ['    <line class="%s" x1="%d" y1="%.1f" x2="%d" y2="%.1f" />'
              % ("axis" if v == 0 else "rule", X0, y, X1, y),
              '    <text class="tick" x="%d" y="%.1f">%d</text>'
              % (X0 - 10, y + 4, v)]
    L += ['  </g>',
          '  <text class="ylab" transform="translate(16 %.1f) rotate(-90)">'
          'Success rate (%%)</text>' % ((Y_TOP + Y_BOT) / 2)]

    if c["ref"] is not None:
        # Left-anchored: the bars on this chart all sit well below the line,
        # and the right end is where the tallest one puts its value label.
        ry = y_of(c["ref"])
        L += ['  <g class="ref pop" style="--d:0.12s">',
              '    <line class="gtline" x1="%d" y1="%.2f" x2="%d" y2="%.2f" />'
              % (X0, ry, X1, ry),
              '    <text class="key" x="%d" y="%.2f">%s: %s%%</text>'
              % (X0 + 4, ry - 8, c["ref_label"], c["ref"]),
              '  </g>']

    L.append('  <g class="bars">')
    for i, (lab, v) in enumerate(zip(c["labels"], c["values"])):
        cx = X0 + (i + 0.5) * cat
        top = y_of(v)
        L += ['    <g>',
              '      <rect class="bar rise bar--ours" x="%.1f" y="%.2f" '
              'width="%.1f" height="%.2f" rx="3" />'
              % (cx - bw / 2, top, bw, Y_BOT - top),
              '      <text class="val val--ours pop" x="%.1f" y="%.2f" '
              'style="--d:%.2fs">%s%%</text>' % (cx, top - 12, LABEL, v),
              '      <text class="xlab" x="%.1f" y="%d">%s</text>'
              % (cx, Y_BOT + 22, lab),
              '    </g>']
    L += ['  </g>',
          '  <text class="atitle" x="%.1f" y="%d">%s</text>'
          % ((X0 + X1) / 2, Y_BOT + 48, c["xlabel"]),
          '</svg>']
    return "\n".join("          " + s for s in L)


def main():
    html = open(HTML, encoding="utf-8").read()
    for c in CHARTS:
        begin = ("          <!-- >>> %s CHART: generated by "
                 "tools/make_transfer_charts.py >>> -->" % c["key"].upper())
        end = "          <!-- <<< %s CHART <<< -->" % c["key"].upper()
        pat = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
        if not pat.search(html):
            sys.exit("markers for %s not found -- insert them first" % c["key"])
        html = pat.sub(lambda _: "%s\n%s\n%s" % (begin, build(c), end), html)
    open(HTML, "w", encoding="utf-8").write(html)

    for c in CHARTS:
        print("%-8s %s" % (c["key"], "  ".join(
            "%s %.1f%%" % (l, v) for l, v in zip(c["labels"], c["values"]))
            + ("   ref %s = %s%%" % (c["ref_label"], c["ref"])
               if c["ref"] is not None else "")))


if __name__ == "__main__":
    main()
