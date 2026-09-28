#!/usr/bin/env python3
"""Apply a named, versioned look to images, always from the untouched master.

usage:
  grade.py LOOK FILE [FILE ...] [--looks looks.json] [--compare OUT.jpg] [--dry-run]
  grade.py --list [--looks looks.json]
  grade.py --restore FILE [FILE ...]          put the ungraded master back

Looks live in a JSON registry (default: ./looks.json, or $LOOKS_FILE):
  {"looks": {"2027": {"version": 2, "filter": "eq=saturation=0.68:...",
                      "notes": "...", "history": [{"version": 1, "filter": "...", "why": "too muted"}]}}}
A look uses either "filter" (an ffmpeg -vf chain) or "filter_complex" (an ffmpeg graph whose
input is [0] and whose last output is the result).

Masters: the first time a file is graded, the original is copied to <dir>/_ungraded/<name>.
Every later grade starts from that master, so grades never stack and changing a look is just
re-running it. Each graded file gets a sidecar line in <dir>/_ungraded/grades.log.
--compare writes a before/after sheet (master | graded) of up to 6 of the files.
Needs ffmpeg on PATH; --compare needs Pillow.
"""
import os, sys, json, shutil, subprocess, argparse, datetime


def load(path):
    path = path or os.environ.get('LOOKS_FILE') or 'looks.json'
    if not os.path.exists(path):
        sys.exit(f'no looks registry at {path} (pass --looks or set LOOKS_FILE)')
    with open(path) as f:
        return json.load(f)['looks'], path


def master_of(f):
    d, b = os.path.split(os.path.abspath(f))
    return os.path.join(d, '_ungraded', b)


def apply(look, src, dst):
    tmp = dst + '.tmp' + os.path.splitext(dst)[1]
    cmd = ['ffmpeg', '-loglevel', 'error', '-y', '-i', src]
    cmd += ['-filter_complex', look['filter_complex']] if 'filter_complex' in look else ['-vf', look['filter']]
    subprocess.run(cmd + [tmp], check=True, stdin=subprocess.DEVNULL)   # ffmpeg must not eat stdin in loops
    os.replace(tmp, dst)


def compare(files, out):
    from PIL import Image
    tiles = []
    for f in files[:6]:
        a, b = Image.open(master_of(f)).convert('RGB'), Image.open(f).convert('RGB')
        h = 480; w = round(a.width * h / a.height)
        pair = Image.new('RGB', (w * 2 + 8, h), 'white')
        pair.paste(a.resize((w, h)), (0, 0)); pair.paste(b.resize((w, h)), (w + 8, 0))
        tiles.append(pair)
    sheet = Image.new('RGB', (max(t.width for t in tiles), sum(t.height + 8 for t in tiles)), 'white')
    y = 0
    for t in tiles:
        sheet.paste(t, (0, y)); y += t.height + 8
    sheet.save(out, quality=88); print('compare', out, '(left = master, right = graded)')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('look', nargs='?'); ap.add_argument('files', nargs='*')
    ap.add_argument('--looks'); ap.add_argument('--compare'); ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--list', action='store_true'); ap.add_argument('--restore', action='store_true')
    a = ap.parse_args()

    if a.restore:
        for f in [a.look] + a.files:
            m = master_of(f)
            if os.path.exists(m):
                shutil.copy2(m, f); print('restored', f)
            else:
                print('no master for', f)
        return
    looks, path = load(a.looks)
    if a.list or not a.look:
        for k, v in looks.items():
            print(f"{k:<22} v{v.get('version', 1)}  {v.get('notes', '')}")
        return
    if a.look not in looks:
        sys.exit(f"unknown look '{a.look}'; have: {', '.join(looks)}")
    look = looks[a.look]
    for f in a.files:
        m = master_of(f)
        if a.dry_run:
            print('would grade', f, 'from', m if os.path.exists(m) else '(new master)'); continue
        os.makedirs(os.path.dirname(m), exist_ok=True)
        if not os.path.exists(m):
            shutil.copy2(f, m)
        apply(look, m, f)
        with open(os.path.join(os.path.dirname(m), 'grades.log'), 'a') as log:
            log.write(f"{datetime.datetime.now().isoformat(timespec='seconds')}\t{os.path.basename(f)}\t{a.look}\tv{look.get('version', 1)}\n")
        print('graded', f, f"({a.look} v{look.get('version', 1)})")
    if a.compare and a.files and not a.dry_run:
        compare(a.files, a.compare)


if __name__ == '__main__':
    main()
