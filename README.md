# sc-creative-team-skills

Claude skills for the creative team. Each folder is one skill: a `SKILL.md` that tells Claude when and how to use it, plus the scripts it runs.

| Skill | Use it for |
|---|---|
| [`screen-insert`](screen-insert/SKILL.md) | Keying footage onto #00FF00 screens (TVs, CRTs, phones), period picture-tube look, perspective warp for tilted phones, nested screens, pull-back reveals, green-screen audits, contact sheets. |
| [`era-grade`](era-grade/SKILL.md) | Named, versioned colour looks applied from untouched masters, with before/after comparisons. |

## Install

Copy (or symlink) a skill folder into `~/.claude/skills/` for personal use, or into a project's `.claude/skills/` to share it with everyone working in that repo.

```bash
ln -sfn "$PWD/screen-insert" ~/.claude/skills/screen-insert
ln -sfn "$PWD/era-grade" ~/.claude/skills/era-grade
python3 -m venv ~/.venvs/creative-skills
~/.venvs/creative-skills/bin/pip install numpy pillow opencv-python-headless scipy
```

Requirements: Python 3 with `numpy`, `Pillow` and `opencv-python-headless` (`scipy` optional, for multi-screen frames), and `ffmpeg` on PATH for `era-grade`.
