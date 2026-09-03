#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
VENV="$DIR/../.venv"

export PATH="$HOME/.foundry/bin:$HOME/.cargo/bin:$VENV/bin:$PATH"

$VENV/bin/python "$DIR/main.py" "$@"
