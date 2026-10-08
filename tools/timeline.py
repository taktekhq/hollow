#!/usr/bin/env python3
"""The demo the video plays: a person's pointer, as a list of timed events.

Times are in simulation frames at 60 fps. Every event is real input: the CLI
replays it through the runtime's own dispatch (`--pointer=down|move|up`), so
the knife, the buttons, the sliders and the state machine all react exactly as
they would under a mouse. Nothing in the scene is keyframed for the video.
"""
import math

FPS = 60


class Take:
    def __init__(self, start=(1180, 760)):
        self.events = []  # (frame, kind, x, y)
        self.f = 1
        self.x, self.y = start
        self.events.append((self.f, 'move', self.x, self.y))

    # -- primitives -----------------------------------------------------
    def _ev(self, kind, x, y):
        self.events.append((self.f, kind, round(x), round(y)))
        self.x, self.y = x, y

    def wait(self, sec):
        self.f += int(round(sec * FPS))
        return self

    def glide(self, x, y, sec=0.6, arc=0.12, wobble=2.0):
        """an eased, slightly curved hand movement to (x, y)"""
        x0, y0 = self.x, self.y
        n = max(1, int(sec * FPS / 2))
        dx, dy = x - x0, y - y0
        nx, ny = -dy, dx  # normal, for the arc
        for i in range(1, n + 1):
            t = i / n
            e = t * t * (3 - 2 * t)
            bow = math.sin(math.pi * t) * arc
            px = x0 + dx * e + nx * bow + math.sin(i * 1.7) * wobble * (1 - t)
            py = y0 + dy * e + ny * bow + math.cos(i * 1.3) * wobble * (1 - t)
            self.f += 2
            self._ev('move', px, py)
        return self

    def path(self, pts, sec, press=True, jitter=1.2):
        """drag through a polyline at an even speed (press=False just hovers)"""
        self.glide(pts[0][0], pts[0][1], 0.35)
        if press:
            self.f += 2
            self._ev('down', *pts[0])
        segs = list(zip(pts, pts[1:]))
        total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs)
        n = max(2, int(sec * FPS / 2))
        for i in range(1, n + 1):
            d = total * (i / n)
            acc = 0
            for a, b in segs:
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                if acc + L >= d or (a, b) == segs[-1]:
                    u = 0 if L == 0 else min(1, (d - acc) / L)
                    px = a[0] + (b[0] - a[0]) * u + math.sin(i * 2.3) * jitter
                    py = a[1] + (b[1] - a[1]) * u + math.cos(i * 1.9) * jitter
                    break
                acc += L
            self.f += 2
            self._ev('move', px, py)
        if press:
            self.f += 2
            self._ev('up', pts[-1][0], pts[-1][1])
        return self

    def click(self, x, y, travel=0.55):
        self.glide(x, y, travel)
        self.f += 6
        self._ev('down', x, y)
        self.f += 6
        self._ev('up', x, y)
        return self

    def drag_slider(self, x0, x1, y, sec):
        self.glide(x0, y, 0.45)
        self.f += 4
        self._ev('down', x0, y)
        n = max(2, int(sec * FPS / 2))
        for i in range(1, n + 1):
            t = i / n
            e = t * t * (3 - 2 * t)
            self.f += 2
            self._ev('move', x0 + (x1 - x0) * e, y + math.sin(i) * 1.5)
        self.f += 4
        self._ev('up', x1, y)
        return self

    def frames(self):
        return self.f


# ---------------------------------------------------------------------------
# geometry for the hand-carved face (artboard units)

def tri(cx, cy, w, h, tilt=0):
    return [(cx - w / 2, cy + h / 2 + tilt), (cx - w * 0.1, cy - h / 2), (cx + w / 2, cy + h / 2 - tilt),
            (cx - w / 2 + 4, cy + h / 2 + tilt + 2)]


