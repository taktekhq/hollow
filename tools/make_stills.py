#!/usr/bin/env python3
"""Pulls the 1600x1000 stills and the cover out of the rendered takes (raw CLI
frames, no overlays), so the stills always match the video.

    ~/venvs/pw/bin/python tools/make_stills.py /tmp/hollow_frames
"""
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, 'media')

# (take, frame at 30 fps, file)
PICKS = [
    ('carve', 960, 'hollow-hero.png'),       # lit, rays, and the eyes on the wall
    ('carve', 330, 'hollow-carving.png'),    # moonlight, knife mid-stroke on the mouth
    ('carve', 1262, 'hollow-snuffed.png'),   # snuffed: smoke, the eyes stay
    ('mash', 440, 'hollow-mashrabiya.png'),  # the mashrabiya stencil, lit
    ('ghoul', 290, 'hollow-ghoul.png'),      # cut + etch stencil, lit
]


def nearest(frames_dir, take, k):
    for d in range(0, 30):
        for kk in (k - d, k + d):
            p = os.path.join(frames_dir, take, f'{kk:05d}.png')
            if os.path.exists(p):
                return p
    raise SystemExit(f'no frame near {take} {k}')


def main():
    frames_dir = sys.argv[1]
    os.makedirs(MEDIA, exist_ok=True)
    for take, k, name in PICKS:
        img = Image.open(nearest(frames_dir, take, k)).convert('RGB')
        img.save(os.path.join(MEDIA, name), optimize=True)
        if name == 'hollow-hero.png':
            img.save(os.path.join(MEDIA, 'hero.jpg'), quality=90, optimize=True, progressive=True)
        print('wrote', name)


if __name__ == '__main__':
    main()
