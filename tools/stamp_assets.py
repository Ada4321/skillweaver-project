#!/usr/bin/env python3
"""Write ?v=<content hash> onto every local asset URL in index.html.

The preview server rewrites these on the fly, so during development a changed
stylesheet always arrives. Static hosting does not: GitHub Pages serves plain
URLs under `cache-control: max-age=600`, and a browser holding an older
js/nav.js will keep using it — which is how the page can be correct on disk,
byte-identical when fetched, and still behave like the previous version.

The stamp is a hash of the file's bytes, not its mtime, so re-encoding an asset
to identical output does not churn the URL and re-copying a file does not
invalidate a good cache entry.

Run after changing anything under css/, js/ or assets/, and before committing:

    python3 tools/stamp_assets.py
"""

import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "index.html")

# href/src/poster pointing at a local asset, with or without an existing stamp.
REF = re.compile(r'(?P<attr>\b(?:href|src|poster)=")'
                 r'(?P<path>(?:css|js|assets)/[^"?#]+)'
                 r'(?P<old>\?v=[0-9a-f]+)?"')


def digest(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:10]


def main():
    html = open(HTML, encoding="utf-8").read()
    changed, missing = [], []

    def stamp(m):
        target = os.path.join(ROOT, m["path"])
        if not os.path.isfile(target):
            missing.append(m["path"])
            return m[0]
        v = digest(target)
        if (m["old"] or "")[3:] != v:
            changed.append((m["path"], (m["old"] or "?v=—")[3:], v))
        return f'{m["attr"]}{m["path"]}?v={v}"'

    out = REF.sub(stamp, html)
    if out != html:
        open(HTML, "w", encoding="utf-8").write(out)

    for path, old, new in changed:
        print(f"  {old:>10} -> {new}  {path}")
    print(f"{len(changed)} stamp(s) updated, "
          f"{len(REF.findall(out))} local asset reference(s) total")
    if missing:
        print("MISSING (left unstamped):", ", ".join(sorted(set(missing))))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
