#!/usr/bin/env python3
"""Cuts the demo film (1600x1000, about 57 s) from the frames tools/render_take.py
renders, following the cut in tools/timeline.py (CUT, COLD_OPEN):

  cold open  2.5 s  the face on the wall, its eyes turning to follow the pointer
  title      3.0 s
  how        6.0 s  one 4-line snippet per file, large, then the CLI loop
  carve     ~31 s   first eye real time, the rest of the carving at 2x, lighting,
                    the face coming alive, the gust, the snuff, the eyes staying
  mashrabiya ~10 s  the stencil traced at 2x, then lit
  credits    4.0 s

The soundtrack is synthesised here with numpy from the takes' real input events,
mapped through the same cut, and normalised to -14 LUFS with ffmpeg loudnorm.
Leaves room for a ~12 s Rive Editor clip spliced in after the "how" segment.

    ~/venvs/pw/bin/python tools/make_video.py /tmp/hollow_frames2 media/hollow.mp4
"""
import json
import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
from timeline import COLD_OPEN, CUT, ORDER, TAKES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, 'fonts')
W, H = 1600, 1000
AW, AH = 1280, 800  # artboard units
FPS = 30

CREAM = (242, 230, 208)
MUTED = (156, 147, 132)
AMBER = (240, 160, 64)
INK = (12, 10, 14)

DISPLAY = 'CormorantGaramond-SemiBoldItalic.ttf'
SERIF = 'CormorantGaramond-Medium.ttf'
MONO = 'IBMPlexMono-Medium.ttf'
_FONTS = {}

N_COLD, N_TITLE, N_MAKE, N_END = 75, 90, 180, 120
XFADE = 12
# an optional screen recording of the Rive Editor pass, spliced in after "how it's made":
#   EDITOR_CLIP=media/editor.mov KEEP=1 tools/render_all.sh   (the sound is rebuilt for the new timing)
EDITOR = os.environ.get('EDITOR_CLIP') or os.environ.get('EDITOR_MOV') or ''


def editor_frames():
    if not EDITOR:
        return 0
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', EDITOR],
                       capture_output=True, text=True, check=True)
    return int(float(r.stdout.strip()) * FPS)


def font(name, size):
    key = (name, int(size))
    if key not in _FONTS:
        _FONTS[key] = ImageFont.truetype(os.path.join(FONTS, name), int(size))
    return _FONTS[key]


def fade(img, a):
    if a >= 1:
        return img
    return Image.blend(Image.new('RGBA', img.size, (0, 0, 0, 255)), img, max(0.0, a))


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------
# camera: a window on the artboard (zoom z around cx, cy), cut from the 1920x1200 frame

def window(z, cx, cy):
    ww, wh = AW / z, AH / z
    x0 = min(max(cx - ww / 2, 0), AW - ww)
    y0 = min(max(cy - wh / 2, 0), AH - wh)
    return x0, y0, ww, wh


def shoot(src, z=1.0, cx=AW / 2, cy=AH / 2):
    x0, y0, ww, wh = window(z, cx, cy)
    k = src.size[0] / AW
    box = (x0 * k, y0 * k, (x0 + ww) * k, (y0 + wh) * k)
    return src.resize((W, H), Image.LANCZOS, box=box), (x0, y0, W / ww)


def camera(take, k):
    """the takes play full frame (the panel steps back on its own during the reveal)"""
    return 1.0, AW / 2, AH / 2


# ---------------------------------------------------------------------------
# pointer overlay

