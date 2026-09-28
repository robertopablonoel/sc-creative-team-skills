#!/usr/bin/env python3
"""Key footage into the #00FF00 screen of a frame.

usage:
  screen_insert.py BASE INSERT OUT [--look crt|flat] [--focus 0.5] [--xfocus 0.5]
                   [--spill 0.10] [--grit 0.5] [--seed N] [--region N] [--edge despill|gray]

BASE    image containing a pure-green (#00FF00) screen area
INSERT  footage to put on the screen (center-cropped to the screen's aspect)
OUT     output path

--look crt    old picture-tube look: barrel curve, scanlines, bloom, glass sheen, edge falloff,
              plus signal damage scaled by --grit (hum bars, ghost, row jitter, tear, grain).
--look flat   clean fit, no treatment (phones, laptops, modern screens).
--focus/--xfocus  where the crop sits in the insert, 0 = top/left, 1 = bottom/right.
--spill       faint colour glow from the screen onto its surroundings (0 = off).
--grit        0 = clean tube, 0.5 = default, 1.0 = heavy damage. crt only.
--seed        fixes where hum bars and the tear land; defaults to a hash of the insert's
              file name, so a given insert always renders the same way.
--region N    use only the Nth green area, counted left to right (needs scipy). For frames
              with more than one screen.
--edge        despill (default): neutralise green on the matte edge, keeps colour plates in colour.
              gray: grayscale the matte edge (for black-and-white plates).

--fit MODE     cover (default): crop the insert to the screen's shape. stretch: squeeze it to
              fit, keeping everything (UI, captions). auto: stretch if the shapes differ by at most 12%.
--warp MODE    auto (default): flat screens that aren't square to camera (key fills < 88% of its
              box) get a four-corner perspective warp so the insert follows the tilt (needs
              opencv-python-headless). on / off to force.
--ring PX     width of the cleaned edge band (default 9; raise it for upscaled plates).

Also importable: composite(base_img, insert_img, **opts) -> (PIL.Image, (x, y, w, h)).
"""
import os, sys, argparse, zlib
import numpy as np
from PIL import Image, ImageFilter


def key_mask(B, region=None):
    """Boolean mask of pure-green pixels; optionally a single connected area."""
    r, g, b = B[..., 0], B[..., 1], B[..., 2]
    key = (g > 120) & (g - np.maximum(r, b) > 60)
    if region is None:
        return key
    try:
        from scipy import ndimage
    except ImportError:
        sys.exit('--region needs scipy (pip install scipy)')
    lab, n = ndimage.label(key)
    comps = [i for i in range(1, n + 1) if (lab == i).sum() >= 1000]
    comps.sort(key=lambda i: np.nonzero(lab == i)[1].min())
    if region >= len(comps):
        sys.exit(f'--region {region}: only {len(comps)} green areas found')
    return lab == comps[region]


