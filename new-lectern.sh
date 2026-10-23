#!/usr/bin/env bash
# new-lectern: a Lectern instance, from nothing to running, in one go.
#
#   ./new-lectern.sh                 in a copy of Lectern: set this one up
#   ./new-lectern.sh ~/apps/lectern  get Lectern into that folder (git clone) if it isn't there, then set it up
#
# It makes a Python environment (.venv in the folder; or LECTERN_VENV=~/venvs/cenv to use one you have),
# installs what Lectern needs, then runs `python app.py setup`, which asks a few questions (address,
# email, your admin account, importing old courses) and checks it all works. Safe to run again.
#
# Other settings: LECTERN_REPO (where to clone from), LECTERN_BRANCH.
set -euo pipefail

REPO=${LECTERN_REPO:-https://github.com/chandra-gummaluru/lectern.git}
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [ $# -ge 1 ]; then dir=$1
elif [ -f "$here/app.py" ] && [ -d "$here/server" ]; then dir=$here
else dir=$PWD/lectern; fi

need() { command -v "$1" >/dev/null 2>&1 || { echo "new-lectern: needs $1 ($2)" >&2; exit 1; }; }
need python3 "e.g. sudo apt install python3 python3-venv"

if [ ! -f "$dir/app.py" ]; then
  need git "e.g. sudo apt install git"
  echo "Getting Lectern into $dir…"
  git clone ${LECTERN_BRANCH:+--branch "$LECTERN_BRANCH"} "$REPO" "$dir"
fi
dir=$(cd "$dir" && pwd)

venv=${LECTERN_VENV:-$dir/.venv}
if [ ! -x "$venv/bin/python" ]; then
  echo "Making a Python environment in $venv…"
  python3 -m venv "$venv" || { echo "new-lectern: couldn't make it. On Ubuntu/Debian: sudo apt install python3-venv" >&2; exit 1; }
fi
echo "Installing what Lectern needs…"
"$venv/bin/python" -m pip install --quiet --upgrade pip
"$venv/bin/python" -m pip install --quiet -r "$dir/requirements.txt"

cd "$dir"
"$venv/bin/python" app.py setup
echo
echo "To start it later:  cd $dir && $venv/bin/python app.py"
