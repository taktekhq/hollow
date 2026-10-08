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
# (take, frame, file, zoom): lit frames have the panel tucked away, so they are framed
# tighter on the pumpkin and the wall (cut from the 1920x1200 render, no upscaling)
PICKS = [
    ('carve', 960, 'hollow-hero.png', 1.2),        # lit, rays, and the face on the wall, awake
    ('carve', 330, 'hollow-carving.png', 1.0),     # moonlight, knife mid-stroke
    ('carve', 1195, 'hollow-snuffed.png', 1.0),    # snuffed: smoke, and the eyes stay on the wall
    ('mash', 440, 'hollow-mashrabiya.png', 1.2),   # the mashrabiya stencil, lit
    ('ghoul', 290, 'hollow-ghoul.png', 1.2),       # cut + etch stencil, lit
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
    for take, k, name, z in PICKS:
        img = Image.open(nearest(frames_dir, take, k)).convert('RGB')
        sc = img.size[0] / 1280
        ww, wh = 1280 / z, 800 / z
        x0 = min(max(500 - ww / 2, 0), 1280 - ww)
        box = (x0 * sc, 0, (x0 + ww) * sc, wh * sc)
        img = img.resize((1600, 1000), Image.LANCZOS, box=box)
        img.save(os.path.join(MEDIA, name), optimize=True)
        if name == 'hollow-hero.png':
            img.save(os.path.join(MEDIA, 'hero.jpg'), quality=90, optimize=True, progressive=True)
        print('wrote', name)


if __name__ == '__main__':
    main()