def take_carve():
    """Segment A: carve by hand, light, meet the thing on the wall, snuff."""
    t = Take()
    t.glide(760, 300, 0.9).wait(0.3)
    # left eye, then the right: closed shapes pop out
    t.path(tri(405, 392, 104, 84, 10), 1.25).wait(0.45)
    t.path([(p[0] + 0, p[1]) for p in [(546, 404), (634, 350), (604, 432), (548, 406)]], 1.15).wait(0.4)
    # nose
    t.path([(484, 470), (500, 438), (518, 470), (486, 472)], 0.8).wait(0.35)
    # the mouth: a wide grin with two teeth
    mouth = [(372, 508), (404, 534), (430, 538), (432, 516), (462, 516), (466, 546), (536, 546), (540, 516),
             (570, 516), (572, 538), (604, 530), (632, 504), (604, 574), (536, 594), (468, 594), (404, 572),
             (374, 510)]
    t.path(mouth, 3.0).wait(0.5)
    # a slit for a scar
    t.path([(612, 300), (640, 322), (664, 352)], 0.5).wait(0.3)
    # etch: switch tool, shave two angry brows
    t.click(1163, 102).wait(0.25)
    t.path([(378, 356), (408, 336), (456, 352)], 0.7).wait(0.15)
    t.path([(552, 352), (606, 328), (648, 342)], 0.7).wait(0.3)
    t.click(1057, 102).wait(0.2)
    # light it, and give it more haze and more flame straight away (the panel is
    # still up; it steps back once the pointer leaves for the room)
    t.click(1108, 378).wait(0.3)
    t.drag_slider(1130, 1205, 560, 0.9).wait(0.15)
    t.drag_slider(1172, 1216, 492, 0.5).wait(0.2)
    t.glide(760, 470, 1.2, arc=0.2).wait(0.4)
    # a hand passing by: the flame leans
    t.glide(640, 300, 0.9, arc=0.3).glide(820, 360, 0.8).wait(0.3)
    # wait for it; it watches the pointer
    t.glide(860, 250, 1.4, arc=0.1).wait(0.6)
    t.glide(300, 230, 2.2, arc=0.1).wait(0.4)
    t.glide(780, 200, 2.0, arc=-0.1).wait(0.8)
    # a fast sweep: a gust
    t.glide(840, 470, 0.4).path([(840, 470), (520, 440), (180, 420)], 0.16, press=False, jitter=0).wait(1.6)
    t.glide(700, 260, 1.2).wait(2.0)
    # snuff it out: the eyes stay a moment longer
    t.click(1108, 378).wait(0.6)
    t.glide(760, 520, 1.0).wait(2.4)
    return t


def take_mashrabiya():
    """Segment B: the mashrabiya stencil, carved by the script, then lit."""
    t = Take(start=(820, 700))
    t.click(1108, 289, 0.8).wait(0.3)
    t.glide(760, 560, 0.8).wait(3.6)
    t.click(1108, 378).wait(0.6)
    t.glide(800, 420, 1.0).wait(0.6)
    t.drag_slider(1130, 1216, 560, 1.4).wait(0.3)
    t.glide(640, 260, 1.0, arc=0.3).glide(860, 330, 1.0).wait(0.4)
    t.glide(840, 470, 0.6).wait(1.8)
    return t


def take_ghoul():
    """Segment C: the ghoul stencil (cuts and etched skin)."""
    t = Take(start=(800, 680))
    t.click(1108, 239, 0.7).wait(0.2)
    t.glide(780, 520, 0.8).wait(3.4)
    t.click(1108, 378).wait(0.5)
    t.glide(820, 430, 1.2).wait(2.2)
    return t


TAKES = {'carve': take_carve, 'mash': take_mashrabiya, 'ghoul': take_ghoul}

# The cut: which take frames (30 fps indices) play, and how fast. (start, end, step):
# step 2 plays that stretch at double speed, so only every other frame is rendered.
CUT = {
    'carve': [(0, 105, 1), (105, 305, 2), (305, 360, 1), (360, 512, 2), (512, 540, 1), (540, 610, 2), (610, 1190, 1)],
    'ghoul': [(24, 178, 3), (178, 270, 1)],
    'mash': [(0, 190, 2), (190, 320, 1)],
}
ORDER = ['carve', 'ghoul', 'mash']
COLD_OPEN = ('carve', 872, 947)   # the face on the wall, its eyes following the pointer
STILLS = {'carve': [932, 330, 1168], 'mash': [300], 'ghoul': [250]}


def cut_frames(take):
    out = set()
    for a, b, step in CUT.get(take, []):
        out.update(range(a, b, step))
    if COLD_OPEN[0] == take:
        out.update(range(COLD_OPEN[1], COLD_OPEN[2]))
    out.update(STILLS.get(take, []))
    return sorted(out)

if __name__ == '__main__':
    for k, fn in TAKES.items():
        t = fn()
        print(k, t.frames(), 'frames', round(t.frames() / FPS, 1), 's', len(t.events), 'events')
