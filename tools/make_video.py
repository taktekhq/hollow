#!/usr/bin/env python3
"""Cuts the demo video at 1600x1000: a title over the lit room, how it's made
(the source, the CLI loop, frames coming out of `rive --screenshot`), the two
takes rendered by tools/render_take.py with the pointer drawn on top and
feature callouts, then credits. The soundtrack is synthesised here with numpy
from the takes' real input: knife scrapes while the pointer is down on the
pumpkin, pops and thuds when a piece falls, the match, the flame, the gust,
the thing on the wall, the snuff, under a music-box theme and room tone.

    ~/venvs/pw/bin/python tools/make_video.py /tmp/hollow_frames media/hollow.mp4

Needs Pillow, numpy and ffmpeg. Frames are piped straight into ffmpeg.
"""
import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
from timeline import TAKES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, 'fonts')
W, H = 1600, 1000
S = W / 1280  # artboard units -> video pixels
FPS = 30

CREAM = (242, 230, 208)
MUTED = (156, 147, 132)
AMBER = (240, 160, 64)
INK = (12, 10, 14)

DISPLAY = 'CormorantGaramond-SemiBoldItalic.ttf'
SERIF = 'CormorantGaramond-Medium.ttf'
MONO = 'IBMPlexMono-Medium.ttf'
_FONTS = {}


def font(name, size):
    key = (name, int(size))
    if key not in _FONTS:
        _FONTS[key] = ImageFont.truetype(os.path.join(FONTS, name), int(size))
    return _FONTS[key]


def fade(img, a):
    if a >= 1:
        return img
    black = Image.new('RGBA', img.size, (0, 0, 0, 255))
    return Image.blend(black, img, max(0.0, a))


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------
# timing of the whole cut (seconds)

TITLE_SEC = 4.5
MAKE_SEC = 10.5
END_SEC = 6.0
XFADE = 15  # frames of crossfade between the takes


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


ARROW = arrow(S)


def knife_zone(x, y):
    """the script draws its own knife over the pumpkin (artboard units)"""
    dx = (x - 500) / (214 + 60)
    dy = (y - 464) / (160 + 60)
    return dx * dx + dy * dy <= 1


def overlay_pointer(img, x, y, since_down):
    if not knife_zone(x, y):
        img.alpha_composite(ARROW, (int(x * S) - 4, int(y * S) - 4))
    if since_down < 22:
        t = since_down / 22
        r = (8 + 26 * t) * S
        cx, cy = x * S, y * S
        ring = Image.new('RGBA', img.size, (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 214, 150, int(200 * (1 - t))),
                                     width=3)
        img.alpha_composite(ring)


# ---------------------------------------------------------------------------
# backgrounds

def vignette_bg():
    bg = Image.new('RGB', (W, H), INK)
    glow = Image.new('L', (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W * 0.15, H * 0.05, W * 0.85, H * 1.1], fill=60)
    glow = glow.filter(ImageFilter.GaussianBlur(200))
    warm = Image.new('RGB', (W, H), (90, 44, 12))
    return Image.composite(warm, bg, glow).convert('RGBA')


def dimmed(frame, blur, dark):
    img = frame.convert('RGB').filter(ImageFilter.GaussianBlur(blur))
    return Image.blend(Image.new('RGB', img.size, INK), img, 1 - dark).convert('RGBA')


BG = None
TITLE_BG = None
THUMBS = []


