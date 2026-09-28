#!/usr/bin/env python3
"""List every image that still has a #00FF00 key area, with where it is.

usage: find_keys.py PATH [PATH ...] [--json]

PATH can be files or folders (non-recursive; skips _old/ and _ungraded/).
Per image: size, key box (x, y, w, h), fill ratio of that box, and the number of
separate green areas (needs scipy; otherwise '?'). Fill well below ~0.85 usually means
the screen is angled or partly covered; more than one area means use --region.
"""
import os, sys, json, glob
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
from screen_insert import key_mask

if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
    print(__doc__); sys.exit(0)
args = [x for x in sys.argv[1:] if x != '--json']
files = []
for p in args:
    if os.path.isdir(p):
        files += sorted(f for f in glob.glob(os.path.join(p, '*')) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')))
    else:
        files.append(p)
try:
    from scipy import ndimage
except ImportError:
    ndimage = None
rows = []
for f in files:
    B = np.asarray(Image.open(f).convert('RGB')).astype(np.float32)
    k = key_mask(B)
    if k.sum() < 1000:
        continue
    ys, xs = np.nonzero(k)
    x, y, w, h = int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
    areas = '?'
    if ndimage is not None:
        lab, n = ndimage.label(k)
        areas = int(sum((lab == i).sum() >= 1000 for i in range(1, n + 1)))
    rows.append(dict(file=os.path.basename(f), size=[B.shape[1], B.shape[0]], box=[x, y, w, h],
                     fill=round(float(k.sum()) / (w * h), 2), areas=areas))
if '--json' in sys.argv:
    print(json.dumps(rows, indent=1))
else:
    for r in rows:
        print(f"{r['file']:<50} box={tuple(r['box'])} fill={r['fill']} areas={r['areas']}")
    print(f'{len(rows)} of {len(files)} images have a key area')
