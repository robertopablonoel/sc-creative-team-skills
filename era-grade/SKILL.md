---
name: era-grade
description: Apply named, versioned colour grades ("looks") to image frames from untouched masters, so grades never stack and a look can be retuned and re-applied to everything. Use when a project has per-era or per-world looks (e.g. a 1957 black-and-white, a muted present day), when the user asks to regrade, warm up, desaturate or re-filter a set of frames, or to compare before/after grades.
---

# Era grade

A look registry plus one script. Needs ffmpeg; `--compare` needs Pillow.

## Environment (once per machine)

```bash
python3 -m venv ~/.venvs/creative-skills
~/.venvs/creative-skills/bin/pip install numpy pillow opencv-python-headless scipy
```

Run every script with `~/.venvs/creative-skills/bin/python` (system Python usually lacks these packages).

## Setup

Copy `looks.example.json` to the project as `looks.json` (or point `LOOKS_FILE` at it) and edit the looks. Each look has a `version`, `notes`, and either `filter` (an ffmpeg `-vf` chain) or `filter_complex` (a graph whose input is `[0]`). Keep old versions under `history` with a one-line `why`.

## Use

```bash
~/.venvs/creative-skills/bin/python scripts/grade.py --list
~/.venvs/creative-skills/bin/python scripts/grade.py 2027 frames/frame07.png frames/frame09.png --compare before_after.jpg
~/.venvs/creative-skills/bin/python scripts/grade.py --restore frames/frame07.png      # back to the master
```

- First grade of a file copies the original to `<dir>/_ungraded/`. Every later grade starts from that master, so re-running is safe and a retuned look simply re-applies.
- Each grade is logged to `<dir>/_ungraded/grades.log` (time, file, look, version).
- `--dry-run` shows what would happen.

## Retuning a look

1. Make a comparison first: grade two or three representative frames with `--compare`, look at it.
2. Change the numbers in `looks.json`, bump `version`, move the old filter into `history` with why.
3. Re-run the look on every file that uses it (grep `grades.log` for the look name to find them).
4. Rebuild anything downstream (composites, thumbnails) — a grade change does not propagate by itself.

## Gotchas

- Never grade a file that was produced some other way and already carries a look, unless you want the look applied twice: its "master" will be the already-graded image. Check `_ungraded/` first.
- Don't grade chroma-key plates with a look that shifts green; use a keep-green variant (see the example `1957-keep-green`).
- Render → grade → composite, in that order. Composites made before a regrade are stale.