def title_card(k):
    """the lit room, out of focus, slowly pushing in; the title rises"""
    t = k / FPS
    z = 1.0 + 0.035 * (t / TITLE_SEC)
    bw, bh = int(W * z), int(H * z)
    bg = TITLE_BG.resize((bw, bh), Image.BILINEAR).crop(((bw - W) // 2, (bh - H) // 2, (bw - W) // 2 + W,
                                                          (bh - H) // 2 + H))
    img = bg.copy()
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    def line(at, y, text, f, col, rise=18):
        a = ease((t - at) / 0.9)
        if a <= 0:
            return
        d.text((W / 2, y + (1 - a) * rise), text, font=f, fill=(*col, int(255 * a)), anchor='mm')

    line(0.25, 380, 'Hollow', font(DISPLAY, 200), CREAM, 30)
    line(0.9, 512, "CARVE IT  ·  LIGHT IT  ·  DON'T TRUST WHAT IT CASTS", font(MONO, 18), MUTED)
    line(1.5, 618, 'An interactive jack-o’-lantern, made in Rive', font(SERIF, 38), CREAM)
    line(2.0, 676, 'Rive CLI  ·  RML  ·  Luau scripting  ·  GPU Canvas (WGSL)  ·  data binding  ·  state machines',
         font(MONO, 17), AMBER)
    img.alpha_composite(layer)
    return img


KW = {'local', 'function', 'end', 'if', 'then', 'else', 'elseif', 'return', 'for', 'do', 'in', 'let', 'var', 'fn',
      'while', 'and', 'or', 'not', 'struct'}


def code_lines(path, marker, count):
    with open(os.path.join(ROOT, path)) as f:
        lines = f.read().split('\n')
    start = next(i for i, l in enumerate(lines) if marker in l)
    return start + 1, lines[start:start + count]


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


def draw_code(d, x, y, lines, first, size, lh, max_w):
    f = font(MONO, size)
    for i, line in enumerate(lines):
        yy = y + i * lh
        d.text((x, yy), f'{first + i:>4}', font=f, fill=(84, 78, 72))
        cx0 = x + f.getlength('0000  ')
        s = line.rstrip().replace('\t', '    ')
        if s.strip().startswith(('--', '//')):
            d.text((cx0, yy), s, font=f, fill=(128, 118, 104))
            continue
        cx = cx0
        for tok in tokenize(s):
            if cx > x + max_w:
                break
            c = CREAM
            if tok in KW:
                c = AMBER
            elif tok.startswith(("'", '"')):
                c = (170, 206, 140)
            elif tok in ('<', '/', '>'):
                c = (232, 150, 90)
            d.text((cx, yy), tok, font=f, fill=c)
            cx += f.getlength(tok)


PANES = [
    ('scene.rml', 'RML · markup, view model, state machine: the candle toggles a bound boolean',
     'scene.rml', 'name="Stencil Mashrabiya"', 21),
    ('main.luau', 'LUAU · a closed knife stroke becomes a hole, and the piece falls out',
     'main.luau', 'local function addCut', 22),
    ('light.wgsl', 'WGSL · GPU Canvas: rays march toward the flame through whatever you carved',
     'light.wgsl', '// rays: march from this pixel', 18),
]


def pane_lines(i):
    _name, _caption, path, marker, count = PANES[i]
    return code_lines(path, marker, count)


def code_card(k):
    """source panes slide through on the left, the take's frames come out of the CLI on the right,
    and the terminal types the loop"""
    t = k / FPS
    img = BG.copy()
    d = ImageDraw.Draw(img)
    d.text((72, 52), 'How it’s made', font=font(DISPLAY, 60), fill=CREAM)
    d.text((76, 128), 'Three plain-text files, written with a coding agent. The Rive CLI builds, verifies and renders them headless.',
           font=font(SERIF, 27), fill=MUTED)
    per = 2.9
    i = min(2, int(t / per))
    local = t - i * per
    name, caption = PANES[i][0], PANES[i][1]
    appear = ease(local / 0.35)
    pw, ph = 1000, 600
    pane = Image.new('RGBA', (pw, ph), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pane)
    pd.rounded_rectangle([0, 0, pw - 1, ph - 1], 18, fill=(20, 17, 22, 250), outline=(255, 255, 255, 30))
    for j, (n2, *_rest) in enumerate(PANES):
        tx = 26 + j * 150
        on = j == i
        pd.text((tx, 22), n2, font=font(MONO, 17), fill=AMBER if on else (110, 102, 92))
        if on:
            pd.line([tx, 48, tx + font(MONO, 17).getlength(n2), 48], fill=AMBER, width=2)
    pd.text((26, 66), caption, font=font(MONO, 14), fill=MUTED)
    first, lines = pane_lines(i)
    draw_code(pd, 20, 104, lines, first, 16, 26, pw - 60)
    if appear < 1:
        pane = fade(pane, appear)
    img.alpha_composite(pane, (72, 186 + int((1 - appear) * 24)))

    # right: frames of the take, as the CLI writes them
    fx, fy, fw = 1102, 186, 426
    fh = int(fw * H / W)
    d = ImageDraw.Draw(img)
    d.text((fx, fy), 'rive --screenshot', font=font(MONO, 15), fill=AMBER)
    d.text((fx, fy + 24), 'one run per frame, replaying real pointer input', font=font(SERIF, 21), fill=MUTED)
    for j in range(2):
        idx = int(t * 6) + j * 11
        frame_no, th = THUMBS[idx % len(THUMBS)]
        y = fy + 64 + j * (fh + 14)
        img.alpha_composite(th, (fx, y))
        lab = f'{frame_no:05d}.png'
        lw = font(MONO, 13).getlength(lab)
        d.rounded_rectangle([fx + 8, y + 8, fx + 24 + lw, y + 32], 6, fill=(8, 8, 10))
        d.text((fx + 16, y + 12), lab, font=font(MONO, 13), fill=CREAM)

    # the terminal
    tx, ty = 72, 820
    term = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(term).rounded_rectangle([tx, ty, tx + 1456, ty + 136], 16, fill=(8, 8, 10, 255),
                                           outline=(255, 255, 255, 30))
    img.alpha_composite(term)
    d = ImageDraw.Draw(img)
    cmds = [
        ('$ rive hollow --verify', 'rive  verified (0 errors, 0 warnings)  ·  RML, Luau strict types, WGSL'),
        ('$ rive hollow --viewport=1600x1000 --screenshot=f.png --pointer=down@405,392 --pointer=move@410,380 … --advance=2',
         'rive  wrote f.png  ·  every frame of this video is a replay of real input through the runtime'),
    ]
    f = font(MONO, 17)
    for j, (c, r) in enumerate(cmds):
        lt = t - 0.6 - j * 3.2
        if lt < 0:
            continue
        typed = c[:int(lt * 44)]
        caret = '▌' if int(t * 3) % 2 == 0 and len(typed) < len(c) else ''
        d.text((tx + 24, ty + 20 + j * 56), typed + caret, font=f, fill=CREAM)
        if lt * 44 > len(c) + 8:
            d.text((tx + 24, ty + 46 + j * 56), r, font=font(MONO, 14), fill=(140, 200, 140))
    return img


def end_card(k):
    t = k / FPS
    img = BG.copy()
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    def line(at, y, text, f, col):
        a = ease((t - at) / 0.7)
        if a > 0:
            d.text((W / 2, y + (1 - a) * 12), text, font=f, fill=(*col, int(255 * a)), anchor='mm')

    line(0.0, 230, 'Hollow', font(DISPLAY, 150), CREAM)
    line(0.4, 360, 'Carve it. Light it. Don’t trust what it casts.', font(SERIF, 36), CREAM)
    line(0.8, 430, 'Rive CLI  ·  RML  ·  Luau  ·  WGSL GPU Canvas  ·  data binding  ·  state machines',
         font(MONO, 17), AMBER)
    credits = [
        ('MADE BY', 'Taktek  ·  taktek.io'),
        ('SOURCE', 'github.com/taktekhq/hollow  ·  code MIT'),
        ('TYPE', 'Cormorant Garamond  ·  IBM Plex Mono  ·  IBM Plex Sans Arabic  (OFL)'),
        ('SOUND', 'synthesised from the take’s own input, music box and all'),
    ]
    for j, (lab, txt) in enumerate(credits):
        a = ease((t - 1.3 - j * 0.25) / 0.6)
        if a <= 0:
            continue
        y = 540 + j * 54
        d.text((W / 2 - 230, y), lab, font=font(MONO, 14), fill=(*MUTED, int(255 * a)), anchor='rm')
        d.text((W / 2 - 202, y), txt, font=font(SERIF, 27), fill=(*CREAM, int(255 * a)), anchor='lm')
    line(2.6, 840, '#rivehalloweenchallenge   @rive_app', font(MONO, 17), MUTED)
    img.alpha_composite(layer)
    return img


# ---------------------------------------------------------------------------
# callouts over the takes: what Rive feature is doing the work right now (take frame ranges, 30 fps)

CALLOUTS = {
    'carve': [(30, 250, 'LUAU', 'your strokes become cuts; close one and the piece pops out'),
              (372, 470, 'STATE MACHINE', 'tool pill, eased with a hand-tuned overshoot'),
              (512, 650, 'GPU CANVAS · WGSL', 'light leaks through the carving: glow, rays, projection'),
              (652, 770, 'DATA BINDING', 'sliders write the view model; the shader reads it'),
              (860, 986, 'WGSL', 'the haze shows a second face nobody carved, and it watches you'),
              (992, 1070, 'LUAU', 'a fast sweep is a gust: the flame gutters and it hides'),
              (1157, 1270, 'STATE MACHINE + LUAU', 'snuffed: smoke, and the eyes stay a moment longer')],
    'mash': [(20, 170, 'STENCIL · LUAU', 'the script carves a mashrabiya, star by star'),
             (190, 330, 'WGSL', 'eight-point stars thrown across the room')],
}


def callout(img, label, text, a):
    f1 = font(MONO, 14)
    f2 = font(SERIF, 27)
    w = f1.getlength(label) + f2.getlength(text) + 80
    x = 760 - w / 2
    y = 26
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x, y, x + w, y + 48], 24, fill=(10, 8, 12, int(220 * a)), outline=(240, 160, 64, int(90 * a)))
    d.text((x + 26, y + 24), label, font=f1, fill=(*AMBER, int(255 * a)), anchor='lm')
    d.text((x + 44 + f1.getlength(label), y + 23), text, font=f2, fill=(*CREAM, int(255 * a)), anchor='lm')
    img.alpha_composite(layer)


