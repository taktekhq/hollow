#!/usr/bin/env python3
"""Cuts the demo video: title, a look at the source and the CLI loop, the two
takes rendered by tools/render_take.py (with the pointer drawn on top), an end
card, and a quiet synthesised soundtrack. Needs Pillow and numpy.

    ~/venvs/pw/bin/python tools/make_video.py /tmp/hollow_frames media/hollow.mp4
"""
import math
import os
import shutil
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
from timeline import TAKES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, 'fonts')
W, H = 1280, 800
FPS = 30

CREAM = (242, 230, 208)
MUTED = (156, 147, 132)
AMBER = (240, 160, 64)
INK = (12, 10, 14)


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


DISPLAY = 'CormorantGaramond-SemiBoldItalic.ttf'
SERIF = 'CormorantGaramond-Medium.ttf'
MONO = 'IBMPlexMono-Medium.ttf'


# ---------------------------------------------------------------------------
# pointer overlay

def arrow(scale=1.0):
    pts = [(0, 0), (0, 22), (5.5, 17), (9.5, 26), (13, 24.5), (9, 16), (16, 16)]
    img = Image.new('RGBA', (40, 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p = [(4 + x * scale, 4 + y * scale) for x, y in pts]
    shadow = Image.new('RGBA', (40, 40), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon([(x + 1.5, y + 2) for x, y in p], fill=(0, 0, 0, 120))
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(1.5)))
    d = ImageDraw.Draw(img)
    d.polygon(p, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
    return img


ARROW = arrow()


def knife_zone(x, y):
    dx = (x - 500) / (214 + 60)
    dy = (y - 464) / (160 + 60)
    return dx * dx + dy * dy <= 1


def overlay_pointer(img, x, y, down, since_down):
    if not knife_zone(x, y):
        img.alpha_composite(ARROW, (int(x) - 4, int(y) - 4))
    if since_down < 22:
        # a click ring, so the viewer can see the press
        t = since_down / 22
        r = 8 + 26 * t
        ring = Image.new('RGBA', img.size, (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse([x - r, y - r, x + r, y + r], outline=(255, 214, 150, int(200 * (1 - t))), width=2)
        img.alpha_composite(ring)


# ---------------------------------------------------------------------------
# cards

def vignette_bg():
    bg = Image.new('RGB', (W, H), INK)
    glow = Image.new('L', (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W * 0.15, H * 0.05, W * 0.85, H * 1.1], fill=60)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    warm = Image.new('RGB', (W, H), (90, 44, 12))
    return Image.composite(warm, bg, glow).convert('RGBA')


BG = None


def title_card(alpha=1.0):
    img = BG.copy()
    d = ImageDraw.Draw(img)
    f1 = font(DISPLAY, 150)
    d.text((W / 2, 300), 'Hollow', font=f1, fill=CREAM, anchor='mm')
    f2 = font(MONO, 15)
    d.text((W / 2, 410), "CARVE IT  ·  LIGHT IT  ·  DON'T TRUST WHAT IT CASTS", font=f2, fill=MUTED, anchor='mm')
    f3 = font(SERIF, 30)
    d.text((W / 2, 500), 'An interactive jack-o’-lantern for the Rive Halloween Challenge', font=f3, fill=CREAM, anchor='mm')
    d.text((W / 2, 545), 'Rive CLI  ·  RML  ·  Luau scripting  ·  GPU Canvas (WGSL)  ·  data binding  ·  state machines',
           font=font(MONO, 14), fill=AMBER, anchor='mm')
    return fade(img, alpha)


def fade(img, a):
    if a >= 1:
        return img
    black = Image.new('RGBA', img.size, (0, 0, 0, 255))
    return Image.blend(black, img, max(0.0, a))


KW = {'local', 'function', 'end', 'if', 'then', 'else', 'elseif', 'return', 'for', 'do', 'in', 'let', 'var', 'fn',
      'while', 'and', 'or', 'not', 'struct'}


def code_lines(path, start, count):
    with open(os.path.join(ROOT, path)) as f:
        lines = f.read().split('\n')
    return lines[start - 1:start - 1 + count]


def draw_code(d, x, y, lines, size=13, color=CREAM, lh=None):
    f = font(MONO, size)
    lh = lh or int(size * 1.55)
    for i, line in enumerate(lines):
        yy = y + i * lh
        s = line.rstrip()
        if s.strip().startswith(('--', '//')):
            d.text((x, yy), s, font=f, fill=(120, 112, 100))
            continue
        # crude highlighting: keywords amber, strings green, the rest cream
        cx = x
        for tok in tokenize(s):
            c = color
            if tok in KW:
                c = AMBER
            elif tok.startswith(("'", '"')):
                c = (170, 206, 140)
            elif tok.startswith('<') or tok.startswith('</'):
                c = (232, 150, 90)
            d.text((cx, yy), tok, font=f, fill=c)
            cx += f.getlength(tok)


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


PANES = [
    ('scene.rml', 'RML · the candle button toggles a view-model boolean (negate converter)', 'scene.rml', 382, 8),
    ('main.luau', 'LUAU · a closed knife stroke becomes a hole and the piece falls out', 'main.luau', 646, 20),
    ('light.wgsl', 'WGSL · rays: march toward the flame, collecting light that leaks through the cuts', 'light.wgsl', 183, 16),
]


def code_card(k, n):
    """k-th frame of n: three source panes slide in, then the CLI loop types out."""
    img = BG.copy()
    d = ImageDraw.Draw(img)
    d.text((60, 46), 'How it’s made', font=font(DISPLAY, 46), fill=CREAM)
    d.text((62, 104), 'Plain text files, written with a coding agent, built and tested headless by the Rive CLI. No editor yet.',
           font=font(SERIF, 22), fill=MUTED)
    t = k / FPS
    i = min(2, int(t / 2.6))
    local = t - i * 2.6
    name, caption, path, start, count = PANES[i]
    appear = min(1.0, local / 0.3) if i > 0 or local > 0 else 1.0
    pane = Image.new('RGBA', (1160, 490), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pane)
    pd.rounded_rectangle([0, 0, 1159, 489], 16, fill=(20, 17, 22, 250), outline=(255, 255, 255, 30))
    pd.text((26, 20), name, font=font(MONO, 15), fill=AMBER)
    pd.text((26 + font(MONO, 15).getlength(name) + 18, 21), caption, font=font(MONO, 14), fill=MUTED)
    draw_code(pd, 26, 62, code_lines(path, start, count), size=15, lh=21)
    pane = fade(pane, appear) if appear < 1 else pane
    img.alpha_composite(pane, (60, 150 + int((1 - appear) * 20)))
    # the terminal
    tx, ty = 60, 660
    term = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(term).rounded_rectangle([tx, ty, tx + 1160, ty + 110], 14, fill=(8, 8, 10, 255), outline=(255, 255, 255, 30))
    img.alpha_composite(term)
    d = ImageDraw.Draw(img)
    cmds = [
        ('$ rive hollow --verify', 'rive  verified (0 errors, 0 warnings)'),
        ('$ rive hollow --screenshot=f.png --pointer=down@405,392 --pointer=move@410,380 ... --advance=2', 'rive  wrote f.png   (one frame of this video; every frame is a replay of real input)'),
    ]
    f = font(MONO, 14)
    line_t = t - 1.0
    for i, (c, r) in enumerate(cmds):
        lt = line_t - i * 2.6
        if lt < 0:
            continue
        typed = c[:int(lt * 38)]
        d.text((tx + 20, ty + 18 + i * 44), typed, font=f, fill=CREAM)
        if lt * 38 > len(c) + 6:
            d.text((tx + 20, ty + 40 + i * 44), r, font=font(MONO, 12), fill=(140, 200, 140))
    return img


def end_card(alpha=1.0):
    img = BG.copy()
    d = ImageDraw.Draw(img)
    d.text((W / 2, 250), 'Hollow', font=font(DISPLAY, 120), fill=CREAM, anchor='mm')
    lines = [
        'Carve with the pointer: close a cut and the piece falls out. Etch for a softer glow.',
        'Light the candle: a WGSL pass lights the room through whatever you carved.',
        'Keep it lit long enough and something on the wall looks back.',
    ]
    for i, l in enumerate(lines):
        d.text((W / 2, 370 + i * 40), l, font=font(SERIF, 27), fill=CREAM, anchor='mm')
    d.text((W / 2, 530), 'Rive CLI  ·  RML  ·  Luau  ·  WGSL GPU Canvas  ·  data binding  ·  state machines',
           font=font(MONO, 14), fill=AMBER, anchor='mm')
    d.text((W / 2, 640), 'Taktek  ·  github.com/taktekhq/hollow  ·  #rivehalloweenchallenge  @rive_app',
           font=font(MONO, 14), fill=MUTED, anchor='mm')
    return fade(img, alpha)


# ---------------------------------------------------------------------------
# callouts over the takes: what Rive feature is doing the work right now

CALLOUTS = {
    'carve': [(30, 250, 'LUAU', 'your strokes become cuts; close one and the piece pops out'),
              (372, 470, 'STATE MACHINE', 'tool pill, eased with a hand-tuned overshoot'),
              (512, 650, 'GPU CANVAS · WGSL', 'light leaks through the carving: glow, rays, projection'),
              (652, 770, 'DATA BINDING', 'sliders write the view model; the shader reads it'),
              (860, 1000, 'WGSL', 'the haze shows a second picture nobody carved'),
              (1157, 1260, 'STATE MACHINE + LUAU', 'snuffed: smoke, and the eyes stay a moment longer')],
    'mash': [(20, 170, 'STENCIL', 'the script carves a mashrabiya, star by star'),
             (190, 330, 'WGSL', 'eight-point stars thrown across the room')],
}


def callout(img, label, text, a):
    f1 = font(MONO, 11)
    f2 = font(SERIF, 21)
    w = f1.getlength(label) + f2.getlength(text) + 64
    x = 640 - w / 2 - 70
    y = 22
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x, y, x + w, y + 38], 19, fill=(10, 8, 12, int(215 * a)), outline=(240, 160, 64, int(90 * a)))
    d.text((x + 20, y + 19), label, font=f1, fill=(*AMBER, int(255 * a)), anchor='lm')
    d.text((x + 34 + f1.getlength(label), y + 18), text, font=f2, fill=(*CREAM, int(255 * a)), anchor='lm')
    img.alpha_composite(layer)


def take_frames(frames_dir, name):
    meta = {}
    with open(os.path.join(frames_dir, name, 'pointer.tsv')) as f:
        for line in f:
            k, x, y, down, since = line.split()
            meta[int(k)] = (float(x), float(y), int(down), int(since) // 2)
    n = len(meta)
    for k in range(n):
        p = os.path.join(frames_dir, name, f'{k:05d}.png')
        if not os.path.exists(p):
            continue
        img = Image.open(p).convert('RGBA')
        x, y, down, since = meta[k]
        overlay_pointer(img, x, y, down, since)
        for (a, b, label, text) in CALLOUTS.get(name, []):
            if a <= k <= b:
                fa = min(1.0, (k - a) / 8, (b - k) / 8)
                callout(img, label, text, max(0.0, fa))
        yield img


# ---------------------------------------------------------------------------
# sound

SR = 44100


def soundtrack(total_sec, events):
    n = int(total_sec * SR)
    rng = np.random.default_rng(7)
    out = np.zeros(n)
    # room tone: brown noise, low-passed, slowly breathing
    white = rng.standard_normal(n)
    brown = np.cumsum(white)
    brown -= np.convolve(brown, np.ones(4410) / 4410, mode='same')
    brown /= np.max(np.abs(brown)) + 1e-9
    t = np.arange(n) / SR
    out += brown * 0.10 * (0.7 + 0.3 * np.sin(t * 0.4))
    # a low drone, two detuned sines
    out += 0.035 * (np.sin(2 * np.pi * 55 * t) + np.sin(2 * np.pi * 55.4 * t + 1)) * (0.6 + 0.4 * np.sin(t * 0.21))

    def add(at, sig):
        i = int(at * SR)
        j = min(n, i + len(sig))
        if i < n:
            out[i:j] += sig[:j - i]

    for at, kind in events:
        if kind == 'thock':  # a knife popping a piece out
            L = int(0.25 * SR)
            tt = np.arange(L) / SR
            sig = np.sin(2 * np.pi * (140 - 60 * tt) * tt) * np.exp(-tt * 22) * 0.5
            sig += rng.standard_normal(L) * np.exp(-tt * 60) * 0.12
            add(at, sig)
        elif kind == 'match':
            L = int(1.4 * SR)
            tt = np.arange(L) / SR
            hiss = rng.standard_normal(L)
            hiss = np.diff(np.concatenate([[0], hiss]))
            env = np.where(tt < 0.06, tt / 0.06, np.exp(-(tt - 0.06) * 5))
            add(at, hiss * env * 0.18)
            # the flame catching: a soft low whoomp
            add(at + 0.08, np.sin(2 * np.pi * 70 * tt) * np.exp(-tt * 6) * 0.25)
        elif kind == 'whoosh':
            L = int(0.7 * SR)
            tt = np.arange(L) / SR
            sig = rng.standard_normal(L)
            sig = np.convolve(sig, np.ones(30) / 30, mode='same')
            add(at, sig * np.sin(np.pi * tt / 0.7) ** 2 * 0.6)
        elif kind == 'snuff':
            L = int(0.9 * SR)
            tt = np.arange(L) / SR
            sig = np.convolve(rng.standard_normal(L), np.ones(12) / 12, mode='same')
            add(at, sig * np.exp(-tt * 4) * 0.5)
        elif kind == 'tick':
            L = int(0.06 * SR)
            tt = np.arange(L) / SR
            add(at, np.sin(2 * np.pi * 900 * tt) * np.exp(-tt * 90) * 0.08)
        elif kind == 'swell':  # the thing on the wall
            L = int(4.0 * SR)
            tt = np.arange(L) / SR
            env = np.sin(np.pi * tt / 4.0) ** 2
            sig = (np.sin(2 * np.pi * 220 * tt) * 0.5 + np.sin(2 * np.pi * 233.1 * tt) * 0.5 +
                   np.sin(2 * np.pi * 329.6 * tt) * 0.3) * env * 0.05
            add(at, sig)
    # gentle fade in and out, then normalise
    fade_n = int(1.5 * SR)
    out[:fade_n] *= np.linspace(0, 1, fade_n)
    out[-fade_n:] *= np.linspace(1, 0, fade_n)
    out /= max(1e-9, np.max(np.abs(out))) / 0.7
    return out


def write_wav(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    stereo = np.repeat(pcm[:, None], 2, axis=1)
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())


# ---------------------------------------------------------------------------

def main():
    global BG
    frames_dir, out = sys.argv[1], sys.argv[2]
    BG = vignette_bg()
    tmp = '/tmp/hollow_video'
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    idx = [0]
    marks = {}

    def put(img):
        img.convert('RGB').save(os.path.join(tmp, f'{idx[0]:05d}.jpg'), quality=94)
        idx[0] += 1

    # title, 3 s
    for k in range(90):
        a = min(1.0, k / 18, (90 - k) / 14)
        put(title_card(a))
    # how it's made, 8.5 s
    n = 255
    for k in range(n):
        img = code_card(k, n)
        put(fade(img, min(1.0, k / 10, (n - k) / 10)))
    marks['carve'] = idx[0] / FPS
    prev = None
    carve = list_frames(frames_dir, 'carve')
    for i, img in enumerate(carve):
        if i < 10:
            img = fade(img, i / 10)
        put(img)
        prev = img
    # crossfade into the mashrabiya take
    marks['mash'] = idx[0] / FPS - 0.5
    mash = list_frames(frames_dir, 'mash')
    for i, img in enumerate(mash):
        if i < 15 and prev is not None:
            img = Image.blend(prev, img, i / 15)
        put(img)
        prev = img
    # end card, 4 s
    for k in range(120):
        a = min(1.0, k / 15, (120 - k) / 12)
        put(end_card(a))
    total = idx[0] / FPS

    # sound events from the takes' real input
    ev = []
    carve_t = TAKES['carve']()
    for f, kind, x, y in carve_t.events:
        at = marks['carve'] + (f / 60)
        if kind == 'up' and knife_zone(x, y):
            ev.append((at, 'thock'))
        if kind == 'down' and abs(x - 1108) < 120 and abs(y - 378) < 30:
            ev.append((at, 'match' if not any(e[1] == 'match' for e in ev) else 'snuff'))
    # the gust and the swell, from the take's known beats (sim seconds)
    gust_f = [f for f, k, x, y in carve_t.events if k == 'move' and x < 200]
    if gust_f:
        ev.append((marks['carve'] + gust_f[0] / 60 - 0.25, 'whoosh'))
    candle = [e for e in ev if e[1] == 'match']
    if candle:
        ev.append((candle[0][0] + 6.2, 'swell'))
    mash_t = TAKES['mash']()
    downs = [f for f, k, x, y in mash_t.events if k == 'down']
    if downs:
        start = marks['mash'] + 0.5 + downs[0] / 60
        for i in range(34):
            ev.append((start + 0.15 + i * 0.085, 'tick'))
        if len(downs) > 1:
            ev.append((marks['mash'] + 0.5 + downs[1] / 60, 'match'))
            ev.append((marks['mash'] + 0.5 + downs[1] / 60 + 6.2, 'swell'))
    write_wav(os.path.join(tmp, 'sound.wav'), soundtrack(total, ev))

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-framerate', str(FPS), '-i', os.path.join(tmp, '%05d.jpg'),
                    '-i', os.path.join(tmp, 'sound.wav'), '-c:v', 'libx264', '-preset', 'slow', '-crf', '21',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-c:a', 'aac', '-b:a', '128k', '-shortest', out],
                   check=True)
    print('wrote', out, round(total, 1), 's')


def list_frames(frames_dir, name):
    return take_frames(frames_dir, name)


if __name__ == '__main__':
    main()
