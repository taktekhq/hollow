#!/bin/bash
# One command for all the media: verify, render the takes, cut the video, pull the stills.
#   tools/render_all.sh              # fresh render into /tmp/hollow_frames (about 1 h on a busy XPS)
#   KEEP=1 tools/render_all.sh       # reuse frames already rendered (after editing only make_video.py)
#   JOBS=8 FRAMES=/tmp/x tools/render_all.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH=$HOME/.rive/bin:$PATH
export EGL_PLATFORM=${EGL_PLATFORM:-surfaceless}   # skip the XPS's flaky second GPU
FR=${FRAMES:-/tmp/hollow_frames}
JOBS=${JOBS:-7}
PY=${PY:-$HOME/venvs/pw/bin/python}               # needs numpy + Pillow
VIEW=(--viewport 1600x1000 --data quality=1.25)

rive . --verify
[ "${KEEP:-0}" = 1 ] || rm -rf "$FR"
python3 tools/render_take.py carve "$FR/carve" --jobs "$JOBS" "${VIEW[@]}"
python3 tools/render_take.py mash  "$FR/mash"  --jobs "$JOBS" "${VIEW[@]}"
python3 tools/render_take.py ghoul "$FR/ghoul" --jobs 2 "${VIEW[@]}" --only 290
"$PY" tools/make_video.py "$FR" media/hollow.mp4
"$PY" tools/make_stills.py "$FR"
ls -la media
