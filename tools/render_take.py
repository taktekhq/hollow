#!/usr/bin/env python3
"""Renders one take of tools/timeline.py into a PNG sequence with the Rive CLI.

Every frame is its own headless `rive --screenshot` run that replays the
pointer events up to that moment and captures (the CLI has no video mode, but
advancing is cheap: a 40 s replay costs a few seconds). Workers each get
their own copy of the project so parallel builds don't trip over build/.

    python3 tools/render_take.py carve out/carve --fps 30 --jobs 8 [--every 3]
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
from timeline import TAKES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIVE = os.path.expanduser('~/.rive/bin/rive')
# the XPS's second GPU (nouveau) sometimes fails to resume and Mesa's default
# EGL platform then gives up; the surfaceless platform goes straight to the iGPU
os.environ.setdefault('EGL_PLATFORM', 'surfaceless')
FILES = ['rive.yaml', 'scene.rml', 'main.luau', 'light.wgsl', 'fonts']


def worker_dir(i, tag):
    d = f'/tmp/hollow_render/{tag}_w{i}'
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)
    for f in FILES:
        src = os.path.join(ROOT, f)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(d, f))
        else:
            shutil.copy(src, d)
    return d


def args_for(events, capture, extra):
    out = list(extra)
    cur = 0
    for (f, kind, x, y) in events:
        if f >= capture:
            break
        if f > cur:
            out.append(f'--advance={f - cur}')
            cur = f
        out.append(f'--pointer={kind}@{x},{y}')
    out.append(f'--advance={max(1, capture - cur)}')
    return out


def pointer_at(events, capture):
    x, y, down, last_down = 0, 0, False, -999
    for (f, kind, ex, ey) in events:
        if f >= capture:
            break
        x, y = ex, ey
        if kind == 'down':
            down, last_down = True, f
        elif kind == 'up':
            down = False
    return x, y, down, last_down


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('take')
    ap.add_argument('out')
    ap.add_argument('--fps', type=int, default=30)
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--every', type=int, default=1, help='render every Nth frame (previews)')
    ap.add_argument('--viewport', default='')
    ap.add_argument('--only', default='', help='comma list of frame indices')
    ap.add_argument('--data', action='append', default=[])
    a = ap.parse_args()

    take = TAKES[a.take]()
    events = take.events
    step = 60 // a.fps
    n = take.frames() // step
    os.makedirs(a.out, exist_ok=True)
    extra = []
    if a.viewport:
        extra += [f'--viewport={a.viewport}', '--fit=contain']
    for d in a.data:
        extra.append(f'--data={d}')
    tag = f'{a.take}_{os.getpid()}'
    dirs = [worker_dir(i, tag) for i in range(a.jobs)]
    todo = [k for k in range(0, n, a.every) if not os.path.exists(os.path.join(a.out, f'{k:05d}.png'))]
    if a.only:
        todo = [int(v) for v in a.only.split(',')]
    meta = open(os.path.join(a.out, 'pointer.tsv'), 'w')
    for k in range(n):
        c = 2 + k * step
        x, y, down, ld = pointer_at(events, c)
        meta.write(f'{k}\t{x}\t{y}\t{int(down)}\t{c - ld}\n')
    meta.close()

    def run(job):
        idx, k = job
        d = dirs[idx % a.jobs]
        c = 2 + k * step
        png = os.path.join(os.path.abspath(a.out), f'{k:05d}.png')
        cmd = [RIVE, d, f'--screenshot={png}.tmp.png', '--quiet'] + args_for(events, c, extra)
        for attempt in range(3):
            r = subprocess.run(cmd, capture_output=True, text=True)
            if os.path.exists(png + '.tmp.png'):
                os.replace(png + '.tmp.png', png)
                return k
        print('FAILED', k, r.stderr[-400:], file=sys.stderr)
        return -1

    # each worker dir handles every jobs-th task, so no two runs share a dir
    def lane(i):
        done = 0
        for j, k in enumerate(todo):
            if j % a.jobs == i:
                run((i, k))
                done += 1
                if done % 20 == 0:
                    print(f'lane {i}: {done}', flush=True)

    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(lane, range(a.jobs)))
    print('done', a.take, len(todo), 'frames')


if __name__ == '__main__':
    main()
