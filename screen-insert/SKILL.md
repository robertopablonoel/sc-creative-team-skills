---
name: screen-insert
description: Put footage onto green (#00FF00) screens in rendered frames — TVs, CRTs, phones, laptops. Use when a storyboard or ad frame has a chroma-key screen that needs content keyed in, when footage should look like it is playing on an old picture tube (scanlines, hum bars, ghosting), for nested screens (a phone playing inside a TV), for a pull-back reveal from a screen out to the person holding it, or to audit which frames still have green screens.
---

# Screen insert

Deterministic keying of footage into #00FF00 screen areas, with an optional period picture-tube look. Python with numpy + Pillow; OpenCV (`opencv-python-headless`) for the perspective warp on tilted screens; scipy for `--region`.

## Setup (once per machine)

```bash
python3 -m venv ~/.venvs/creative-skills
~/.venvs/creative-skills/bin/pip install numpy pillow opencv-python-headless scipy
```

Run every script with `~/.venvs/creative-skills/bin/python` (system Python usually lacks these packages).

## Scripts (`scripts/`)

| Script | Does |
|---|---|
| `screen_insert.py BASE INSERT OUT` | Keys INSERT into BASE's green screen. `--look crt` (default) or `flat`. |
| `find_keys.py PATH...` | Lists every image that still has a green area: box, fill ratio, number of separate screens. |
| `pullback.py FRAME INSERT PREFIX` | Tight-to-wide square crops of a frame with a green device, the insert keyed sharp into each; `--plate TV` puts every step on a TV. |
| `sheet.py OUT.jpg FILES...` | Contact sheet. `--square` shows each frame's centred 1:1 crop, `--safe` outlines it. |

Run `~/.venvs/creative-skills/bin/python scripts/<name>.py -h` for every option.

## Workflow

1. **Audit.** `find_keys.py frames/` to see what still needs a screen. Fill well under ~0.85 means the screen is tilted or partly covered. Flat screens like that get a four-corner perspective warp automatically (`--warp auto`); fingers over the screen can pull a corner off, so check those, and flag strong angles for proper tracking in post. `areas` > 1 means several screens: key them one at a time with `--region N` (counted left to right), highest index first so the numbering doesn't shift.
2. **Pick the look.**
   - Old TV / CRT / monitor in a period scene: `--look crt`. `--grit` sets signal damage: 0 clean tube, 0.5 default (subtle), 1.0 heavy. Keep one grit value across a project.
   - Phones and modern screens: `--look flat --spill 0.06`. For UI screenshots, use `--fit auto` (or `stretch`) so captions and icons aren't cropped off; the default `cover` crops to the screen's shape, better for photographic footage.
   - Black-and-white plates: add `--edge gray`. Colour plates: keep the default `despill`.
3. **Frame the crop.** `--focus` (vertical) and `--xfocus` (horizontal), 0 = top/left, 1 = bottom/right. Check faces aren't cut.
4. **Nesting.** Key the inner screen first with `--look flat`, then use that output as the INSERT for the outer screen.
5. **Continuity across a cut.** CRT damage is seeded from the insert's file name. For shots that cut together on the same set, pass the same `--seed` so hum bars and the tear hold still.
6. **Review.** Always build a `sheet.py` contact sheet and look at it before delivering. Zoom into screen edges on tight crops; if a green line survives, raise `--ring`.

## Consistency rule worth adopting

When the story beat *is* what's on a screen, use one frontal plate of that screen, framed so the screen fills the middle 1:1 square of the 9:16 master, and key every insert into that same plate. Reaction beats can stay wide with the screen keyed in. For phone hero shots, aim for the phone at ~85–90% of the middle square's height: big screen, still inside the square-crop safe area.

## Gotchas

- Keys pure green only (`g > 120` and `g - max(r, b) > 60`). Phosphor-green "glow" props won't key; render key props as flat #00FF00.
- In shell loops, run with `</dev/null` if any step calls ffmpeg, and use bash (zsh does not word-split `$var`).
- Scaling a small screen up (pull-backs) smears green further; `pullback.py` widens the cleaned edge automatically.