def arrow(scale):
    pts = [(0, 0), (0, 22), (5.5, 17), (9.5, 26), (13, 24.5), (9, 16), (16, 16)]
    size = int(44 * scale)
    p = [(4 + x * scale, 4 + y * scale) for x, y in pts]
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    shadow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon([(x + 1.5, y + 2.5) for x, y in p], fill=(0, 0, 0, 130))
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(2)))
    ImageDraw.Draw(img).polygon(p, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
    return img


ARROW = arrow(1.3)


def knife_zone(x, y):
    """the script draws its own knife over the pumpkin (artboard units)"""
    dx = (x - 500) / (214 + 60)
    dy = (y - 464) / (160 + 60)
    return dx * dx + dy * dy <= 1


def overlay_pointer(img, x, y, since_down, cam):
    x0, y0, k = cam
    cx, cy = (x - x0) * k, (y - y0) * k
    if not knife_zone(x, y):
        img.alpha_composite(ARROW, (int(cx) - 5, int(cy) - 5))
    if since_down < 22:
        t = since_down / 22
        r = (10 + 32 * t)
        ring = Image.new('RGBA', img.size, (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 214, 150, int(200 * (1 - t))), width=3)
        img.alpha_composite(ring)


# ---------------------------------------------------------------------------
# cards

def vignette_bg():
    bg = Image.new('RGB', (W, H), INK)
    glow = Image.new('L', (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W * 0.15, H * 0.05, W * 0.85, H * 1.1], fill=60)
    glow = glow.filter(ImageFilter.GaussianBlur(200))
    warm = Image.new('RGB', (W, H), (90, 44, 12))
    return Image.composite(warm, bg, glow).convert('RGBA')


BG = None
TITLE_BG = None


def title_card(k):
    t = k / FPS
    z = 1.0 + 0.03 * (k / N_TITLE)
    bw, bh = int(W * z), int(H * z)
    img = TITLE_BG.resize((bw, bh), Image.BILINEAR).crop(((bw - W) // 2, (bh - H) // 2, (bw - W) // 2 + W,
                                                          (bh - H) // 2 + H))
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    def line(at, y, text, f, col, rise=18):
        a = ease((t - at) / 0.6)
        if a > 0:
            d.text((W / 2, y + (1 - a) * rise), text, font=f, fill=(*col, int(255 * a)), anchor='mm')

    line(0.0, 390, 'Hollow', font(DISPLAY, 210), CREAM, 30)
    line(0.4, 526, "CARVE IT  ·  LIGHT IT  ·  DON'T TRUST WHAT IT CASTS", font(MONO, 22), MUTED)
    line(0.8, 630, 'An interactive jack-o’-lantern, made in Rive', font(SERIF, 44), CREAM)
    img.alpha_composite(layer)
    return img


SNIPPETS = [
    ('scene.rml', 'RML · the view model the markup and the script share', 'scene.rml', '<ViewModel defaultInstanceId', 4),
    ('main.luau', 'LUAU · the face on the wall wakes up', 'main.luau', '-- it blinks, and its eyes narrow', 4),
    ('light.wgsl', 'WGSL · GPU Canvas: the wall shows your carving, then its face', 'light.wgsl', 'let dark = 1.0 - clamp(wt.g', 4),
]
KW = {'local', 'function', 'end', 'if', 'then', 'else', 'elseif', 'return', 'for', 'do', 'in', 'let', 'var', 'fn'}


def snippet(path, marker, count):
    with open(os.path.join(ROOT, path)) as f:
        lines = f.read().split('\n')
    i = next(j for j, l in enumerate(lines) if marker in l)
    chunk = lines[i:i + count]
    ind = min(len(l) - len(l.lstrip()) for l in chunk if l.strip())
    return i + 1, [l[ind:] for l in chunk]


def tokenize(s):
    out, cur, q = [], '', None
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                out.append(cur)
                cur, q = '', None
            continue
        if ch in '\'"':
            if cur:
                out.append(cur)
            cur, q = ch, ch
        elif ch.isalnum() or ch == '_':
            cur += ch
        else:
            if cur:
                out.append(cur)
            out.append(ch)
            cur = ''
    if cur:
        out.append(cur)
    return out


def draw_code(d, x, y, lines, first, size, lh):
    f = font(MONO, size)
    for i, line in enumerate(lines):
        yy = y + i * lh
        d.text((x, yy), f'{first + i:>4}', font=f, fill=(90, 82, 74))
        cx = x + f.getlength('0000  ')
        if line.strip().startswith(('--', '//')):
            d.text((cx, yy), line, font=f, fill=(150, 138, 120))
            continue
        for tok in tokenize(line):
            c = CREAM
            if tok in KW:
                c = AMBER
            elif tok.startswith(("'", '"')):
                c = (170, 206, 140)
            elif tok in ('<', '/', '>'):
                c = (232, 150, 90)
            d.text((cx, yy), tok, font=f, fill=c)
            cx += f.getlength(tok)


def make_card(k):
    t = k / FPS
    img = BG.copy()
    d = ImageDraw.Draw(img)
    d.text((72, 44), 'How it’s made', font=font(DISPLAY, 56), fill=CREAM)
    d.text((76, 116), 'Three plain-text files. The Rive CLI builds, checks and renders them headless.',
           font=font(SERIF, 30), fill=MUTED)
    per = 1.7
    i = min(2, int(t / per))
    local = t - i * per
    name, cap, path, marker, count = SNIPPETS[i]
    a = ease(local / 0.25)
    pane = Image.new('RGBA', (1456, 330), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pane)
    pd.rounded_rectangle([0, 0, 1455, 329], 20, fill=(20, 17, 22, 250), outline=(255, 255, 255, 34))
    x = 32
    for j, s in enumerate(SNIPPETS):
        f = font(MONO, 26)
        pd.text((x, 24), s[0], font=f, fill=AMBER if j == i else (104, 96, 88))
        if j == i:
            pd.line([x, 60, x + f.getlength(s[0]), 60], fill=AMBER, width=3)
        x += f.getlength(s[0]) + 44
    pd.text((x + 10, 30), cap, font=font(SERIF, 26), fill=MUTED)
    first, lines = snippet(path, marker, count)
    draw_code(pd, 24, 96, lines, first, 30, 52)
    if a < 1:
        pane = fade(pane, a)
    img.alpha_composite(pane, (72, 180 + int((1 - a) * 18)))

    # the terminal, full width
    tx, ty = 72, 548
    term = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(term).rounded_rectangle([tx, ty, tx + 1456, ty + 400], 20, fill=(8, 8, 10, 255),
                                           outline=(255, 255, 255, 34))
    img.alpha_composite(term)
    d = ImageDraw.Draw(img)
    cmds = [
        (0.2, '$ rive hollow --verify', ['rive  verified  ·  0 errors, 0 warnings', '      RML · Luau strict types · WGSL']),
        (2.4, '$ rive hollow --screenshot=f.png --pointer=down@405,392 … --advance=2',
         ['rive  wrote f.png', '      one run per frame: every frame of this film replays real input']),
    ]
    f = font(MONO, 27)
    for j, (at, c, outs) in enumerate(cmds):
        lt = t - at
        if lt < 0:
            continue
        typed = c[:int(lt * 70)]
        caret = '▌' if len(typed) < len(c) and int(t * 4) % 2 == 0 else ''
        y = ty + 36 + j * 180
        d.text((tx + 32, y), typed + caret, font=f, fill=CREAM)
        if lt * 70 > len(c) + 6:
            for m, o in enumerate(outs):
                d.text((tx + 32, y + 46 + m * 40), o, font=font(MONO, 25), fill=(146, 206, 146))
    return img


def end_card(k):
    t = k / FPS
    img = BG.copy()
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    def line(at, y, text, f, col, x=W / 2, anchor='mm'):
        a = ease((t - at) / 0.5)
        if a > 0:
            d.text((x, y + (1 - a) * 10), text, font=f, fill=(*col, int(255 * a)), anchor=anchor)

    line(0.0, 220, 'Hollow', font(DISPLAY, 150), CREAM)
    line(0.2, 345, 'Carve it. Light it. Don’t trust what it casts.', font(SERIF, 38), CREAM)
    line(0.4, 412, 'Rive CLI  ·  RML  ·  Luau  ·  WGSL GPU Canvas  ·  data binding  ·  state machines',
         font(MONO, 19), AMBER)
    credits = [
        ('MADE BY', 'Taktek  ·  taktek.io/hollow'),
        ('SOURCE', 'github.com/taktekhq/hollow  ·  code MIT'),
        ('TYPE', 'Cormorant Garamond  ·  IBM Plex Mono  ·  IBM Plex Sans Arabic  (OFL)'),
        ('SOUND', 'synthesised from the film’s own input'),
    ]
    for j, (lab, txt) in enumerate(credits):
        y = 520 + j * 56
        line(0.7 + j * 0.15, y, lab, font(MONO, 16), MUTED, x=W / 2 - 230, anchor='rm')
        line(0.7 + j * 0.15, y, txt, font(SERIF, 29), CREAM, x=W / 2 - 202, anchor='lm')
    line(1.6, 820, '#rivehalloweenchallenge   @rive_app', font(MONO, 19), MUTED)
    img.alpha_composite(layer)
    return img


# ---------------------------------------------------------------------------
# callouts, a lower third above the caption (take frame ranges)

CALLOUTS = {
    'carve': [(2, 44, 'RML · STATE MACHINE', 'the title rises in on an eased intro timeline'),
              (50, 104, 'LUAU', 'your strokes become cuts; close one and the piece pops out'),
              (318, 358, 'LUAU', 'leave a cut open and you get a slit of light'),
              (376, 482, 'STATE MACHINE', 'the tool pill slides to Etch: shave the skin instead'),
              (512, 608, 'DATA BINDING', 'the candle and the sliders write the view model; the shader reads it'),
              (612, 690, 'GPU CANVAS · WGSL', 'light through your carving: glow, rays, your face on the wall'),
              (700, 820, 'LUAU + WGSL', 'the face on the wall wakes up: it narrows its eyes and watches you'),
              (963, 1020, 'LUAU', 'a fast sweep is a gust: it slides out of the light'),
              (1134, 1188, 'LUAU', 'snuffed: smoke rises from the lid, and the eyes stay')],
    'ghoul': [(26, 176, 'STENCIL · LUAU', 'Ghoul: the knife cuts the eyes and mouth, then etches brows and cheeks'),
              (182, 268, 'WGSL', 'etched skin is thin enough to glow amber')],
    'mash': [(10, 188, 'STENCIL · LUAU', 'the script carves a mashrabiya, star by star'),
             (196, 318, 'WGSL', 'eight-point stars thrown across the room')],
}


def callout(img, label, text, a):
    f1 = font(MONO, 17)
    f2 = font(SERIF, 31)
    w = f1.getlength(label) + f2.getlength(text) + 84
    x = 720 - w / 2
    y = 822
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x, y, x + w, y + 54], 27, fill=(10, 8, 12, int(225 * a)), outline=(240, 160, 64, int(100 * a)))
    d.text((x + 28, y + 27), label, font=f1, fill=(*AMBER, int(255 * a)), anchor='lm')
    d.text((x + 50 + f1.getlength(label), y + 26), text, font=f2, fill=(*CREAM, int(255 * a)), anchor='lm')
    img.alpha_composite(layer)


def take_meta(frames_dir, name):
    meta = {}
    with open(os.path.join(frames_dir, name, 'pointer.tsv')) as f:
        for line in f:
            k, x, y, down, since = line.split()
            meta[int(k)] = (float(x), float(y), int(down), int(since) // 2)
    return meta


def take_frame(frames_dir, name, meta, k, cam=None, pointer=True, callouts=True):
    src = Image.open(os.path.join(frames_dir, name, f'{k:05d}.png')).convert('RGBA')
    z, cx, cy = cam if cam else camera(name, k)
    img, c = shoot(src, z, cx, cy)
    img = img.convert('RGBA')
    if pointer:
        x, y, down, since = meta[k]
        overlay_pointer(img, x, y, since, c)
    if callouts:
        for (a, b, label, text) in CALLOUTS.get(name, []):
            if a <= k <= b:
                callout(img, label, text, max(0.0, min(1.0, (k - a) / 6, (b - k) / 6)))
    return img


# ---------------------------------------------------------------------------
# the cut as a list of video frames, and the map from take time to film time

def plan():
    """the film as a list of (kind, take, k, blend): blend = (take, k) of the previous take crossfading out"""
    frames = []
    for i in range(N_COLD):
        frames.append(('cold', 'carve', COLD_OPEN[1] + i * (COLD_OPEN[2] - COLD_OPEN[1]) // N_COLD, None))
    frames += [('title', None, i, None) for i in range(N_TITLE)]
    frames += [('make', None, i, None) for i in range(N_MAKE)]
    frames += [('editor', None, i, None) for i in range(editor_frames())]
    starts = {}
    for n, take in enumerate(ORDER):
        tail = []
        if n > 0:
            tail = [(f[1], f[2]) for f in frames[-XFADE:]]
            frames = frames[:-XFADE]
        starts[take] = len(frames)
        j = 0
        for a, b, step in CUT[take]:
            for k in range(a, b, step):
                frames.append(('take', take, k, tail[j] if j < len(tail) else None))
                j += 1
    frames += [('end', None, i, None) for i in range(N_END)]
    return frames, starts


def time_map(frames):
    """take -> sorted list of (take k, film seconds) for every frame that plays"""
    m = {}
    for i, (kind, take, k, bk) in enumerate(frames):
        if kind == 'take':
            m.setdefault(take, []).append((k, i / FPS))
            if bk is not None:
                m.setdefault(bk[0], []).append((bk[1], i / FPS))
    for v in m.values():
        v.sort()
    return m


def film_time(tm, take, sim_frame):
    """film seconds when take sim frame f plays, or None if that moment was cut away"""
    k = (sim_frame - 2) / 2
    pts = tm[take]
    if k < pts[0][0] - 1 or k > pts[-1][0] + 1:
        return None
    for (k0, t0), (k1, t1) in zip(pts, pts[1:]):
        if k0 <= k <= k1:
            if k1 - k0 > 4:  # a jump in the cut
                return None
            return t0 + (t1 - t0) * (k - k0) / max(1e-9, k1 - k0)
    return pts[0][1] if k < pts[0][0] else pts[-1][1]


# ---------------------------------------------------------------------------
# sound

SR = 44100
RNG = np.random.default_rng(7)


def smooth(x, w):
    c = np.cumsum(np.concatenate([np.zeros(w), x, np.full(w, x[-1])]))
    y = (c[w:] - c[:-w]) / w
    return y[w // 2:w // 2 + len(x)]


def bandnoise(n, lo, hi):
    spec = np.fft.rfft(RNG.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    spec[(f < lo) | (f > hi)] = 0
    x = np.fft.irfft(spec, n)
    return x / (np.max(np.abs(x)) + 1e-9)


def bell(freq, dur=2.2, amp=1.0, detune=0.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for d in ((0.0,) if not detune else (-detune, detune)):
        f = freq * (2 ** (d / 1200))
        mod = 1.6 * np.exp(-t * 6) * np.sin(2 * np.pi * f * 3.5 * t)
        sig += np.sin(2 * np.pi * f * t + mod) * np.exp(-t * 2.2)
        sig += 0.25 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t * 5)
    return sig * np.minimum(1, t / 0.004) * amp / (2 if detune else 1)


def drone(dur, amp, base=36.7):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = (np.sin(2 * np.pi * base * t) + 0.7 * np.sin(2 * np.pi * base * 1.5 * 1.003 * t + 1)
           + 0.4 * np.sin(2 * np.pi * base * 2.01 * t + 2)) * (0.8 + 0.2 * np.sin(t * 0.7))
    sig += bandnoise(n, 40, 160) * 0.5
    env = np.minimum(1, t / 2.0) * np.minimum(1, (dur - t) / 0.8)
    return sig / 2.6 * env * amp


def reverb(x, sec=2.6, wet=0.28):
    n = int(sec * SR)
    t = np.arange(n) / SR
    ir = RNG.standard_normal(n) * np.exp(-t * 3.2)
    ir[:int(0.012 * SR)] = 0
    ir /= np.sqrt(np.sum(ir ** 2))
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)]
    return x * (1 - wet) + y * wet * 2.2


NOTE = {'D3': 146.83, 'A3': 220.0, 'D4': 293.66, 'E4': 329.63, 'F4': 349.23, 'G4': 392.0, 'A4': 440.0,
        'Bb4': 466.16, 'Cs5': 554.37, 'D5': 587.33, 'E5': 659.25}
THEME = ['D5', 'A4', 'F4', 'A4', 'E5', 'A4', 'F4', 'A4', 'D5', 'A4', 'G4', 'Bb4', 'A4', 'F4', 'E4', 'Cs5']


def soundtrack(total, cues):
    n = int(total * SR) + SR
    t = np.arange(n) / SR
    music = np.zeros(n)
    sfx = np.zeros(n)
    amb = np.zeros(n)

    def add(buf, at, sig):
        i = int(at * SR)
        if i >= n or i + len(sig) <= 0:
            return
        if i < 0:
            sig, i = sig[-i:], 0
        j = min(n, i + len(sig))
        buf[i:j] += sig[:j - i]

    def theme(a, b, level, pitch=1.0, detune=0.0, beat=0.42):
        i, x = 0, a
        while x < b - 0.3:
            add(music, x, bell(NOTE[THEME[i % len(THEME)]] * pitch, 2.6, level * (0.9 if i % 4 == 0 else 0.6), detune))
            if i % 8 == 0:
                add(music, x, bell(NOTE['D3'] * pitch, 3.0, level * 0.5, detune))
            x += beat
            i += 1

    # room tone, a slow wind, and crickets that hush once the candle is the light
    amb += bandnoise(n, 30, 400) * 0.08 * (0.75 + 0.25 * np.sin(t * 0.37))
    amb += bandnoise(n, 300, 1400) * 0.05 * (0.5 + 0.5 * np.sin(t * 0.21 + 1.3)) ** 2
    lit = np.zeros(n)
    for a, b in cues['lit']:
        lit[int(a * SR):int(b * SR)] = 1
    lit = smooth(lit, SR)
    for c0 in np.arange(cues['scene'][0], cues['scene'][1], 1.1):
        for k in range(3):
            L = int(0.035 * SR)
            tt = np.arange(L) / SR
            add(amb, c0 + k * 0.07 + RNG.uniform(0, 0.03), np.sin(2 * np.pi * 4700 * tt) * np.sin(np.pi * tt / 0.035) * 0.018)
    amb *= 1 - 0.55 * lit

    # music: cold open drone + detuned theme; nothing under the carving; the reveal gets
    # the drone and the detuned theme; after the snuff the theme comes back pitched down
    cold_end = cues['cold_end']
    add(music, 0.0, drone(cold_end + 0.6, 0.35))
    theme(0.3, cold_end, 0.07, 0.94, 18, beat=0.6)
    add(music, cold_end - 0.05, bell(NOTE['D4'], 4, 0.4) + bell(NOTE['A4'], 4, 0.22))  # title hit
    add(music, cold_end - 0.05, drone(3.0, 0.4, 27.5))
    make0 = cues['make'][0]
    add(music, make0, drone(cues['make'][1] - make0 + cues.get('editor_sec', 0), 0.12, 55.0))
    for a, b in cues['reveal']:
        add(music, a, drone(b - a + 0.4, 0.22))
        theme(a + 0.8, b, 0.055, 0.94, 22, beat=0.55)
    for a, b in cues['linger']:
        theme(a + 0.15, b, 0.12, 0.75, 14, beat=0.7)
    for a, b in cues['soft']:
        theme(a, b, 0.07)
    theme(cues['end'][0], cues['end'][1], 0.05, 1.0, 0, beat=0.5)

    for at, kind, arg in cues['sfx']:
        if kind == 'scrape':
            L = int(arg * SR)
            tt = np.arange(L) / SR
            s = bandnoise(L, 900, 3800) * (0.55 + 0.45 * np.abs(np.sin(tt * 23 + RNG.uniform(0, 3))))
            s += bandnoise(L, 120, 400) * 0.5
            env = np.minimum(1, tt / 0.03) * np.minimum(1, (arg - tt) / 0.05)
            add(sfx, at, s * env * 0.08)
        elif kind == 'pop':
            L = int(0.3 * SR)
            tt = np.arange(L) / SR
            s = np.sin(2 * np.pi * (180 - 90 * tt) * tt) * np.exp(-tt * 20) * 0.55
            s += bandnoise(L, 200, 2000) * np.exp(-tt * 50) * 0.25
            add(sfx, at, s)
        elif kind == 'thud':
            L = int(0.35 * SR)
            tt = np.arange(L) / SR
            s = np.sin(2 * np.pi * (95 - 30 * tt) * tt) * np.exp(-tt * 16) * 0.6
            s += bandnoise(L, 300, 1600) * np.exp(-tt * 40) * 0.18
            add(sfx, at, s * 0.8)
        elif kind == 'click':
            L = int(0.05 * SR)
            tt = np.arange(L) / SR
            add(sfx, at, (np.sin(2 * np.pi * 1800 * tt) * 0.6 + bandnoise(L, 2000, 6000) * 0.4) * np.exp(-tt * 120) * 0.2)
        elif kind == 'match':
            L = int(1.6 * SR)
            tt = np.arange(L) / SR
            strike = bandnoise(L, 1500, 9000) * np.where(tt < 0.12, np.sin(np.pi * tt / 0.12), 0) * 0.35
            hiss = bandnoise(L, 600, 5000) * np.where(tt < 0.1, 0, np.exp(-(tt - 0.1) * 3)) * 0.14
            whoomp = np.sin(2 * np.pi * (60 + 30 * np.exp(-tt * 8)) * tt) * np.where(tt < 0.1, 0, np.exp(-(tt - 0.1) * 5)) * 0.45
            add(sfx, at, strike + hiss + whoomp)
        elif kind == 'flame':
            L = int(arg * SR)
            tt = np.arange(L) / SR
            add(sfx, at, bandnoise(L, 80, 500) * 0.05 * np.minimum(1, tt / 0.8) * np.minimum(1, (arg - tt) / 0.3))
            for c in np.arange(0.3, arg - 0.2, 0.23):
                if RNG.random() < 0.55:
                    CL = int(0.012 * SR)
                    add(sfx, at + c + RNG.uniform(0, 0.15), bandnoise(CL, 2000, 7000) * np.hanning(CL) * RNG.uniform(0.03, 0.09))
        elif kind == 'whoosh':
            L = int(0.9 * SR)
            tt = np.arange(L) / SR
            add(sfx, at, bandnoise(L, 200, 2500) * np.sin(np.pi * tt / 0.9) ** 3 * 0.55)
        elif kind == 'snuff':
            L = int(1.2 * SR)
            tt = np.arange(L) / SR
            add(sfx, at, bandnoise(L, 150, 1800) * np.exp(-tt * 5) * 0.55 + np.sin(2 * np.pi * (70 - 35 * tt) * tt) * np.exp(-tt * 3) * 0.45)
        elif kind == 'tick':
            L = int(0.07 * SR)
            tt = np.arange(L) / SR
            add(sfx, at, bandnoise(L, 1200, 4000) * np.exp(-tt * 70) * 0.12)
        elif kind == 'slide':
            for c in np.arange(0, arg, 0.08):
                CL = int(0.02 * SR)
                add(sfx, at + c, np.sin(2 * np.pi * 2400 * np.arange(CL) / SR) * np.exp(-np.arange(CL) / SR * 200) * 0.05)
        elif kind == 'swish':  # a soft air cut between segments
            L = int(0.5 * SR)
            tt = np.arange(L) / SR
            add(sfx, at, bandnoise(L, 400, 3000) * np.sin(np.pi * tt / 0.5) ** 2 * 0.12)

    music = reverb(music, 3.0, 0.4)
    sfx = reverb(sfx, 1.4, 0.18)
    mix = music * 0.9 + sfx + amb
    # true silence for a breath before the snuff
    for at in cues['hush']:
        a, b = int((at - 0.6) * SR), int(at * SR)
        env = np.ones(n)
        env[a:b] = 0
        env[max(0, a - int(0.08 * SR)):a] = np.linspace(1, 0, a - max(0, a - int(0.08 * SR)))
        mix *= env
    left = mix + 0.3 * np.roll(amb, 331) - 0.3 * amb
    right = mix + 0.3 * np.roll(amb, -517) - 0.3 * amb
    st = np.stack([left, right], 1)[:int(total * SR)]
    for at in cues['hush']:  # keep the hush clean after the stereo widening too
        st[int((at - 0.6) * SR):int(at * SR)] = 0
    fn = int(0.6 * SR)
    st[:fn] *= np.linspace(0, 1, fn)[:, None]
    st[-int(1.5 * SR):] *= np.linspace(1, 0, int(1.5 * SR))[:, None]
    st /= max(1e-9, np.max(np.abs(st))) / 0.9
    return st


def write_wav(path, st):
    pcm = (np.clip(st, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def loudnorm(src, dst, target=-13.4):
    """two-pass ffmpeg loudnorm to `target` LUFS, true peak -1.5 dB"""
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', src, '-af', f'loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json',
                        '-f', 'null', '-'], capture_output=True, text=True)
    js = json.loads(r.stderr[r.stderr.rindex('{'):r.stderr.rindex('}') + 1])
    af = (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:"
          f"measured_LRA={js['input_lra']}:measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true")
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', src, '-af', af, '-ar', str(SR), dst], check=True)


def panel_hit(x, y):
    return x > 960


def take_cues(name, tm, cues):
    take = TAKES[name]()
    ev = take.events
    down_at = None
    lit_from = None
    for f, kind, x, y in ev:
        at = film_time(tm, name, f)
        if kind == 'down':
            down_at = (f, at, x, y)
            if at is not None and panel_hit(x, y):
                cues['sfx'].append((at, 'click', 0))
            if panel_hit(x, y) and abs(y - 378) < 30:
                if lit_from is None:
                    lit_from = at
                    if at is not None:
                        cues['sfx'].append((at + 0.05, 'match', 0))
                else:
                    if at is not None:
                        cues['hush'].append(at)
                        cues['sfx'].append((at + 0.02, 'snuff', 0))
                        cues['linger'].append((at + 0.3, at + 2.6))
                    cues['lit'].append((lit_from, at))
                    lit_from = None
        elif kind == 'up' and down_at is not None:
            f0, a, x0, y0 = down_at
            if a is not None and at is not None and at > a:
                if knife_zone(x0, y0) and not panel_hit(x0, y0):
                    cues['sfx'].append((a, 'scrape', at - a))
                    if math.hypot(x - x0, y - y0) < 12:
                        cues['sfx'].append((at, 'pop', 0))
                        th = film_time(tm, name, f + 33)
                        if th is not None:
                            cues['sfx'].append((th, 'thud', 0))
                elif panel_hit(x0, y0) and abs(x - x0) > 30:
                    cues['sfx'].append((a, 'slide', at - a))
            down_at = None
    if lit_from is not None:
        cues['lit'].append((lit_from, tm[name][-1][1]))
    sweeps = [f1 for (f1, k1, x1, y1), (f2, k2, x2, y2) in zip(ev, ev[1:])
              if k1 == k2 == 'move' and f2 - f1 <= 2 and abs(x2 - x1) > 100]
    if sweeps:
        at = film_time(tm, name, sweeps[-1] - 6)
        if at is not None and cues['lit'] and cues['lit'][-1][0] < at:
            cues['sfx'].append((at - 0.1, 'whoosh', 0))
    return take


def build_sound(frames, tm, wav='/tmp/hollow_sound.wav'):
    total = len(frames) / FPS
    cues = {'sfx': [], 'lit': [], 'hush': [], 'linger': [], 'reveal': [], 'soft': []}
    cues['cold_end'] = N_COLD / FPS
    cues['make'] = ((N_COLD + N_TITLE) / FPS, (N_COLD + N_TITLE + N_MAKE) / FPS)
    cues['editor_sec'] = sum(1 for f in frames if f[0] == 'editor') / FPS
    t_take = min(t for pts in tm.values() for _, t in pts)
    cues['scene'] = (t_take, total - N_END / FPS)
    cues['end'] = (total - N_END / FPS, total - 0.8)
    carve = take_cues('carve', tm, cues)
    n_lit = len(cues['lit'])
    stencils = [take_cues(n, tm, cues) for n in ORDER if n != 'carve']
    carve_lit = cues['lit'][0]
    # the face starts to wake six seconds of sim time after lighting
    light_f = next(f for f, k, x, y in carve.events if k == 'down' and x > 960 and abs(y - 378) < 30)
    t_wake = film_time(tm, 'carve', light_f + 360) or carve_lit[0] + 5
    cues['reveal'].append((t_wake, cues['hush'][0] - 0.6))
    for a, b in cues['lit'][n_lit:]:
        cues['soft'].append((a + 0.5, b))
    # the stencils' knife ticking while the script traces (sped up in the cut)
    for name, take in zip([n for n in ORDER if n != 'carve'], stencils):
        downs = [f for f, k, x, y in take.events if k == 'down']
        t0 = film_time(tm, name, downs[0] + 8)
        t1 = film_time(tm, name, downs[1] - 4) if len(downs) > 1 else None
        if t0 is not None and t1 is not None:
            for x in np.arange(t0 + 0.1, t1, 0.05):
                cues['sfx'].append((x, 'tick', 0))
    for at in (N_COLD / FPS, (N_COLD + N_TITLE) / FPS, (N_COLD + N_TITLE + N_MAKE) / FPS):
        cues['sfx'].append((at - 0.25, 'swish', 0))
    st = soundtrack(total, cues)
    raw = wav.replace('.wav', '_raw.wav')
    write_wav(raw, st)
    loudnorm(raw, wav)
    return total, wav, cues


def main():
    global BG, TITLE_BG
    frames_dir, out = sys.argv[1], sys.argv[2]
    BG = vignette_bg()
    meta = {n: take_meta(frames_dir, n) for n in ORDER}
    hero = Image.open(os.path.join(frames_dir, 'carve', '00932.png')).convert('RGB')
    TITLE_BG = Image.blend(Image.new('RGB', (W, H), INK),
                           shoot(hero, 1.25, 520, 330)[0].filter(ImageFilter.GaussianBlur(18)), 0.42).convert('RGBA')
    frames, starts = plan()
    tm = time_map(frames)
    total, wav, cues = build_sound(frames, tm)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    ff = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                           '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', wav,
                           '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-maxrate', '5000k', '-bufsize', '10000k',
                           '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-c:a', 'aac', '-b:a', '160k',
                           '-shortest', out], stdin=subprocess.PIPE)
    dec = None
    if EDITOR:
        dec = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-i', EDITOR, '-an', '-vf',
                                f'scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0c0a0e,fps={FPS}',
                                '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
    last_frame = None
    last_take = max(i for i, f in enumerate(frames) if f[0] == 'take')
    for i, (kind, take, k, bk) in enumerate(frames):
        if kind == 'cold':
            z = 1.6 + 0.12 * (i / N_COLD)
            img = take_frame(frames_dir, 'carve', meta['carve'], k, cam=(z, 500, 170), pointer=False, callouts=False)
            img = fade(img, min(1.0, i / 12, (N_COLD - i) / 6))
        elif kind == 'title':
            img = fade(title_card(k), min(1.0, k / 8, (N_TITLE - k) / 8))
        elif kind == 'make':
            img = fade(make_card(k), min(1.0, k / 8, (N_MAKE - k) / 8))
        elif kind == 'editor':
            buf = dec.stdout.read(W * H * 3) if dec else b''
            if len(buf) == W * H * 3:
                last_frame = Image.frombytes('RGB', (W, H), buf).convert('RGBA')
            img = last_frame if last_frame is not None else BG.copy()
            n_ed = sum(1 for f in frames if f[0] == 'editor')
            img = fade(img, min(1.0, k / 8, (n_ed - k) / 8))
        elif kind == 'take':
            img = take_frame(frames_dir, take, meta[take], k)
            if take == ORDER[0] and i - starts[take] < 4:
                img = fade(img, (i - starts[take]) / 4)
            if bk is not None:
                m = i - starts[take]
                img = Image.blend(take_frame(frames_dir, bk[0], meta[bk[0]], bk[1]), img, (m + 1) / (XFADE + 1))
            if i > last_take - 10:
                img = fade(img, (last_take - i) / 10)
        else:
            img = fade(end_card(k), min(1.0, k / 10, (N_END - k) / 12))
        ff.stdin.write(img.convert('RGB').tobytes())
    ff.stdin.close()
    ff.wait()
    print('wrote', out, round(total, 1), 's', 'snuff at', [round(h, 2) for h in cues['hush']])


if __name__ == '__main__':
    main()
