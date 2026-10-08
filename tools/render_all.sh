#!/bin/bash
# One command for all the media: verify, render the takes, cut the video, pull the stills.
#   tools/render_all.sh              # fresh render into /tmp/hollow_frames2 (about 1 h on a busy XPS)
#   KEEP=1 tools/render_all.sh       # reuse frames already rendered (after editing only make_video.py)
#   JOBS=8 FRAMES=/tmp/x tools/render_all.sh
#   EDITOR_CLIP=media/editor.mov KEEP=1 tools/render_all.sh   # splice the Rive Editor clip in after "how it's made"
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH=$HOME/.rive/bin:$PATH
export EGL_PLATFORM=${EGL_PLATFORM:-surfaceless}   # skip the XPS's flaky second GPU
FR=${FRAMES:-/tmp/hollow_frames2}
JOBS=${JOBS:-7}
PY=${PY:-$HOME/venvs/pw/bin/python}               # needs numpy + Pillow
VIEW=(--viewport 1920x1200 --data quality=1.5 --cut)   # rendered larger so the film can push in; --cut = only frames the cut uses

rive . --verify
[ "${KEEP:-0}" = 1 ] || rm -rf "$FR"
python3 tools/render_take.py carve "$FR/carve" --jobs "$JOBS" "${VIEW[@]}"
python3 tools/render_take.py mash  "$FR/mash"  --jobs "$JOBS" "${VIEW[@]}"
python3 tools/render_take.py ghoul "$FR/ghoul" --jobs 1 "${VIEW[@]}"
"$PY" tools/make_video.py "$FR" media/hollow.mp4
"$PY" tools/make_stills.py "$FR"
ls -la media