def take_meta(frames_dir, name):
    meta = {}
    with open(os.path.join(frames_dir, name, 'pointer.tsv')) as f:
        for line in f:
            k, x, y, down, since = line.split()
            meta[int(k)] = (float(x), float(y), int(down), int(since) // 2)
    return meta


def take_frame(frames_dir, name, meta, k):
    img = Image.open(os.path.join(frames_dir, name, f'{k:05d}.png')).convert('RGBA')
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)
    x, y, down, since = meta[k]
    overlay_pointer(img, x, y, since)
    for (a, b, label, text) in CALLOUTS.get(name, []):
        if a <= k <= b:
            callout(img, label, text, max(0.0, min(1.0, (k - a) / 8, (b - k) / 8)))
    return img


# ---------------------------------------------------------------------------
# sound

SR = 44100
RNG = np.random.default_rng(7)


def smooth(x, w):
    """moving average over w samples (cumulative sum, so it stays fast on long buffers)"""
    c = np.cumsum(np.concatenate([np.zeros(w), x, np.full(w, x[-1])]))
    y = (c[w:] - c[:-w]) / w
    return y[w // 2:w // 2 + len(x)]


def bandnoise(n, lo, hi):
    spec = np.fft.rfft(RNG.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    spec[(f < lo) | (f > hi)] = 0
    x = np.fft.irfft(spec, n)
    return x / (np.max(np.abs(x)) + 1e-9)


def bell(freq, dur=2.2, amp=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    mod = 1.6 * np.exp(-t * 6) * np.sin(2 * np.pi * freq * 3.5 * t)
    sig = np.sin(2 * np.pi * freq * t + mod) * np.exp(-t * 2.6)
    sig += 0.25 * np.sin(2 * np.pi * freq * 2.0 * t) * np.exp(-t * 5)
    att = np.minimum(1, t / 0.004)
    return sig * att * amp


def pad(freqs, dur, amp):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for f in freqs:
        for det in (-0.6, 0.0, 0.7):
            sig += np.sin(2 * np.pi * (f + det) * t + RNG.uniform(0, 6))
    env = np.minimum(1, t / 1.5) * np.minimum(1, (dur - t) / 1.5)
    return sig / (len(freqs) * 3) * env * amp


def reverb(x, sec=2.6, wet=0.28):
    n = int(sec * SR)
    t = np.arange(n) / SR
    ir = RNG.standard_normal(n) * np.exp(-t * 3.2)
    ir[:int(0.012 * SR)] = 0
    ir /= np.sqrt(np.sum(ir ** 2))
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)]
    return x * (1 - wet) + y * wet * 2.2


NOTE = {'D3': 146.83, 'F3': 174.61, 'A3': 220.0, 'C4': 261.63, 'D4': 293.66, 'E4': 329.63, 'F4': 349.23,
        'G4': 392.0, 'A4': 440.0, 'Bb4': 466.16, 'C5': 523.25, 'D5': 587.33, 'E5': 659.25, 'F5': 698.46,
        'A5': 880.0, 'Cs5': 554.37, 'G#4': 415.3}
THEME = ['D5', 'A4', 'F4', 'A4', 'E5', 'A4', 'F4', 'A4', 'D5', 'A4', 'G4', 'Bb4', 'A4', 'F4', 'E4', 'Cs5']


def soundtrack(total, cues):
    n = int(total * SR) + SR
    t = np.arange(n) / SR
    music = np.zeros(n)
    sfx = np.zeros(n)
    amb = np.zeros(n)

    def add(buf, at, sig, pan=0.0):
        i = int(at * SR)
        if i >= n or i + len(sig) <= 0:
            return
        if i < 0:
            sig = sig[-i:]
            i = 0
        j = min(n, i + len(sig))
        buf[i:j] += sig[:j - i]

    # room tone and a slow wind
    amb += bandnoise(n, 30, 400) * 0.08 * (0.75 + 0.25 * np.sin(t * 0.37))
    wind = bandnoise(n, 300, 1400)
    amb += wind * 0.05 * (0.5 + 0.5 * np.sin(t * 0.21 + 1.3)) ** 2
    # crickets in the moonlight, quieter once the candle is the light
    lit_mask = np.zeros(n)
    for a, b in cues['lit']:
        lit_mask[int(a * SR):int(b * SR)] = 1
    lit_s = smooth(lit_mask, SR)
    for c0 in np.arange(cues['scene'][0], cues['scene'][1], 1.1):
        for k in range(3):
            L = int(0.035 * SR)
            tt = np.arange(L) / SR
            ch = np.sin(2 * np.pi * 4700 * tt) * np.sin(np.pi * tt / 0.035) * 0.018
            add(amb, c0 + k * 0.07 + RNG.uniform(0, 0.03), ch)
    amb *= 1 - 0.55 * lit_s

    # music box theme: plays through, held back while carving, swells for the ghost
    for sec0, sec1, level in cues['music']:
        beat = 0.42
        i = 0
        x = sec0
        while x < sec1 - 0.3:
            nt = THEME[i % len(THEME)]
            add(music, x, bell(NOTE[nt], 2.4, level * (0.9 if i % 4 == 0 else 0.6)))
            if i % 8 == 0:
                add(music, x, bell(NOTE['D3'] if (i // 8) % 2 == 0 else NOTE['A3'] / 2 * 1.0, 3.0, level * 0.5))
            x += beat
            i += 1
    # a low pad under the scene, darker chord for the ghost
    for sec0, sec1, chord, level in cues['pads']:
        add(music, sec0, pad([NOTE[c] / 2 for c in chord], sec1 - sec0, level))

    for at, kind, arg in cues['sfx']:
        if kind == 'scrape':  # knife dragging through the rind for `arg` seconds
            L = int(arg * SR)
            tt = np.arange(L) / SR
            s = bandnoise(L, 900, 3800) * (0.55 + 0.45 * np.abs(np.sin(tt * 23 + RNG.uniform(0, 3))))
            s += bandnoise(L, 120, 400) * 0.5
            env = np.minimum(1, tt / 0.04) * np.minimum(1, (arg - tt) / 0.06)
            add(sfx, at, s * env * 0.07)
        elif kind == 'pop':  # the piece pushes out
            L = int(0.3 * SR)
            tt = np.arange(L) / SR
            s = np.sin(2 * np.pi * (180 - 90 * tt) * tt) * np.exp(-tt * 20) * 0.55
            s += bandnoise(L, 200, 2000) * np.exp(-tt * 50) * 0.25
            add(sfx, at, s)
        elif kind == 'thud':  # and lands on the table
            L = int(0.35 * SR)
            tt = np.arange(L) / SR
            s = np.sin(2 * np.pi * (95 - 30 * tt) * tt) * np.exp(-tt * 16) * 0.6
            s += bandnoise(L, 300, 1600) * np.exp(-tt * 40) * 0.18
            add(sfx, at, s * arg)
        elif kind == 'click':
            L = int(0.05 * SR)
            tt = np.arange(L) / SR
            add(sfx, at, (np.sin(2 * np.pi * 1800 * tt) * 0.6 + bandnoise(L, 2000, 6000) * 0.4) * np.exp(-tt * 120) * 0.22)
        elif kind == 'match':
            L = int(1.6 * SR)
            tt = np.arange(L) / SR
            strike = bandnoise(L, 1500, 9000) * np.where(tt < 0.12, np.sin(np.pi * tt / 0.12), 0) * 0.35
            hiss = bandnoise(L, 600, 5000) * np.where(tt < 0.1, 0, np.exp(-(tt - 0.1) * 3)) * 0.14
            whoomp = np.sin(2 * np.pi * (60 + 30 * np.exp(-tt * 8)) * tt) * np.where(tt < 0.1, 0, np.exp(-(tt - 0.1) * 5)) * 0.45
            add(sfx, at, strike + hiss + whoomp)
        elif kind == 'flame':  # a soft crackle for as long as it burns
            L = int(arg * SR)
            tt = np.arange(L) / SR
            roar = bandnoise(L, 80, 500) * 0.05 * np.minimum(1, tt / 0.8) * np.minimum(1, (arg - tt) / 0.3)
            add(sfx, at, roar)
            for c in np.arange(0.3, arg - 0.2, 0.23):
                if RNG.random() < 0.55:
                    CL = int(0.012 * SR)
                    add(sfx, at + c + RNG.uniform(0, 0.15), bandnoise(CL, 2000, 7000) * np.hanning(CL) * RNG.uniform(0.03, 0.09))
        elif kind == 'whoosh':
            L = int(0.9 * SR)
            tt = np.arange(L) / SR
            s = bandnoise(L, 200, 2500) * np.sin(np.pi * tt / 0.9) ** 3
            add(sfx, at, s * 0.5)
        elif kind == 'swell':  # the thing on the wall: a cluster that leans in
            L = int(5.0 * SR)
            tt = np.arange(L) / SR
            env = np.sin(np.pi * np.minimum(tt / 5.0, 1)) ** 2
            s = sum(np.sin(2 * np.pi * f * tt + np.sin(tt * 3 + f) * 0.6) for f in (146.8, 155.6, 220.0, 311.1))
            s += np.sin(2 * np.pi * 36 * tt) * 1.5
            add(music, at, s / 5.5 * env * 0.32)
        elif kind == 'snuff':
            L = int(1.2 * SR)
            tt = np.arange(L) / SR
            puff = bandnoise(L, 150, 1800) * np.exp(-tt * 5) * 0.5
            drop = np.sin(2 * np.pi * (70 - 35 * tt) * tt) * np.exp(-tt * 3) * 0.4
            add(sfx, at, puff + drop)
        elif kind == 'tick':
            L = int(0.07 * SR)
            tt = np.arange(L) / SR
            add(sfx, at, (bandnoise(L, 1200, 4000) * np.exp(-tt * 70)) * 0.12)
        elif kind == 'slide':
            L = int(arg * SR)
            tt = np.arange(L) / SR
            for c in np.arange(0, arg, 0.08):
                CL = int(0.02 * SR)
                add(sfx, at + c, np.sin(2 * np.pi * 2400 * np.arange(CL) / SR) * np.exp(-np.arange(CL) / SR * 200) * 0.05)
        elif kind == 'sting':  # title hit
            L = int(4.0 * SR)
            tt = np.arange(L) / SR
            s = np.sin(2 * np.pi * 36.7 * tt) * np.exp(-tt * 0.9) * 0.6
            s += bell(NOTE['D4'], 4.0, 0.35)[:L] + bell(NOTE['A4'], 4.0, 0.2)[:L]
            add(music, at, s)

    music = reverb(music, 3.0, 0.4)
    sfx = reverb(sfx, 1.4, 0.18)
    # duck the music under the duck cues (silence after the snuff)
    duck = np.ones(n)
    for a, b in cues['silence']:
        duck[int(a * SR):int(b * SR)] = 0.1
    duck = smooth(duck, SR // 3)
    mix = music * duck * 0.9 + sfx + amb
    # a little stereo: ambience decorrelated, music slightly wide
    left = mix + 0.3 * np.roll(amb, 331) - 0.3 * amb
    right = mix + 0.3 * np.roll(amb, -517) - 0.3 * amb
    st = np.stack([left, right], 1)[:int(total * SR)]
    fn = int(1.0 * SR)
    st[:fn] *= np.linspace(0, 1, fn)[:, None]
    st[-int(2.0 * SR):] *= np.linspace(1, 0, int(2.0 * SR))[:, None]
    # normalise, then a soft limiter so the quiet room still reads on laptop speakers
    st /= max(1e-9, np.max(np.abs(st)))
    st = np.tanh(st * 2.2) / np.tanh(2.2) * 0.9
    return st


def write_wav(path, st):
    pcm = (np.clip(st, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def panel_hit(x, y):
    return x > 1000


def take_cues(name, t0, cues):
    """sound cues from a take's real pointer events; t0 = when frame 0 of the take plays"""
    take = TAKES[name]()
    ev = take.events
    down_at = None
    lit_from = None
    candle_y = 378
    for f, kind, x, y in ev:
        at = t0 + (f - 2) / 60
        if kind == 'down':
            down_at = (at, x, y)
            if panel_hit(x, y):
                cues['sfx'].append((at, 'click', 0))
                if abs(y - candle_y) < 30:
                    if lit_from is None:
                        cues['sfx'].append((at + 0.05, 'match', 0))
                        lit_from = at
                    else:
                        cues['sfx'].append((at + 0.05, 'snuff', 0))
                        cues['sfx'].append((lit_from + 0.5, 'flame', at - lit_from - 0.5))
                        cues['lit'].append((lit_from, at))
                        cues['silence'].append((at, at + 3.2))
                        lit_from = None
        elif kind == 'up' and down_at is not None:
            a, x0, y0 = down_at
            if knife_zone(x0, y0) and not panel_hit(x0, y0):
                cues['sfx'].append((a, 'scrape', max(0.1, at - a)))
                # did it close? (start and end close together)
                if math.hypot(x - x0, y - y0) < 12:
                    cues['sfx'].append((at, 'pop', 0))
                    cues['sfx'].append((at + 0.55, 'thud', 0.8))
            elif panel_hit(x0, y0) and abs(x - x0) > 30:
                cues['sfx'].append((a, 'slide', max(0.1, at - a)))
            down_at = None
    end = t0 + take.frames() / 60
    if lit_from is not None:
        cues['sfx'].append((lit_from + 0.5, 'flame', end - lit_from - 0.5))
        cues['lit'].append((lit_from, end))
    for a, b in cues['lit']:
        if a >= t0 - 0.01 and b - a > 7:
            cues['sfx'].append((a + 6.0, 'swell', 0))
    # the gust: the fast sweep
    sweeps = [f1 for (f1, k1, x1, y1), (f2, k2, x2, y2) in zip(ev, ev[1:])
              if k1 == k2 == 'move' and f2 - f1 <= 2 and abs(x2 - x1) > 100]
    if sweeps and cues['lit'] and cues['lit'][-1][0] < t0 + sweeps[-1] / 60:
        cues['sfx'].append((t0 + (sweeps[-1] - 6) / 60 - 0.1, 'whoosh', 0))
    return take


def build_sound(nc, nm, wav='/tmp/hollow_sound.wav'):
    n_title = int(TITLE_SEC * FPS)
    n_make = int(MAKE_SEC * FPS)
    n_end = int(END_SEC * FPS)
    t_carve = (n_title + n_make) / FPS
    t_mash = (n_title + n_make + nc - XFADE) / FPS
    total_frames = n_title + n_make + nc + nm - XFADE + n_end
    total = total_frames / FPS

    # sound cues
    cues = {'sfx': [], 'lit': [], 'silence': [], 'music': [], 'pads': [],
            'scene': (t_carve, t_mash + nm / FPS)}
    cues['sfx'].append((0.25, 'sting', 0))
    take_cues('carve', t_carve, cues)
    mash = take_cues('mash', t_mash, cues)
    # the stencil's knife ticks while the script traces it
    downs = [f for f, k, x, y in mash.events if k == 'down']
    for i in range(40):
        cues['sfx'].append((t_mash + downs[0] / 60 + 0.25 + i * 0.085, 'tick', 0))
    carve_lit = [c for c in cues['lit'] if c[0] < t_mash]
    mash_lit = [c for c in cues['lit'] if c[0] >= t_mash]
    cues['music'] = [(1.2, t_carve + 1.0, 0.16),
                     (t_carve + 1.0, carve_lit[0][0], 0.07),
                     (carve_lit[0][0], carve_lit[0][1], 0.13),
                     (carve_lit[0][1] + 3.0, mash_lit[0][0] if mash_lit else t_mash + 5, 0.08),
                     (mash_lit[0][0] if mash_lit else t_mash + 5, total - END_SEC, 0.12),
                     (total - END_SEC, total - 1.0, 0.15)]
    cues['pads'] = [(0.0, t_carve + 2, ['D4', 'F4', 'A4'], 0.10),
                    (t_carve, carve_lit[0][0] + 1, ['D4', 'A4'], 0.05),
                    (carve_lit[0][0], carve_lit[0][1] + 1, ['D4', 'F4', 'Bb4'], 0.09),
                    (carve_lit[0][1] + 2, total, ['D4', 'F4', 'A4'], 0.07)]
    st = soundtrack(total, cues)
    write_wav(wav, st)

    return n_title, n_make, n_end, total, wav


def main():
    global BG, TITLE_BG, THUMBS
    frames_dir, out = sys.argv[1], sys.argv[2]
    BG = vignette_bg()
    meta = {n: take_meta(frames_dir, n) for n in ('carve', 'mash')}
    nc, nm = len(meta['carve']), len(meta['mash'])
    hero = Image.open(os.path.join(frames_dir, 'carve', f'{min(nc - 1, 960):05d}.png'))
    TITLE_BG = dimmed(hero.crop((120, 120, 1160, 770)).resize((W, H), Image.LANCZOS), 16, 0.6)
    THUMBS = []
    tw = 426
    for k in range(0, nc, 27):
        im = Image.open(os.path.join(frames_dir, 'carve', f'{k:05d}.png')).convert('RGB')
        im = im.resize((tw, int(tw * H / W)), Image.LANCZOS).convert('RGBA')
        border = Image.new('RGBA', im.size, (0, 0, 0, 0))
        ImageDraw.Draw(border).rectangle([0, 0, im.size[0] - 1, im.size[1] - 1], outline=(255, 255, 255, 40))
        im.alpha_composite(border)
        THUMBS.append((k, im))

    n_title, n_make, n_end, total, wav = build_sound(nc, nm)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    ff = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                           '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', wav,
                           '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-maxrate', '4200k', '-bufsize', '8400k',
                           '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-c:a', 'aac', '-b:a', '160k',
                           '-shortest', out], stdin=subprocess.PIPE)

    def put(img):
        ff.stdin.write(img.convert('RGB').tobytes())

    for k in range(n_title):
        put(fade(title_card(k), min(1.0, k / 20, (n_title - k) / 12)))
    for k in range(n_make):
        put(fade(code_card(k), min(1.0, k / 12, (n_make - k) / 12)))
    prev_tail = []
    for k in range(nc):
        img = take_frame(frames_dir, 'carve', meta['carve'], k)
        if k < 12:
            img = fade(img, k / 12)
        if k >= nc - XFADE:
            prev_tail.append(img)
            continue
        put(img)
    for k in range(nm):
        img = take_frame(frames_dir, 'mash', meta['mash'], k)
        if k < XFADE:
            img = Image.blend(prev_tail[k], img, (k + 1) / (XFADE + 1))
        if k >= nm - 12:
            img = fade(img, (nm - k) / 12)
        put(img)
    for k in range(n_end):
        put(fade(end_card(k), min(1.0, k / 15, (n_end - k) / 20)))
    ff.stdin.close()
    ff.wait()
    print('wrote', out, round(total, 1), 's')


if __name__ == '__main__':
    main()
