#!/bin/bash
# usage: tools/shot.sh out.png [rive flags...]   (run from anywhere)
cd "$(dirname "$0")/.." || exit 1
export PATH=$HOME/.rive/bin:$PATH
export EGL_PLATFORM=${EGL_PLATFORM:-surfaceless}  # skip the flaky second GPU
out=$1; shift
rive . --screenshot="$out" "$@" 2>&1 | grep -E "error|warn|wrote|print|hollow" | grep -v "interlock"
