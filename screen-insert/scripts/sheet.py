#!/usr/bin/env python3
"""Contact sheet for reviewing composites.

usage: sheet.py OUT.jpg FILE [FILE ...] [--cols 5] [--tile 300] [--square] [--safe] [--labels]

--square  show only each image's centred 1:1 square (what a square crop of a 9:16 master shows)
--safe    show full frames with the centred 1:1 square outlined in red
--labels  print each file's name (up to the first underscore) in the corner
"""
import os, argparse
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument('out'); ap.add_argument('files', nargs='+')
ap.add_argument('--cols', type=int, default=5); ap.add_argument('--tile', type=int, default=300)
ap.add_argument('--square', action='store_true'); ap.add_argument('--safe', action='store_true')
ap.add_argument('--labels', action='store_true')
a = ap.parse_args()

tiles = []
for f in a.files:
    im = Image.open(f).convert('RGB'); w, h = im.size
    if a.square:
        s = min(w, h); im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
        im = im.resize((a.tile, a.tile), Image.LANCZOS)
    else:
        th = round(a.tile * h / w); im = im.resize((a.tile, th), Image.LANCZOS)
        if a.safe:
            d = ImageDraw.Draw(im); s = min(a.tile, th)
            d.rectangle(((a.tile - s) // 2, (th - s) // 2, (a.tile + s) // 2 - 1, (th + s) // 2 - 1), outline=(255, 40, 40), width=3)
    if a.labels:
        d = ImageDraw.Draw(im); t = os.path.basename(f).split('_')[0][:14]
        d.rectangle((0, 0, 8 + 7 * len(t), 20), fill='black'); d.text((4, 4), t, fill='white')
    tiles.append(im)
th = max(t.size[1] for t in tiles); rows = -(-len(tiles) // a.cols)
sheet = Image.new('RGB', (a.cols * a.tile, rows * th), 'white')
for i, t in enumerate(tiles):
    sheet.paste(t, ((i % a.cols) * a.tile, (i // a.cols) * th))
sheet.save(a.out, quality=88); print('ok', a.out, f'{len(tiles)} images')
