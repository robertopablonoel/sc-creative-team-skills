#!/usr/bin/env python3
"""Pull-back reveal: footage fills the frame, then the camera pulls out to show it on a device.

usage:
  pullback.py FRAME INSERT OUT_PREFIX [--plate TV_PLATE] [--steps 480,900,full]
              [--focus 0.4] [--grit 0.5] [--seed N] [--size 1600]

FRAME    wide shot with a green device screen (e.g. a phone in someone's hand)
INSERT   the footage playing on that device
OUT_PREFIX  writes OUT_PREFIX_a.png, _b.png, ... one per step

Each step is a square crop of FRAME, starting tight on the device and ending wide.
The insert is keyed in *after* cropping, at output resolution, so it stays sharp
even in the tight steps. Green edge pixels are cleaned (despill).

--steps     crop sizes in source pixels, tight to wide; 'full' = the frame's centred square.
            The crop centre moves from the device to the frame's middle as it widens,
            so 'full' lands exactly on the middle 1:1 square.
--plate     a frame with its own green screen (e.g. a TV): every step is then keyed
            onto it with the crt look, all with the same --seed so the damage holds still
            across the cut. Without --plate the steps are written as-is.
"""
import os, argparse
from PIL import Image
import numpy as np
from screen_insert import composite, key_mask

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('frame'); ap.add_argument('insert'); ap.add_argument('out_prefix')
ap.add_argument('--plate'); ap.add_argument('--steps', default='480,900,full')
ap.add_argument('--focus', type=float, default=0.4)
ap.add_argument('--grit', type=float, default=0.5)
ap.add_argument('--seed', type=int, default=None)
ap.add_argument('--size', type=int, default=1600, help='working resolution of each step')
a = ap.parse_args()

frame = Image.open(a.frame).convert('RGB'); fw, fh = frame.size
ins = Image.open(a.insert).convert('RGB')
ys, xs = np.nonzero(key_mask(np.asarray(frame).astype(np.float32)))
dcx, dcy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2       # device centre
side = min(fw, fh); fcx, fcy = fw / 2, fh / 2                          # frame's middle square
steps = [side if s == 'full' else int(s) for s in a.steps.split(',')]
seed = a.seed if a.seed is not None else 26
for i, s in enumerate(steps):
    t = 0 if len(steps) == 1 else (s - steps[0]) / max(1, side - steps[0])
    t = min(max(t, 0), 1)
    cx, cy = dcx + (fcx - dcx) * t, dcy + (fcy - dcy) * t
    l = int(min(max(cx - s / 2, 0), fw - s)); tp = int(min(max(cy - s / 2, 0), fh - s))
    crop = frame.crop((l, tp, l + s, tp + s)).resize((a.size, a.size), Image.LANCZOS)
    ring = max(9, int(a.size / s * 5))          # the upscale smears green further in tight steps
    step, _ = composite(crop, ins, look='flat', focus=a.focus, spill=0.06, ring_px=ring)
    tag = chr(ord('a') + i)
    if a.plate:
        step, _ = composite(Image.open(a.plate), step, look='crt', grit=a.grit, seed=seed, edge='gray')
    out = f'{a.out_prefix}_{tag}.png'; step.save(out)
    print('ok', out, 'crop', (l, tp, s))
