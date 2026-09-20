#!/usr/bin/env python3
"""Grouped bar charts in the page's chart idiom, for the generator scripts.

One builder, so the ablation charts, the real-world chart and the pick chart
all read the same way: baseline grey rising first, our spectrum ramp second,
values over the bars, recessive grid, axis titles carrying the units.

The caller supplies the numbers and the labels; everything else -- geometry,
the rise/pop delays, the gradient element, the accessible title/description --
comes from here. Colours stay in css/style.css: a chart's own ramp is keyed on
its class (`.chart--<name> .bar--ours { fill: url(#<gradient>); }`), since a
presentation attribute on the rect would lose to any CSS rule.
"""

RISE = 0.62
HOLD = 0.18
LABEL_LAG = RISE * 0.7


def _f(x):
    s = f"{x:.1f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def grouped_bars(*, name, gradient, groups, series, ylab, atitle, ymax,
                 grid, vb_w=620, vb_h=336, pad_l=56, pad_r=14, y_top=44, y_bot=254,
                 bar_w=34, bar_gap=6, fmt="%s", title=None, desc=None, indent=8,
                 legend=True):
    """One grouped bar chart as SVG lines.

    groups   x-axis labels, one per group (two-word labels wrap onto two lines)
    series   [{label, cls, values}] -- `cls` is bar--gt / bar--gt2 / bar--ours;
             the bars of a series rise together, later series after earlier ones.
             A single series may instead carry `cls_per_group`, one class per
             bar: that is a chart whose groups ARE the methods, so it needs no
             legend (pass legend=False).
    """
    x0, x1 = pad_l, vb_w - pad_r
    n = len(groups)
    k = len(series)
    # The legend wraps rather than running off the edge; every extra line pushes
    # the plot down by one line height.
    rows_of_keys, x = [[]], x0
    for s in (series if legend else []):
        w = 20 + 7.3 * len(s["label"]) + 26
        if rows_of_keys[-1] and x + w > x1:
            rows_of_keys.append([]); x = x0
        rows_of_keys[-1].append((x, s))
        x += w
    shift = 18 * (len(rows_of_keys) - 1)
    y_top, y_bot, vb_h = y_top + shift, y_bot + shift, vb_h + shift
    group_w = (x1 - x0) / float(n)
    pair_w = k * bar_w + (k - 1) * bar_gap
    first = x0 + (group_w - pair_w) / 2 + pair_w - bar_w / 2
    last = first + (n - 1) * group_w

    def y_of(v):
        return y_bot - v / float(ymax) * (y_bot - y_top)

    L = [f'<svg class="chart chart--sm chart--play chart--{name}" viewBox="0 0 {vb_w} {vb_h}" '
         f'role="img" aria-labelledby="{name}Title {name}Desc">',
         f'  <title id="{name}Title">{title}</title>',
         f'  <desc id="{name}Desc">{desc}</desc>',
         '  <defs>',
         f'    <linearGradient id="{gradient}" gradientUnits="userSpaceOnUse" '
         f'x1="{_f(first)}" y1="0" x2="{_f(last)}" y2="0">',
         '      <stop class="g-a" offset="0" />',
         '      <stop class="g-b" offset="1" />',
         '    </linearGradient>',
         '  </defs>',
         '  <g class="legend">']
    for row, keys in enumerate(rows_of_keys):
        for lx, s in keys:
            L += [f'    <rect class="bar {s["cls"]}" x="{_f(lx)}" y="{12 + 18 * row}" width="13" height="13" '
                  f'rx="3" />',
                  f'    <text class="key" x="{_f(lx + 20)}" y="{23 + 18 * row}">{s["label"]}</text>']
    if legend:
        L += ['  </g>']
    else:
        L = L[:L.index('  <g class="legend">')]
    L += ['  <g class="grid">']
    for v in grid:
        y = y_of(v)
        L += [f'    <line class="{"axis" if v == 0 else "rule"}" x1="{x0}" y1="{_f(y)}" x2="{x1}" y2="{_f(y)}" />',
              f'    <text class="tick" x="{x0 - 10}" y="{_f(y + 4)}">{v:g}</text>']
    L += ['  </g>',
          f'  <text class="ylab" transform="translate(16 {_f((y_top + y_bot) / 2)}) rotate(-90)">{ylab}</text>',
          '  <g class="bars">']
    for i, gname in enumerate(groups):
        gx = x0 + i * group_w
        bx = gx + (group_w - pair_w) / 2
        L.append('    <g>')
        for j, s in enumerate(series):
            v = s["values"][i]
            x = bx + j * (bar_w + bar_gap)
            d = (i if s.get("cls_per_group") else j) * (RISE + HOLD)
            s = dict(s, cls=s["cls_per_group"][i]) if s.get("cls_per_group") else s
            top = y_of(v)
            if v > 0:
                h = y_bot - top
                L.append(f'      <rect class="bar rise {s["cls"]}" x="{_f(x)}" y="{_f(top)}" width="{bar_w}" '
                         f'height="{_f(h)}" rx="{_f(min(3, h / 2))}" style="--d:{d:.2f}s" />')
            val_cls = s["cls"].replace("bar--", "val--")
            L.append(f'      <text class="val {val_cls} pop" x="{_f(x + bar_w / 2)}" y="{_f(top - 12)}" '
                     f'style="--d:{d + LABEL_LAG:.2f}s">{fmt % v}</text>')
        L.append(_xlab(gx + group_w / 2, y_bot + 22, gname))
        L.append('    </g>')
    L += ['  </g>',
          f'  <text class="atitle" x="{_f((x0 + x1) / 2)}" y="{y_bot + 66}">{atitle}</text>',
          '</svg>']
    pad = " " * indent
    return "\n".join(pad + s for s in L)


def _xlab(x, y, name):
    """Multi-word labels break onto a second line; a group is too narrow for one."""
    words = name.split()
    if len(words) <= 1:
        return f'      <text class="xlab" x="{_f(x)}" y="{y}">{name}</text>'
    return (f'      <text class="xlab" x="{_f(x)}" y="{y}"><tspan x="{_f(x)}">{words[0]}</tspan>'
            f'<tspan x="{_f(x)}" dy="14">{" ".join(words[1:])}</tspan></text>')