def quad_corners(key):
    """Exact corners (tl, tr, br, bl) of a possibly tilted, round-cornered screen.

    OpenCV: convex hull of the key (it bridges straight across fingers over the screen),
    minAreaRect for the screen's rough axes, then every hull edge is assigned to the side
    whose outward normal it matches (within 25 degrees; rounded-corner and corner-cutting
    edges fall outside that and are ignored). Each side is a length-weighted robust line
    fit (cv2.fitLine, Huber) through its edges; neighbouring sides intersect at the corners.
    """
    import cv2
    k = cv2.morphologyEx(key.astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cs, _ = cv2.findContours(k, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    hull = cv2.convexHull(max(cs, key=cv2.contourArea)).reshape(-1, 2).astype(np.float64)
    box = cv2.boxPoints(cv2.minAreaRect(hull.astype(np.float32))).astype(np.float64)
    ctr = hull.mean(axis=0)
    a1 = (box[1] - box[0]) / np.linalg.norm(box[1] - box[0])
    a2 = (box[2] - box[1]) / np.linalg.norm(box[2] - box[1])
    normals = [a1, -a1, a2, -a2]
    buckets = [[] for _ in range(4)]
    for i in range(len(hull)):
        p, q = hull[i], hull[(i + 1) % len(hull)]
        L = np.linalg.norm(q - p)
        if L < 1:
            continue
        d = (q - p) / L; n = np.array([d[1], -d[0]])
        if (p + q) / 2 @ n - ctr @ n < 0:
            n = -n                                            # make it point outward
        j = int(np.argmax([n @ m for m in normals]))
        if n @ normals[j] > np.cos(np.radians(25)):
            steps = max(2, int(L // 2))
            buckets[j].extend(p + (q - p) * t for t in np.linspace(0, 1, steps))
    sides = []
    for j in range(4):
        n = normals[j]
        if len(buckets[j]) >= 4:
            vx, vy, x0, y0 = cv2.fitLine(np.float32(buckets[j]), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
            sides.append((n, np.array([x0, y0]), np.array([vx, vy])))
        else:                                                 # fall back to the bounding rect side
            proj = box @ n; e = box[np.argsort(proj)[-2:]]
            sides.append((n, e[0], (e[1] - e[0]) / np.linalg.norm(e[1] - e[0])))
    def meet(s1, s2):
        (_, p1, d1), (_, p2, d2) = s1, s2
        t = np.linalg.solve(np.array([d1, -d2]).T, p2 - p1)
        return p1 + t[0] * d1
    # order sides by normal angle (image coords: up -90, right 0, down 90, left 180) starting at the top
    ang = [np.arctan2(s[0][1], s[0][0]) for s in sides]
    order = sorted(range(4), key=lambda i: ang[i])
    top = min(range(4), key=lambda j: abs(np.angle(np.exp(1j * (ang[order[j]] + np.pi / 2)))))
    up, right, down, left = [sides[order[(top + j) % 4]] for j in range(4)]
    return np.array([meet(up, left), meet(up, right), meet(down, right), meet(down, left)])


def fit(ins, W, H, focus=0.5, xfocus=0.5, pad=1.0, mode='cover'):
    iw, ih = ins.size
    tgt = W / H
    if mode == 'stretch' or (mode == 'auto' and abs((iw / ih) / tgt - 1) <= 0.12):
        return ins.resize((int(W * pad), int(H * pad)), Image.LANCZOS)   # keeps captions and UI edges
    if iw / ih > tgt:
        nw = int(ih * tgt); left = int((iw - nw) * xfocus); box = (left, 0, left + nw, ih)
    else:
        nh = int(iw / tgt); top = int((ih - nh) * focus); box = (0, top, iw, top + nh)
    return ins.crop(box).resize((int(W * pad), int(H * pad)), Image.LANCZOS)


def tube(C, W, H, yy, xx, u, v, rr, grit, rng):
    """Picture-tube treatment and signal damage, in place of a clean image."""
    if grit > 0:
        g_ = grit
        lo = Image.fromarray((C * 255).astype(np.uint8)).resize(
            (max(1, int(W * (1 - 0.58 * g_))), max(1, int(H * (1 - 0.64 * g_)))), Image.BILINEAR)
        C = np.asarray(lo.resize((W, H), Image.BICUBIC)).astype(np.float32) / 255.0
        lum = C.mean(axis=2, keepdims=True)
        C = lum + (C - lum) * (1 - 0.28 * g_)                               # washed colour
        C = C * np.array([1.0, 1.02, 0.94]) * (1 - 0.12 * g_) + 0.06 * g_   # phosphor tint, lifted blacks
        gs = max(3, W // 70)                                                # multipath ghost
        C[:, gs:] = C[:, gs:] * (1 - 0.2 * g_) + C[:, :-gs] * 0.2 * g_
        jit = (rng.normal(0, 1.0, H) * g_).astype(np.int32)                 # row jitter
        tear = int(rng.uniform(0.55, 0.9) * H); tl = max(4, H // 40)
        jit[tear:tear + tl] += (np.linspace(W * 0.03, 0, len(jit[tear:tear + tl])) * g_).astype(np.int32)
        cols = np.clip(np.arange(W)[None, :] - jit[:, None], 0, W - 1)
        C = C[np.arange(H)[:, None], cols]
        ph = rng.uniform(0, 1)                                              # rolling hum bar
        hum = 1 - 0.30 * g_ * np.clip(np.sin(2 * np.pi * (yy / H * 1.7 + ph)), 0, 1) ** 1.5
        bright = np.exp(-((yy / H - rng.uniform(0.15, 0.85)) ** 2) / 0.0004) * 0.14 * g_
        thin = np.zeros(H); thin[rng.integers(0, H, 6)] = rng.uniform(-0.25, 0.25, 6) * g_
        bright = bright + np.convolve(thin, np.ones(3) / 1.5, 'same')[:, None]
        C = C * hum[..., None] + bright[..., None]
        C = C + rng.normal(0, 0.035 * g_, (H, W, 1)) + rng.normal(0, 0.015 * g_, (H, 1, 1))
        C = np.clip(C, 0, 1)
    shift = np.clip((np.abs(u) ** 2) * 2.0, 0, 2).astype(np.int32)            # chromatic fringe
    yi, xi = yy.astype(np.int32), xx.astype(np.int32)
    C[..., 0] = C[yi, np.clip(xi + shift, 0, W - 1), 0]
    C[..., 2] = C[yi, np.clip(xi - shift, 0, W - 1), 2]
    line_h = max(2, H // 300)                                                 # scanlines
    C = C * (1 - (0.08 + 0.10 * grit) * ((yy // (line_h / 2)) % 2))[..., None]
    C = C * np.clip(1 - 0.35 * (rr ** 1.6), 0.45, 1)[..., None]               # edge falloff
    hot = Image.fromarray((np.clip(C, 0, 1) * 255).astype(np.uint8)).point(lambda p: max(0, p - 170) * 3)
    bloom = np.asarray(hot.filter(ImageFilter.GaussianBlur(max(4, W // 60)))).astype(np.float32) / 255.0
    C = 1 - (1 - C) * (1 - 0.55 * bloom)
    sheen = np.clip(1 - ((u + 0.55) ** 2 + (v + 0.65) ** 2) / 0.35, 0, 1) * 0.10
    return np.clip(C + sheen[..., None], 0, 1)


def composite(base, insert, look='crt', focus=0.5, xfocus=0.5, spill=0.10, grit=0.5,
              seed=None, region=None, edge='despill', seed_key='', ring_px=9, fit_mode='cover', warp='auto'):
    B = np.asarray(base.convert('RGB')).astype(np.float32)
    key = key_mask(B, region)
    ys, xs = np.nonzero(key)
    if len(xs) < 1000:
        raise ValueError('no #00FF00 area found')
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    W, H = x1 - x0, y1 - y0

    m = Image.fromarray((key * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    M = np.asarray(m.filter(ImageFilter.GaussianBlur(1.5))).astype(np.float32)[..., None] / 255.0

    crt = look == 'crt'
    fill = key.sum() / float(W * H)
    if warp == 'on' or (warp == 'auto' and not crt and fill < 0.88):
        q = quad_corners(key)
        qw = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
        qh = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
        src = fit(insert.convert('RGB'), max(2, int(qw)), max(2, int(qh)), focus, xfocus, 1.0, fit_mode)
        sw, sh = src.size
        import cv2
        Hm = cv2.getPerspectiveTransform(np.float32([[0, 0], [sw, 0], [sw, sh], [0, sh]]), np.float32(q))
        canvas = cv2.warpPerspective(np.asarray(src), Hm, base.size, flags=cv2.INTER_LANCZOS4,
                                     borderMode=cv2.BORDER_REPLICATE).astype(np.float32) / 255.0
        return _blend(B, M, m, canvas, spill, edge, ring_px, W), (x0, y0, W, H)
    pad = 1.06 if crt else 1.0            # overscan so the barrel curve never shows an edge
    I = np.asarray(fit(insert.convert('RGB'), W, H, focus, xfocus, pad, fit_mode)).astype(np.float32) / 255.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    u = (xx / (W - 1)) * 2 - 1; v = (yy / (H - 1)) * 2 - 1
    rr = u * u + v * v
    k = 0.06 if crt else 0.0
    px = np.clip(((u * (1 - k * rr) / pad + 1) / 2) * (I.shape[1] - 1), 0, I.shape[1] - 1).astype(np.int32)
    py = np.clip(((v * (1 - k * rr) / pad + 1) / 2) * (I.shape[0] - 1), 0, I.shape[0] - 1).astype(np.int32)
    C = I[py, px]
    if crt:
        rng = np.random.default_rng(zlib.crc32(seed_key.encode()) if seed is None else seed)
        C = tube(C, W, H, yy, xx, u, v, rr, grit, rng)

    canvas = np.zeros_like(B)
    canvas[y0:y1, x0:x1] = C
    return _blend(B, M, m, canvas, spill, edge, ring_px, W), (x0, y0, W, H)


def _blend(B, M, m, canvas, spill, edge, ring_px, W):
    Bn = B / 255.0
    # matte edge plus a few pixels: upscaled or soft plates smear green past the key
    ring = np.asarray(m.filter(ImageFilter.MaxFilter(ring_px | 1))).astype(np.float32)[..., None] > 0
    if edge == 'gray':
        Bn = np.where(ring, Bn.mean(axis=2, keepdims=True), Bn)
    else:
        mx = np.maximum(Bn[..., 0], Bn[..., 2])
        Bn[..., 1] = np.where(ring[..., 0] & (Bn[..., 1] > mx), mx, Bn[..., 1])
    out = Bn * (1 - M) + canvas * M
    if spill > 0:
        glow = Image.fromarray((canvas * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(20, W // 10)))
        G = np.asarray(glow).astype(np.float32) / 255.0
        out = out + (1 - M) * G * spill * (0.4 + out.mean(axis=2, keepdims=True))
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('base'); ap.add_argument('insert'); ap.add_argument('out')
    ap.add_argument('--look', choices=['crt', 'flat'], default='crt')
    ap.add_argument('--flat', action='store_true', help='same as --look flat')
    ap.add_argument('--focus', type=float, default=0.5)
    ap.add_argument('--xfocus', type=float, default=0.5)
    ap.add_argument('--spill', type=float, default=0.10)
    ap.add_argument('--grit', type=float, default=0.5)
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--region', type=int, default=None)
    ap.add_argument('--edge', choices=['despill', 'gray'], default='despill')
    ap.add_argument('--ring', type=int, default=9)
    ap.add_argument('--fit', choices=['cover', 'stretch', 'auto'], default='cover')
    ap.add_argument('--warp', choices=['auto', 'on', 'off'], default='auto')
    a = ap.parse_args()
    img, box = composite(Image.open(a.base), Image.open(a.insert), 'flat' if a.flat else a.look,
                         a.focus, a.xfocus, a.spill, a.grit, a.seed, a.region, a.edge,
                         seed_key=os.path.basename(a.insert), ring_px=a.ring, fit_mode=a.fit, warp=a.warp)
    img.save(a.out)
    print('ok', a.out, 'screen', box)


if __name__ == '__main__':
    main()
